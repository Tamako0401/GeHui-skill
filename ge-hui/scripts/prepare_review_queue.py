#!/usr/bin/env python3
"""Prepare a private, coverage-aware queue for manual transcript review."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]


def assign_time_bands(records: list[dict[str, Any]]) -> None:
    dated = sorted(
        (row for row in records if row.get("published_on")),
        key=lambda row: str(row["published_on"]),
    )
    if not dated:
        for row in records:
            row["time_band"] = "unknown"
        return
    count = len(dated)
    for index, row in enumerate(dated):
        third = min(2, index * 3 // count)
        row["time_band"] = ("early", "middle", "recent")[third]
    for row in records:
        row.setdefault("time_band", "unknown")


def select_for_review(records: list[dict[str, Any]], limit: int) -> list[dict[str, Any]]:
    """Greedily maximize topic/time coverage, then balance their representation."""
    pool = list(records)
    chosen: list[dict[str, Any]] = []
    topic_counts: Counter[str] = Counter()
    band_counts: Counter[str] = Counter()
    quality_rank = {"high": 0, "medium": 1}
    while pool and len(chosen) < limit:
        def score(row: dict[str, Any]) -> tuple[Any, ...]:
            topic = str(row.get("topic") or "other")
            band = str(row.get("time_band") or "unknown")
            return (
                topic_counts[topic] > 0,
                band_counts[band] > 0,
                topic_counts[topic] + band_counts[band],
                quality_rank.get(str(row.get("quality")), 2),
                -int(row.get("digg_count") or 0),
                str(row.get("video_id") or ""),
            )

        item = min(pool, key=score)
        pool.remove(item)
        chosen.append(item)
        topic_counts[str(item.get("topic") or "other")] += 1
        band_counts[str(item.get("time_band") or "unknown")] += 1
    return chosen


def build_candidates(private_root: Path) -> list[dict[str, Any]]:
    selection = {str(row.get("video_id")): row for row in load_jsonl(private_root / "selection.jsonl")}
    candidates: list[dict[str, Any]] = []
    for qc_path in sorted((private_root / "transcripts" / "qc").glob("*.json")):
        qc = load_json(qc_path)
        if qc.get("quality") not in {"high", "medium"}:
            continue
        video_id = qc_path.stem
        raw_json = private_root / "transcripts" / "raw" / f"{video_id}.json"
        raw_srt = private_root / "transcripts" / "raw" / f"{video_id}.srt"
        audio = private_root / "audio" / f"{video_id}.flac"
        if not (raw_json.exists() and raw_srt.exists() and audio.exists()):
            continue
        metadata = selection.get(video_id, {})
        candidates.append(
            {
                "video_id": video_id,
                "source_url": metadata.get("source_url", f"https://www.douyin.com/video/{video_id}"),
                "title": metadata.get("title", ""),
                "topic": metadata.get("topic", "other"),
                "published_on": metadata.get("published_on"),
                "digg_count": metadata.get("digg_count"),
                "quality": qc.get("quality"),
                "qc": qc,
                "raw_json": raw_json,
                "raw_srt": raw_srt,
                "audio": audio,
            }
        )
    assign_time_bands(candidates)
    return candidates


def write_review(private_root: Path, record: dict[str, Any]) -> Path:
    reviews = private_root / "reviews"
    reviews.mkdir(parents=True, exist_ok=True)
    path = reviews / f"{record['video_id']}.json"
    if path.exists():
        return path
    raw = load_json(record["raw_json"])
    flagged_ids = {int(item.get("id", -1)) for item in record["qc"].get("flagged_segments", [])}
    payload = {
        "schema_version": 1,
        "video_id": record["video_id"],
        "source_url": record["source_url"],
        "title": record["title"],
        "topics": [record["topic"]],
        "published_on": record["published_on"],
        "time_band": record["time_band"],
        "machine_quality": record["quality"],
        "review_status": "pending",
        "reviewer": "",
        "reviewed_on": None,
        "review_notes": "",
        "private_files": {
            "audio": str(record["audio"]),
            "raw_json": str(record["raw_json"]),
            "raw_srt": str(record["raw_srt"]),
        },
        "qc_summary": {
            key: record["qc"].get(key)
            for key in ("quality", "flagged_segment_ratio", "document_flags")
        },
        "segments": [
            {
                "id": segment.get("id"),
                "start": segment.get("start"),
                "end": segment.get("end"),
                "raw_text": str(segment.get("text") or "").strip(),
                "corrected_text": str(segment.get("text") or "").strip(),
                "segment_status": "pending",
                "machine_flagged": int(segment.get("id", -1)) in flagged_ids,
                "notes": "",
            }
            for segment in raw.get("segments", [])
        ],
        "prepared_on": datetime.now(timezone.utc).isoformat(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--limit", type=int, default=30)
    args = parser.parse_args()

    candidates = build_candidates(args.private_root)
    selected = select_for_review(candidates, args.limit)
    queue_path = args.private_root / "review-queue.jsonl"
    queue_rows = []
    for order, record in enumerate(selected, start=1):
        review_path = write_review(args.private_root, record)
        queue_rows.append(
            {
                "order": order,
                "video_id": record["video_id"],
                "quality": record["quality"],
                "topic": record["topic"],
                "time_band": record["time_band"],
                "review_file": str(review_path),
            }
        )
    queue_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in queue_rows),
        encoding="utf-8",
    )
    topics = len({row["topic"] for row in queue_rows})
    bands = len({row["time_band"] for row in queue_rows})
    print(f"Prepared {len(queue_rows)} pending reviews across {topics} topics and {bands} time bands.")
    print("No clip was marked reviewed automatically.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
