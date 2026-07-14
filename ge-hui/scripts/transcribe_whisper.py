#!/usr/bin/env python3
"""Transcribe private FLAC audio with CUDA OpenAI Whisper and emit raw SRT/JSON plus QC."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


SUSPICIOUS_HALLUCINATIONS = (
    "字幕志愿者",
    "优优独播剧场",
    "请不吝点赞",
    "明镜与点点栏目",
    "感谢观看",
    "请订阅",
    "作词 作词",
    "作曲 编曲",
)


def load_hotwords(path: Path, metadata_text: str, maximum: int) -> list[str]:
    selected: list[str] = []
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle, delimiter="\t"):
            if row.get("status") != "approved":
                continue
            canonical = (row.get("canonical") or "").strip()
            domains = row.get("domains") or ""
            context = row.get("context_regex") or ""
            always = "name" in domains or "account" in domains
            matches = canonical in metadata_text
            if context:
                try:
                    matches = matches or bool(re.search(context, metadata_text))
                except re.error:
                    pass
            if canonical and (always or matches):
                selected.append(canonical)
            if len(selected) >= maximum:
                break
    return selected


def format_timestamp(seconds: float) -> str:
    milliseconds = max(0, round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def to_srt(segments: list[dict[str, Any]]) -> str:
    blocks = []
    for index, segment in enumerate(segments, 1):
        blocks.append(
            f"{index}\n{format_timestamp(float(segment['start']))} --> "
            f"{format_timestamp(float(segment['end']))}\n{str(segment['text']).strip()}"
        )
    return "\n\n".join(blocks) + "\n"


def repeated_ngram_ratio(text: str, size: int = 3) -> float:
    characters = [char for char in text if not char.isspace()]
    if len(characters) < size:
        return 0.0
    grams = ["".join(characters[index : index + size]) for index in range(len(characters) - size + 1)]
    counts = Counter(grams)
    repeats = sum(count - 1 for count in counts.values() if count > 1)
    return repeats / len(grams)


def qc_report(result: dict[str, Any]) -> dict[str, Any]:
    flagged: list[dict[str, Any]] = []
    for segment in result.get("segments", []):
        reasons: list[str] = []
        if float(segment.get("avg_logprob", 0)) < -1.0:
            reasons.append("low-logprob")
        if float(segment.get("compression_ratio", 0)) > 2.4:
            reasons.append("high-compression")
        if float(segment.get("no_speech_prob", 0)) > 0.6 and str(segment.get("text", "")).strip():
            reasons.append("speech-on-high-no-speech")
        if repeated_ngram_ratio(str(segment.get("text", ""))) > 0.25:
            reasons.append("repetition")
        if reasons:
            flagged.append(
                {
                    "id": segment.get("id"),
                    "start": segment.get("start"),
                    "end": segment.get("end"),
                    "text": segment.get("text"),
                    "reasons": reasons,
                }
            )
    text = str(result.get("text") or "".join(str(item.get("text", "")) for item in result.get("segments", [])))
    compact = "".join(char for char in text if not char.isspace())
    document_flags: list[str] = []
    repetition = repeated_ngram_ratio(text)
    if repetition > 0.25:
        document_flags.append("document-repetition")
    distinct_ratio = len(set(compact)) / max(1, len(compact))
    if len(compact) >= 30 and distinct_ratio < 0.12:
        document_flags.append("low-information")
    suspicious_hits = [phrase for phrase in SUSPICIOUS_HALLUCINATIONS if phrase in text]
    suspicious_occurrences = sum(text.count(phrase) for phrase in SUSPICIOUS_HALLUCINATIONS)
    if suspicious_hits:
        document_flags.append("known-hallucination-template")
    if len(compact) < 15:
        document_flags.append("low-content")

    ratio = len(flagged) / max(1, len(result.get("segments", [])))
    quality = "high" if ratio <= 0.05 else "medium" if ratio <= 0.2 else "low"
    if document_flags:
        hard_failure = bool(
            {"document-repetition", "low-information", "low-content"}.intersection(document_flags)
        ) or suspicious_occurrences >= 2
        quality = "low" if hard_failure else "medium"
    return {
        "quality": quality,
        "flagged_segment_ratio": ratio,
        "flagged_segments": flagged,
        "document_flags": document_flags,
        "document_repetition_ratio": repetition,
        "distinct_character_ratio": distinct_ratio,
        "suspicious_hallucination_phrases": suspicious_hits,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--hotwords", type=Path, required=True)
    parser.add_argument("--model", default="turbo")
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--qc-only",
        action="store_true",
        help="Recompute QC files from immutable raw JSON without running Whisper",
    )
    args = parser.parse_args()

    audio_dir = args.private_root / "audio"
    raw_dir = args.private_root / "transcripts" / "raw"
    qc_dir = args.private_root / "transcripts" / "qc"
    metadata_dir = args.private_root / "metadata"
    raw_dir.mkdir(parents=True, exist_ok=True)
    qc_dir.mkdir(parents=True, exist_ok=True)

    if args.qc_only:
        raw_files = sorted(raw_dir.glob("*.json"))[: args.limit]
        if not raw_files:
            parser.error(f"No raw transcript JSON found in {raw_dir}")
        for raw_json in raw_files:
            payload = json.loads(raw_json.read_text(encoding="utf-8-sig"))
            report = qc_report(payload)
            (qc_dir / raw_json.name).write_text(
                json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(
                f"{raw_json.stem}: {report['quality']}, "
                f"flags={','.join(report['document_flags']) or 'none'}"
            )
        return 0

    try:
        import torch
        import whisper
    except ImportError as error:
        parser.error(f"Missing transcription dependency: {error}")
    if not torch.cuda.is_available():
        parser.error("CUDA is unavailable; do not fall back silently to CPU")

    audio_files = sorted(audio_dir.glob("*.flac"))[: args.limit]
    if not audio_files:
        parser.error(f"No FLAC audio found in {audio_dir}")

    model = whisper.load_model(args.model, device="cuda")
    print(f"Loaded {args.model} on {torch.cuda.get_device_name(0)}")
    for audio_path in audio_files:
        video_id = audio_path.stem
        raw_json = raw_dir / f"{video_id}.json"
        if raw_json.exists() and not args.force:
            print(f"{video_id}: already-transcribed")
            continue
        metadata_path = metadata_dir / f"{video_id}.json"
        metadata_text = metadata_path.read_text(encoding="utf-8") if metadata_path.exists() else ""
        hotwords = load_hotwords(args.hotwords, metadata_text, maximum=40)
        initial_prompt = (
            "以下是说话者及本段可能出现的专名，请按语境识别：" + "、".join(hotwords)
            if hotwords
            else None
        )
        result = model.transcribe(
            str(audio_path),
            language="zh",
            task="transcribe",
            fp16=True,
            temperature=0,
            beam_size=5,
            word_timestamps=True,
            condition_on_previous_text=False,
            initial_prompt=initial_prompt,
        )
        report = qc_report(result)
        payload = {
            **result,
            "source_id": f"douyin-{video_id}",
            "audio_file": audio_path.name,
            "model": args.model,
            "device": torch.cuda.get_device_name(0),
            "transcribed_on": datetime.now(timezone.utc).isoformat(),
            "initial_prompt_terms": hotwords,
            "qc": report,
        }
        raw_json.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        (raw_dir / f"{video_id}.srt").write_text(
            to_srt(result.get("segments", [])), encoding="utf-8", newline="\n"
        )
        (qc_dir / f"{video_id}.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        print(f"{video_id}: {report['quality']}, flagged={len(report['flagged_segments'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
