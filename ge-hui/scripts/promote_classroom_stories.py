#!/usr/bin/env python3
"""Promote approved classroom story reviews into compact public runtime cards."""

from __future__ import annotations

import argparse
import csv
import io
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from prepare_classroom_stories import CATEGORY_SPECS, timestamp_seconds
from search_srt import parse_srt


CATEGORY_FILES = {
    "buddhism": "stories-buddhism.md",
    "daoism": "stories-daoism.md",
    "fortune_telling": "stories-divination.md",
    "folk_supernatural": "stories-folk-supernatural.md",
}


def load_reviews(review_root: Path) -> list[dict[str, Any]]:
    reviews = []
    for path in sorted(review_root.glob("*/*.json")):
        try:
            review = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as error:
            raise ValueError(f"{path}: invalid JSON: {error}") from error
        if review.get("review_status") != "approved":
            continue
        review["_path"] = path
        reviews.append(review)
    return reviews


def validate_review(review: dict[str, Any], corpus_root: Path) -> list[str]:
    errors: list[str] = []
    story_id = str(review.get("story_id") or "missing-id")
    category = str(review.get("category") or "")
    if category not in CATEGORY_SPECS:
        errors.append(f"{story_id}: invalid-category")
    if not str(review.get("title") or "").strip():
        errors.append(f"{story_id}: missing-title")
    if not str(review.get("narrative_spine") or "").strip():
        errors.append(f"{story_id}: missing-narrative-spine")
    if not str(review.get("return_point") or "").strip():
        errors.append(f"{story_id}: missing-return-point")
    if not review.get("trigger_topics"):
        errors.append(f"{story_id}: missing-trigger-topics")
    source_file = str(review.get("source_file") or "")
    if not (corpus_root / "subtitles-raw" / source_file).is_file():
        errors.append(f"{story_id}: missing-source-file")
    try:
        start = timestamp_seconds(str(review.get("start") or ""))
        end = timestamp_seconds(str(review.get("end") or ""))
        if end <= start:
            errors.append(f"{story_id}: invalid-time-range")
        elif end - start > 900:
            errors.append(f"{story_id}: story-longer-than-15-minutes")
    except ValueError:
        errors.append(f"{story_id}: invalid-timestamp")
    return errors


def source_excerpt(review: dict[str, Any], corpus_root: Path, limit: int) -> str:
    start = timestamp_seconds(str(review["start"]))
    end = timestamp_seconds(str(review["end"]))
    path = corpus_root / "subtitles-raw" / str(review["source_file"])
    selected = []
    for record_start, record_end, text in parse_srt(path):
        if timestamp_seconds(record_end) < start or timestamp_seconds(record_start) > end:
            continue
        selected.append(text.strip())
    value = re.sub(r"\s+", " ", " ".join(selected)).strip()
    if len(value) > limit:
        return value[:limit].rstrip() + "……"
    return value


def markdown_card(review: dict[str, Any], corpus_root: Path, excerpt_limit: int) -> str:
    triggers = "、".join(str(value) for value in review.get("trigger_topics", []))
    excerpt = source_excerpt(review, corpus_root, excerpt_limit)
    return "\n".join(
        [
            f"## {review['title']} (`{review['story_id']}`)",
            "",
            f"- 触发：{triggers}",
            f"- 类型：`{review.get('story_type', '')}`",
            f"- 事实标签：`{review.get('truth_status', '')}`",
            f"- 来源：`{review['source_file']}`，{review['start']}–{review['end']}",
            "",
            "### 叙事骨架",
            "",
            str(review["narrative_spine"]).strip(),
            "",
            "### 回扣方式",
            "",
            str(review["return_point"]).strip(),
            "",
            "### 源语料提示",
            "",
            f"> {excerpt}",
            "",
        ]
    )


def index_tsv(reviews: list[dict[str, Any]]) -> str:
    output = io.StringIO(newline="")
    fieldnames = [
        "story_id",
        "category",
        "title",
        "triggers",
        "story_type",
        "truth_status",
        "source_file",
        "start",
        "end",
        "reference_file",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames, delimiter="\t", lineterminator="\n")
    writer.writeheader()
    for review in sorted(reviews, key=lambda row: (row["category"], row["story_id"])):
        writer.writerow(
            {
                "story_id": review["story_id"],
                "category": review["category"],
                "title": review["title"],
                "triggers": "|".join(str(value) for value in review.get("trigger_topics", [])),
                "story_type": review.get("story_type", ""),
                "truth_status": review.get("truth_status", ""),
                "source_file": review["source_file"],
                "start": review["start"],
                "end": review["end"],
                "reference_file": CATEGORY_FILES[review["category"]],
            }
        )
    return output.getvalue()


def promote(
    review_root: Path,
    corpus_root: Path,
    output_root: Path,
    *,
    excerpt_limit: int = 1200,
) -> list[Path]:
    reviews = load_reviews(review_root)
    errors = [error for review in reviews for error in validate_review(review, corpus_root)]
    if errors:
        raise ValueError("; ".join(errors[:20]))
    story_ids = [str(review["story_id"]) for review in reviews]
    if len(story_ids) != len(set(story_ids)):
        raise ValueError("duplicate-story-id")

    output_root.mkdir(parents=True, exist_ok=True)
    paths: list[Path] = []
    index_path = output_root / "story-index.tsv"
    index_path.write_text(index_tsv(reviews), encoding="utf-8", newline="\n")
    paths.append(index_path)

    grouped: defaultdict[str, list[dict[str, Any]]] = defaultdict(list)
    for review in reviews:
        grouped[str(review["category"])].append(review)
    for category, rows in sorted(grouped.items()):
        path = output_root / CATEGORY_FILES[category]
        heading = CATEGORY_SPECS[category]["display"]
        content = [
            f"# {heading}课堂故事卡",
            "",
            "仅使用人工批准的课堂范围。源语料提示用于保持叙事骨架，不代表其中的历史、宗教或玄学主张已经得到事实验证。",
            "",
        ]
        for row in sorted(rows, key=lambda item: str(item["story_id"])):
            content.append(markdown_card(row, corpus_root, excerpt_limit))
        path.write_text("\n".join(content).rstrip() + "\n", encoding="utf-8", newline="\n")
        paths.append(path)
    return paths


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review-root", type=Path, required=True)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--excerpt-limit", type=int, default=1200)
    args = parser.parse_args()
    if args.excerpt_limit < 100:
        parser.error("--excerpt-limit must be at least 100")
    paths = promote(
        args.review_root.resolve(),
        args.corpus_root.resolve(),
        args.output_root.resolve(),
        excerpt_limit=args.excerpt_limit,
    )
    print(f"Promoted approved classroom stories into {len(paths)} public files.")
    for path in paths:
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
