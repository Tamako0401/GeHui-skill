#!/usr/bin/env python3
"""Export immutable human-reviewed JSON decisions as private SRT/JSON derivatives."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from corpus_status import review_validation_errors


def timestamp(seconds: float) -> str:
    milliseconds = max(0, round(float(seconds) * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def export_review(review_path: Path, output_dir: Path) -> tuple[Path, Path, int]:
    review: dict[str, Any] = json.loads(review_path.read_text(encoding="utf-8-sig"))
    if review.get("review_status") != "reviewed":
        raise ValueError(f"{review_path.name}: review_status is not reviewed")
    errors = review_validation_errors(review)
    if errors:
        raise ValueError(f"{review_path.name}: " + ", ".join(errors[:10]))

    segments = []
    omitted_segments = []
    blocks = []
    for source in review.get("segments", []):
        text = str(source.get("corrected_text") or "").strip()
        start = float(source.get("start") or 0)
        end = float(source.get("end") or start)
        if not text:
            omitted_segments.append(
                {
                    "id": source.get("id"),
                    "start": start,
                    "end": end,
                    "raw_text": str(source.get("raw_text") or ""),
                    "correction_kind": source.get("correction_kind", "none"),
                    "notes": source.get("notes", ""),
                }
            )
            continue
        if end <= start:
            continue
        item = {
            "id": source.get("id"),
            "start": start,
            "end": end,
            "text": text,
            "review_decision": source.get("segment_status"),
            "correction_kind": source.get("correction_kind", "none"),
            "notes": source.get("notes", ""),
        }
        segments.append(item)
        blocks.append(f"{len(blocks) + 1}\n{timestamp(start)} --> {timestamp(end)}\n{text}")

    output_dir.mkdir(parents=True, exist_ok=True)
    video_id = str(review.get("video_id") or review_path.stem)
    srt_path = output_dir / f"{video_id}.srt"
    json_path = output_dir / f"{video_id}.json"
    srt_path.write_text("\n\n".join(blocks) + "\n", encoding="utf-8", newline="\n")
    json_path.write_text(
        json.dumps(
            {
                "video_id": video_id,
                "source_url": review.get("source_url"),
                "title": review.get("title"),
                "topics": review.get("topics", []),
                "time_band": review.get("time_band"),
                "reviewer": review.get("reviewer"),
                "reviewed_on": review.get("reviewed_on"),
                "source_review_file": str(review_path),
                "exported_on": datetime.now(timezone.utc).isoformat(),
                "segments": segments,
                "omitted_segments": omitted_segments,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return srt_path, json_path, len(segments)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    args = parser.parse_args()
    reviews_dir = args.private_root / "reviews"
    output_dir = args.private_root / "transcripts" / "reviewed"
    exported = 0
    segments = 0
    for review_path in sorted(reviews_dir.glob("*.json")):
        review = json.loads(review_path.read_text(encoding="utf-8-sig"))
        if review.get("review_status") != "reviewed":
            continue
        _, _, count = export_review(review_path, output_dir)
        exported += 1
        segments += count
    print(f"Exported {exported} reviewed transcripts with {segments} non-empty timed segments.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
