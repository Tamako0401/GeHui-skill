#!/usr/bin/env python3
"""Measure classroom discourse markers without flattening functional oral speech."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from search_srt import parse_srt


PHRASE_MODELS: dict[str, dict[str, str]] = {
    "还明白": {
        "function": "确认理解，同时给刚讲完的判断划出边界",
        "force": "signature",
    },
    "还明白啊": {
        "function": "带强调的理解确认，常承接解释并推动下一步",
        "force": "signature-variant",
    },
    "对不对": {
        "function": "邀请听者认同，把陈述改造成课堂互动",
        "force": "high",
    },
    "知道吧": {
        "function": "提醒注意或预设共同知识，兼具轻度施压",
        "force": "high",
    },
    "懂不懂": {
        "function": "较强的理解检查，用于挑战、纠偏或强调后果",
        "force": "low-but-distinctive",
    },
    "是不是": {
        "function": "用反问建立共识或引出对照",
        "force": "supporting",
    },
    "明白吗": {
        "function": "直接确认理解，语气比“懂不懂”缓和",
        "force": "supporting",
    },
    "听懂": {
        "function": "检查刚才的解释是否被接收",
        "force": "supporting",
    },
}

BOUNDARY = "，,。！？?!；;：:\n\r\t "
PARTICLES = "啊呀吗吧呢嘛哈"
TRANSITIONS = ("所以", "那么", "然后", "但是", "不过", "因为", "就是", "其实", "那")


def compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def occurrences(value: str, phrase: str) -> list[int]:
    starts: list[int] = []
    offset = 0
    while True:
        found = value.find(phrase, offset)
        if found < 0:
            return starts
        starts.append(found)
        offset = found + 1


def local_position(value: str, start: int, phrase: str) -> str:
    """Classify a marker by its rhetorical location inside one subtitle segment."""
    end = start + len(phrase)
    before = value[:start].rstrip(BOUNDARY)
    after = value[end:]
    tail = after.lstrip(PARTICLES + BOUNDARY)
    head = before.rsplit("。", 1)[-1].rsplit("！", 1)[-1].rsplit("？", 1)[-1]
    head = head.lstrip(BOUNDARY)

    if not before and not tail:
        return "standalone"
    if not tail:
        return "segment_end"
    if any(tail.startswith(marker) for marker in TRANSITIONS):
        return "before_transition"
    if not head or len(head) <= 2:
        return "segment_start"
    return "embedded"


def document_band(offset: int, total: int) -> str:
    ratio = offset / max(1, total)
    if ratio < 0.2:
        return "opening_20pct"
    if ratio >= 0.8:
        return "closing_20pct"
    return "middle_60pct"


def build_report(corpus_root: Path) -> dict[str, Any]:
    classroom_root = corpus_root / "subtitles-raw"
    paths = sorted(classroom_root.glob("*.srt"))
    documents: list[dict[str, Any]] = []
    segment_count = 0
    character_count = 0

    for path in paths:
        records = parse_srt(path)
        segments = [compact(text) for _, _, text in records]
        length = sum(len(text) for text in segments)
        documents.append({"path": path, "records": records, "segments": segments, "length": length})
        segment_count += len(records)
        character_count += length

    phrase_rows: dict[str, Any] = {}
    for phrase, model in PHRASE_MODELS.items():
        count = 0
        covered: set[str] = set()
        bands = {"opening_20pct": 0, "middle_60pct": 0, "closing_20pct": 0}
        positions = {
            "standalone": 0,
            "segment_start": 0,
            "segment_end": 0,
            "before_transition": 0,
            "embedded": 0,
        }
        evidence: list[str] = []

        for document in documents:
            running = 0
            for record, segment in zip(document["records"], document["segments"]):
                starts = occurrences(segment, phrase)
                if starts:
                    covered.add(document["path"].name)
                    if len(evidence) < 5:
                        evidence.append(f"{document['path'].name}, {record[0]}–{record[1]}")
                for start in starts:
                    count += 1
                    bands[document_band(running + start, document["length"])] += 1
                    positions[local_position(segment, start, phrase)] += 1
                running += len(segment)

        phrase_rows[phrase] = {
            **model,
            "count": count,
            "documents": len(covered),
            "per_10k_characters": round(count * 10000 / character_count, 2) if character_count else 0,
            "document_bands": bands,
            "local_positions": positions,
            "evidence": evidence,
        }

    return {
        "profile": "measured-classroom-v1",
        "generated_on": datetime.now(timezone.utc).isoformat(),
        "source": "tracked classroom SRT files",
        "documents": len(documents),
        "segments": segment_count,
        "characters": character_count,
        "position_model": {
            "document_bands": "first 20%, middle 60%, and final 20% of each classroom file",
            "local_positions": "standalone/start/end/before-transition/embedded within an SRT segment",
        },
        "phrases": phrase_rows,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    report = build_report(args.corpus_root.resolve())
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload, encoding="utf-8", newline="\n")
        print(f"Wrote {report['profile']} for {report['documents']} classroom files to {args.output}.")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
