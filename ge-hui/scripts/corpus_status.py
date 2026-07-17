#!/usr/bin/env python3
"""Report whether the private short-video corpus has reached the style-promotion gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


REMOVABLE_NOISE_KINDS = frozenset(
    {
        "noise_music_hallucination",
        "noise_asr_loop",
        "noise_empty_repeat",
    }
)


def count_jsonl(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(1 for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip())


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}


def review_validation_errors(review: dict[str, Any]) -> list[str]:
    """Require explicit, internally consistent human decisions for every segment."""
    errors: list[str] = []
    if not str(review.get("reviewer") or "").strip():
        errors.append("missing-reviewer")
    if not str(review.get("reviewed_on") or "").strip():
        errors.append("missing-reviewed-on")
    segments = review.get("segments")
    if not isinstance(segments, list) or not segments:
        return errors + ["missing-segments"]
    for index, segment in enumerate(segments):
        status = segment.get("segment_status")
        raw = str(segment.get("raw_text") or "")
        corrected = str(segment.get("corrected_text") or "")
        correction_kind = str(segment.get("correction_kind") or "none")
        notes = str(segment.get("notes") or "").strip()
        if status not in {"verified", "corrected"}:
            errors.append(f"segment-{index}-invalid-status")
        elif status == "verified" and corrected != raw:
            errors.append(f"segment-{index}-verified-text-changed")
        elif status == "corrected" and corrected == raw:
            errors.append(f"segment-{index}-corrected-text-unchanged")
        if raw.strip() and not corrected.strip():
            if correction_kind not in REMOVABLE_NOISE_KINDS:
                errors.append(f"segment-{index}-blank-without-approved-noise-kind")
            if not notes:
                errors.append(f"segment-{index}-blank-without-review-note")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    args = parser.parse_args()
    root = args.private_root

    qc_files = list((root / "transcripts" / "qc").glob("*.json"))
    quality = {"high": 0, "medium": 0, "low": 0, "unknown": 0}
    for path in qc_files:
        value = str(load_json(path).get("quality") or "unknown")
        quality[value if value in quality else "unknown"] += 1

    reviewed = 0
    topics: set[str] = set()
    time_bands: set[str] = set()
    pending_reviews = 0
    queued_topics: set[str] = set()
    queued_time_bands: set[str] = set()
    invalid_reviewed: dict[str, list[str]] = {}
    for path in (root / "reviews").glob("*.json"):
        review = load_json(path)
        if review.get("review_status") == "reviewed":
            errors = review_validation_errors(review)
            if errors:
                invalid_reviewed[path.stem] = errors
                continue
            reviewed += 1
            topics.update(str(value) for value in review.get("topics", []) if value)
            time_band = review.get("time_band")
            if time_band:
                time_bands.add(str(time_band))
        elif review.get("review_status") == "pending":
            pending_reviews += 1
            queued_topics.update(str(value) for value in review.get("topics", []) if value)
            time_band = review.get("time_band")
            if time_band:
                queued_time_bands.add(str(time_band))

    usable = quality["high"] + quality["medium"]
    promoted = usable >= 60 and reviewed >= 30 and len(topics) >= 5 and len(time_bands) >= 3
    report = {
        "inventory": count_jsonl(root / "inventory.jsonl"),
        "selected": count_jsonl(root / "selection.jsonl"),
        "audio": len(list((root / "audio").glob("*.flac"))),
        "raw_transcripts": len(list((root / "transcripts" / "raw").glob("*.json"))),
        "clean_transcripts": len(list((root / "transcripts" / "clean").glob("*.srt"))),
        "reviewed_transcripts": len(list((root / "transcripts" / "reviewed").glob("*.srt"))),
        "quality": quality,
        "usable_transcripts": usable,
        "reviewed_clips": reviewed,
        "invalid_reviewed_clips": len(invalid_reviewed),
        "invalid_review_files": invalid_reviewed,
        "pending_review_clips": pending_reviews,
        "topic_count": len(topics),
        "time_band_count": len(time_bands),
        "queued_topic_count": len(queued_topics),
        "queued_time_band_count": len(queued_time_bands),
        "style_profile_ready": promoted,
        "requirements": {
            "usable_transcripts": 60,
            "reviewed_clips": 30,
            "topics": 5,
            "time_bands": 3,
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
