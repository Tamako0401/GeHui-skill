#!/usr/bin/env python3
"""Extract coverage-balanced classroom story candidates for human boundary review."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from search_srt import parse_srt


CATEGORY_SPECS: dict[str, dict[str, Any]] = {
    "buddhism": {
        "prefix": "BUD",
        "display": "佛教",
        "story_type": "religious_narrative",
        "truth_status": "religious_narrative_or_classroom_claim",
        "terms": {
            "释迦牟尼": 6,
            "佛陀": 5,
            "佛教": 3,
            "佛家": 4,
            "菩萨": 4,
            "地藏": 6,
            "地狱": 5,
            "轮回": 5,
            "业力": 4,
            "因果": 3,
            "和尚": 2,
            "佛经": 3,
            "前世": 3,
        },
    },
    "daoism": {
        "prefix": "DAO",
        "display": "道教与易学",
        "story_type": "religious_philosophical_narrative",
        "truth_status": "tradition_or_classroom_claim",
        "terms": {
            "道教": 5,
            "道家": 4,
            "道士": 5,
            "老子": 3,
            "道德经": 3,
            "易经": 4,
            "八卦": 5,
            "河图": 6,
            "洛书": 6,
            "阴阳": 4,
            "五行": 4,
            "修仙": 5,
            "道法": 5,
        },
    },
    "fortune_telling": {
        "prefix": "DIV",
        "display": "算命与术数",
        "story_type": "occult_instruction_or_personal_anecdote",
        "truth_status": "personal_anecdote_or_occult_claim",
        "terms": {
            "算命": 7,
            "生辰八字": 7,
            "生成八字": 7,
            "八字": 5,
            "看相": 6,
            "面相": 5,
            "手相": 5,
            "骨相": 5,
            "风水": 6,
            "占卜": 7,
            "占补": 7,
            "鬼市": 7,
            "梅花": 4,
            "师父": 3,
        },
    },
    "folk_supernatural": {
        "prefix": "FOLK",
        "display": "民间神异",
        "story_type": "folk_legend",
        "truth_status": "folk_legend_or_classroom_claim",
        "terms": {
            "出马仙": 9,
            "动物仙": 8,
            "狐黄白": 8,
            "狐狸精": 8,
            "黄鼠狼": 8,
            "蛇仙": 7,
            "鬼": 4,
            "妖": 5,
            "神仙": 4,
            "仙人": 4,
            "附体": 8,
            "保家仙": 8,
            "灵魂": 5,
            "托梦": 7,
        },
    },
}

ANCHORS = {
    "故事": 5,
    "传说": 4,
    "相传": 4,
    "据说": 3,
    "有一次": 4,
    "我告诉你": 3,
    "我跟你讲": 3,
    "我给你讲": 4,
    "我给你们讲": 4,
    "想不想听": 6,
    "你们知不知道": 3,
    "突然": 2,
    "后来": 2,
    "结果": 2,
    "当时": 1,
    "比如说": 1,
}


def timestamp_seconds(value: str) -> float:
    match = re.fullmatch(r"(\d{2}):(\d{2}):(\d{2}),(\d{3})", value)
    if not match:
        raise ValueError(f"Invalid SRT timestamp: {value}")
    hours, minutes, seconds, milliseconds = map(int, match.groups())
    return hours * 3600 + minutes * 60 + seconds + milliseconds / 1000


def timestamp(value: float) -> str:
    milliseconds = max(0, round(value * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, millis = divmod(remainder, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"


def compact(value: str) -> str:
    return re.sub(r"\s+", "", value)


def term_hits(value: str, terms: dict[str, int]) -> dict[str, int]:
    return {term: value.count(term) for term in terms if term in value}


def weighted_score(hits: dict[str, int], terms: dict[str, int]) -> int:
    return sum(terms[term] * min(count, 4) for term, count in hits.items())


def load_documents(corpus_root: Path) -> list[dict[str, Any]]:
    documents: list[dict[str, Any]] = []
    for path in sorted((corpus_root / "subtitles-raw").glob("*.srt")):
        records = [
            {
                "start": timestamp_seconds(start),
                "end": timestamp_seconds(end),
                "start_timestamp": start,
                "end_timestamp": end,
                "text": text,
            }
            for start, end, text in parse_srt(path)
        ]
        if records:
            documents.append({"path": path, "records": records})
    return documents


def window(records: list[dict[str, Any]], start: float, end: float) -> list[dict[str, Any]]:
    return [record for record in records if record["end"] >= start and record["start"] <= end]


def suggest_title(category: str, hits: dict[str, int]) -> str:
    spec = CATEGORY_SPECS[category]
    ranked = sorted(
        hits,
        key=lambda term: (-spec["terms"][term], -hits[term], term),
    )[:3]
    suffix = "、".join(ranked) if ranked else "待命名故事"
    return f"{spec['display']}：{suffix}"


def stable_story_id(category: str, source_file: str, seed_start: float) -> str:
    digest = hashlib.sha1(
        f"{category}|{source_file}|{round(seed_start, 1)}".encode("utf-8")
    ).hexdigest()[:8]
    return f"CLS-{CATEGORY_SPECS[category]['prefix']}-{digest.upper()}"


def extract_candidates(
    corpus_root: Path,
    *,
    per_category: int = 5,
    before_seconds: float = 45,
    after_seconds: float = 135,
) -> list[dict[str, Any]]:
    provisional: list[dict[str, Any]] = []
    for document in load_documents(corpus_root):
        records = document["records"]
        for seed in records:
            seed_text = compact(seed["text"])
            seed_has_anchor = any(anchor in seed_text for anchor in ANCHORS)
            seed_has_specific_term = any(
                any(term in seed_text and weight >= 5 for term, weight in spec["terms"].items())
                for spec in CATEGORY_SPECS.values()
            )
            if not (seed_has_anchor or seed_has_specific_term):
                continue

            suggested_start = max(0.0, seed["start"] - before_seconds)
            suggested_end = seed["end"] + after_seconds
            source_segments = window(records, suggested_start, suggested_end)
            context = compact("".join(item["text"] for item in source_segments))
            category_rows = []
            for category, spec in CATEGORY_SPECS.items():
                hits = term_hits(context, spec["terms"])
                category_rows.append((weighted_score(hits, spec["terms"]), category, hits))
            category_score, category, hits = max(category_rows, key=lambda row: (row[0], row[1]))
            anchor_hits = term_hits(context, ANCHORS)
            anchor_score = weighted_score(anchor_hits, ANCHORS)
            if category_score < 7 or (anchor_score == 0 and category_score < 14):
                continue

            total_score = category_score + min(anchor_score, 20)
            provisional.append(
                {
                    "category": category,
                    "source_file": document["path"].name,
                    "seed_start": seed["start"],
                    "suggested_start": suggested_start,
                    "suggested_end": suggested_end,
                    "score": total_score,
                    "category_score": category_score,
                    "anchor_score": anchor_score,
                    "matched_terms": hits,
                    "matched_anchors": anchor_hits,
                    "source_segments": source_segments,
                }
            )

    selected: list[dict[str, Any]] = []
    for category in CATEGORY_SPECS:
        pool = sorted(
            (row for row in provisional if row["category"] == category),
            key=lambda row: (-row["score"], row["source_file"], row["seed_start"]),
        )
        chosen: list[dict[str, Any]] = []
        seen_sources: set[str] = set()

        def is_duplicate(candidate: dict[str, Any]) -> bool:
            center = (candidate["suggested_start"] + candidate["suggested_end"]) / 2
            return any(
                row["source_file"] == candidate["source_file"]
                and abs((row["suggested_start"] + row["suggested_end"]) / 2 - center) < 150
                for row in chosen
            )

        # First maximize source-file coverage so one dense lecture cannot consume the batch.
        for candidate in pool:
            if len(chosen) >= per_category:
                break
            if candidate["source_file"] in seen_sources or is_duplicate(candidate):
                continue
            chosen.append(candidate)
            seen_sources.add(candidate["source_file"])
        # Then fill remaining slots with distinct windows from the strongest sources.
        for candidate in pool:
            if len(chosen) >= per_category:
                break
            if candidate in chosen or is_duplicate(candidate):
                continue
            chosen.append(candidate)
        selected.extend(chosen)
    return sorted(selected, key=lambda row: (row["category"], row["source_file"], row["seed_start"]))


def review_payload(candidate: dict[str, Any]) -> dict[str, Any]:
    category = candidate["category"]
    spec = CATEGORY_SPECS[category]
    story_id = stable_story_id(category, candidate["source_file"], candidate["seed_start"])
    segments = [
        {
            "start": item["start_timestamp"],
            "end": item["end_timestamp"],
            "text": item["text"],
        }
        for item in candidate["source_segments"]
    ]
    return {
        "schema_version": 1,
        "story_id": story_id,
        "review_status": "pending",
        "category": category,
        "title": suggest_title(category, candidate["matched_terms"]),
        "source_file": candidate["source_file"],
        "start": timestamp(candidate["suggested_start"]),
        "end": timestamp(candidate["suggested_end"]),
        "trigger_topics": sorted(candidate["matched_terms"], key=lambda term: (-candidate["matched_terms"][term], term)),
        "story_type": spec["story_type"],
        "truth_status": spec["truth_status"],
        "narrative_spine": "",
        "return_point": "",
        "review_notes": "",
        "automatic_evidence": {
            "score": candidate["score"],
            "category_score": candidate["category_score"],
            "anchor_score": candidate["anchor_score"],
            "matched_terms": candidate["matched_terms"],
            "matched_anchors": candidate["matched_anchors"],
        },
        "source_segments": segments,
        "human_instructions": [
            "修改 title。",
            "把 start 和 end 改成故事真实起止时间，格式 HH:MM:SS,mmm。",
            "确认后把 review_status 改成 approved；误判候选直接删除本 JSON。",
            "narrative_spine 和 return_point 暂时留空，后续由技能构建流程从已批准范围提炼。",
        ],
        "prepared_on": datetime.now(timezone.utc).isoformat(),
    }


def write_review_queue(candidates: list[dict[str, Any]], output_root: Path) -> list[Path]:
    reviews_root = output_root / "story-reviews"
    paths: list[Path] = []
    queue_rows: list[dict[str, Any]] = []
    for candidate in candidates:
        payload = review_payload(candidate)
        category_root = reviews_root / payload["category"]
        category_root.mkdir(parents=True, exist_ok=True)
        path = category_root / f"{payload['story_id']}.json"
        if not path.exists():
            path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        paths.append(path)
        queue_rows.append(
            {
                "story_id": payload["story_id"],
                "category": payload["category"],
                "review_file": str(path),
            }
        )
    queue_path = output_root / "story-review-queue.jsonl"
    output_root.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in queue_rows),
        encoding="utf-8",
        newline="\n",
    )
    return paths


def human_review_errors(review: dict[str, Any], corpus_root: Path) -> list[str]:
    errors: list[str] = []
    story_id = str(review.get("story_id") or "missing-id")
    if review.get("review_status") not in {"pending", "approved"}:
        errors.append(f"{story_id}: invalid-review-status")
    if review.get("review_status") != "approved":
        return errors
    if not str(review.get("title") or "").strip():
        errors.append(f"{story_id}: missing-title")
    source_file = str(review.get("source_file") or "")
    source_path = corpus_root / "subtitles-raw" / source_file
    if not source_path.is_file():
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


def review_status_report(output_root: Path, corpus_root: Path) -> dict[str, Any]:
    counts: Counter[str] = Counter()
    invalid: dict[str, list[str]] = {}
    files = sorted((output_root / "story-reviews").glob("*/*.json"))
    for path in files:
        try:
            review = json.loads(path.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as error:
            invalid[str(path)] = [f"invalid-json: {error}"]
            continue
        status = str(review.get("review_status") or "missing")
        counts[status] += 1
        errors = human_review_errors(review, corpus_root)
        if errors:
            invalid[str(path)] = errors
    return {
        "review_files": len(files),
        "status": dict(counts),
        "invalid_files": invalid,
        "human_gate_ready": bool(files) and counts["pending"] == 0 and not invalid,
        "next_step": (
            "Fill narrative_spine and return_point, then run promote_classroom_stories.py."
            if bool(files) and counts["pending"] == 0 and not invalid
            else "Edit title/start/end, set approved, or delete false-positive JSON files."
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--per-category", type=int, default=5)
    parser.add_argument("--before-seconds", type=float, default=45)
    parser.add_argument("--after-seconds", type=float, default=135)
    parser.add_argument("--status-only", action="store_true")
    args = parser.parse_args()
    if args.per_category < 1 or args.before_seconds < 0 or args.after_seconds <= 0:
        parser.error("invalid extraction limits")

    if args.status_only:
        report = review_status_report(args.output_root.resolve(), args.corpus_root.resolve())
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if not report["invalid_files"] else 1

    candidates = extract_candidates(
        args.corpus_root.resolve(),
        per_category=args.per_category,
        before_seconds=args.before_seconds,
        after_seconds=args.after_seconds,
    )
    paths = write_review_queue(candidates, args.output_root.resolve())
    counts = Counter(candidate["category"] for candidate in candidates)
    print(f"Prepared {len(paths)} pending classroom story reviews: {dict(counts)}")
    print(f"Edit JSON files under {args.output_root.resolve() / 'story-reviews'}")
    print("Existing review JSON files were not overwritten.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
