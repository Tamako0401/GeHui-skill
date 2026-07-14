#!/usr/bin/env python3
"""Create a private aggregate style report from fully reviewed short videos."""

from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PHRASE_GROUPS = {
    "direct_address": ["大家", "朋友", "你看", "我们来看", "给大家"],
    "question_frame": ["为什么", "什么", "怎么", "是不是", "对不对", "知道吗"],
    "explanation": ["其实", "也就是说", "因为", "所以", "但是", "那么"],
    "demonstration": ["你看", "来看", "看一下", "这个", "这里"],
    "uncertainty": ["可能", "大概", "也许", "据说", "传说", "应该"],
    "transition": ["然后", "后来", "接下来", "最后", "再看"],
}


def load_reviewed(root: Path) -> list[dict[str, Any]]:
    reviews = []
    for path in sorted((root / "reviews").glob("*.json")):
        review = json.loads(path.read_text(encoding="utf-8-sig"))
        if review.get("review_status") != "reviewed":
            continue
        segments = review.get("segments") or []
        if not segments or any(item.get("segment_status") not in {"verified", "corrected"} for item in segments):
            continue
        review["_path"] = str(path)
        review["_text"] = "".join(str(item.get("corrected_text") or "") for item in segments)
        reviews.append(review)
    return reviews


def phrase_statistics(reviews: list[dict[str, Any]]) -> dict[str, Any]:
    total_chars = sum(len(review["_text"]) for review in reviews)
    output: dict[str, Any] = {}
    for group, phrases in PHRASE_GROUPS.items():
        rows = []
        for phrase in phrases:
            sources = [str(review.get("video_id")) for review in reviews if phrase in review["_text"]]
            count = sum(review["_text"].count(phrase) for review in reviews)
            rows.append(
                {
                    "phrase": phrase,
                    "count": count,
                    "clips": len(sources),
                    "per_10k_chars": round(count * 10000 / total_chars, 2) if total_chars else 0,
                    "evidence_video_ids": sources[:10],
                }
            )
        output[group] = sorted(rows, key=lambda row: (-row["clips"], -row["count"], row["phrase"]))
    return output


def ngrams(reviews: list[dict[str, Any]], length: int, limit: int = 30) -> list[dict[str, Any]]:
    counts: Counter[str] = Counter()
    clips: defaultdict[str, set[str]] = defaultdict(set)
    for review in reviews:
        text = re.sub(r"[^\u4e00-\u9fff]", "", review["_text"])
        seen = set()
        for index in range(max(0, len(text) - length + 1)):
            value = text[index : index + length]
            if len(set(value)) == 1:
                continue
            counts[value] += 1
            seen.add(value)
        for value in seen:
            clips[value].add(str(review.get("video_id")))
    rows = [
        {"text": value, "count": count, "clips": len(clips[value])}
        for value, count in counts.items()
        if len(clips[value]) >= 2
    ]
    return sorted(rows, key=lambda row: (-row["clips"], -row["count"], row["text"]))[:limit]


def opening_markers(reviews: list[dict[str, Any]]) -> list[dict[str, Any]]:
    markers = ["大家", "朋友", "现在", "今天", "你看", "来看", "这个", "为什么", "说到"]
    rows = []
    for marker in markers:
        sources = [str(review.get("video_id")) for review in reviews if marker in review["_text"][:80]]
        rows.append({"marker": marker, "clips": len(sources), "evidence_video_ids": sources[:10]})
    return sorted(rows, key=lambda row: (-row["clips"], row["marker"]))


def build_report(root: Path) -> dict[str, Any]:
    reviews = load_reviewed(root)
    segments = [segment for review in reviews for segment in review.get("segments", [])]
    chars = sum(len(review["_text"]) for review in reviews)
    return {
        "generated_on": datetime.now(timezone.utc).isoformat(),
        "source": "private manually reviewed transcript JSON",
        "reviewed_clips": len(reviews),
        "segments": len(segments),
        "characters": chars,
        "average_characters_per_clip": round(chars / len(reviews), 1) if reviews else 0,
        "average_characters_per_segment": round(chars / len(segments), 1) if segments else 0,
        "corrected_segments": sum(item.get("segment_status") == "corrected" for item in segments),
        "topics": dict(Counter(topic for review in reviews for topic in review.get("topics", []))),
        "time_bands": dict(Counter(str(review.get("time_band")) for review in reviews)),
        "opening_markers_first_80_chars": opening_markers(reviews),
        "phrase_groups": phrase_statistics(reviews),
        "frequent_ngrams": {str(length): ngrams(reviews, length) for length in (2, 3, 4, 5)},
        "privacy_note": "Evidence IDs stay private; publish only aggregate rules and minimal short phrases.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    output = args.output or args.private_root / "style-report.json"
    report = build_report(args.private_root)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote private aggregate report for {report['reviewed_clips']} clips and "
        f"{report['segments']} segments to {output}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
