#!/usr/bin/env python3
"""Verify a Douyin profile, merge Playwright-discovered video links, and sample clips."""

from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


VIDEO_ID = re.compile(r"(?:https?://www\.douyin\.com)?/video/(?P<id>\d+)")
CARD_PREFIX = re.compile(
    r"^(?P<pinned>置顶\s+)?(?P<digg>\d+(?:\.\d+)?(?:万|w)?)\s+(?P<title>.+)$",
    re.IGNORECASE | re.DOTALL,
)

TOPIC_KEYWORDS = (
    ("瓷器鉴定", ("瓷", "窑", "釉", "青花", "斗彩", "陶器")),
    ("书画艺术", ("书法", "国画", "水墨", "绘画", "山水画", "字画", "画")),
    ("佛道民俗", ("佛", "菩萨", "观音", "禅", "道教", "修仙", "民俗", "祭奠", "信仰")),
    ("神话怪谈", ("紫薇", "圣女", "鬼", "妖", "怪", "神话", "救世", "地球升维")),
    ("历史文化", ("历史", "古代", "红楼梦", "名将", "文化", "文物", "兵器")),
    ("情感人生", ("爱情", "愛", "感情", "人生", "生命", "心动", "真情", "爱")),
)

SPEECH_POSITIVE = (
    "介绍",
    "鉴定",
    "鉴赏",
    "讲",
    "历史",
    "时期",
    "文化",
    "收藏",
    "瓷器",
    "书法",
    "绘画",
    "国画",
    "佛像",
    "天珠",
    "为什么",
    "什么是",
)
SPEECH_NEGATIVE = (
    "歌词",
    "歌曲",
    "一首歌",
    "演唱",
    "翻唱",
    "音乐",
    "情感共鸣",
    "爱的力量",
    "愛情",
    "爱情",
)


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8-sig").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def write_jsonl(path: Path, records: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in records)
    path.write_text(content, encoding="utf-8", newline="\n")


def verify_profile(profile_text: str, expected_handle: str, expected_name: str) -> None:
    compact = re.sub(r"\s+", "", profile_text)
    missing = [value for value in (expected_handle, expected_name) if value not in compact]
    if missing:
        raise ValueError(f"Profile identity mismatch; missing: {', '.join(missing)}")


def parse_digg(value: str) -> int:
    normalized = value.strip().lower()
    multiplier = 10_000 if normalized.endswith(("万", "w")) else 1
    normalized = normalized.rstrip("万w")
    return int(float(normalized) * multiplier)


def parse_card_text(value: str) -> tuple[str, int | None, bool]:
    compact = re.sub(r"\s+", " ", value).strip()
    match = CARD_PREFIX.match(compact)
    if not match:
        return compact, None, False
    return match.group("title").strip(), parse_digg(match.group("digg")), bool(match.group("pinned"))


def infer_published_on(video_id: str) -> str | None:
    """Infer UTC time from the high 32 bits used by Douyin/TikTok snowflake IDs."""
    try:
        timestamp = int(video_id) >> 32
        value = datetime.fromtimestamp(timestamp, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    if not 2016 <= value.year <= datetime.now(timezone.utc).year + 1:
        return None
    return value.isoformat()


def infer_topic(title: str) -> str:
    lowered = title.lower()
    for topic, keywords in TOPIC_KEYWORDS:
        if any(keyword.lower() in lowered for keyword in keywords):
            return topic
    return "生活其他"


def speech_score(title: str) -> int:
    score = sum(2 for value in SPEECH_POSITIVE if value in title)
    score -= sum(3 for value in SPEECH_NEGATIVE if value in title)
    return score


def normalize_link(item: Any, captured_on: str) -> dict[str, Any] | None:
    if isinstance(item, str):
        item = {"url": item}
    if not isinstance(item, dict):
        return None
    url = str(item.get("url") or item.get("href") or "")
    match = VIDEO_ID.search(url)
    if not match:
        return None
    video_id = match.group("id")
    engagement = item.get("engagement") or {}
    title, card_digg, pinned = parse_card_text(str(item.get("title") or item.get("text") or ""))
    published_on = item.get("published_on") or infer_published_on(video_id)
    return {
        "source_id": f"douyin-{video_id}",
        "video_id": video_id,
        "source_url": f"https://www.douyin.com/video/{video_id}",
        "title": title,
        "published_on": published_on,
        "published_on_source": item.get("published_on_source")
        or ("video-id-inference" if published_on else None),
        "duration_seconds": item.get("duration_seconds"),
        "digg_count": engagement.get("digg") or item.get("digg_count") or card_digg,
        "digg_count_source": item.get("digg_count_source")
        or ("profile-card" if card_digg is not None else None),
        "comment_count": engagement.get("comment") or item.get("comment_count"),
        "share_count": engagement.get("share") or item.get("share_count"),
        "topic": str(item.get("topic") or infer_topic(title)),
        "speech_score": item.get("speech_score")
        if item.get("speech_score") is not None
        else speech_score(title),
        "speech_score_source": item.get("speech_score_source") or "title-heuristic",
        "pinned": bool(item.get("pinned", pinned)),
        "captured_on": captured_on,
        "status": str(item.get("status") or "inventoried"),
    }


def merge_records(existing: list[dict[str, Any]], incoming: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged = {str(item["video_id"]): dict(item) for item in existing}
    for item in incoming:
        video_id = str(item["video_id"])
        previous = merged.get(video_id, {})
        combined = dict(previous)
        for key, value in item.items():
            if value not in (None, "", "unlabeled") or key not in combined:
                combined[key] = value
        combined["first_captured_on"] = previous.get(
            "first_captured_on", previous.get("captured_on", item["captured_on"])
        )
        merged[video_id] = combined
    return sorted(merged.values(), key=lambda value: str(value["video_id"]))


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def interleave_topics(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    queues: dict[str, deque[dict[str, Any]]] = defaultdict(deque)
    for item in records:
        queues[str(item.get("topic") or "unlabeled")].append(item)
    ordered: list[dict[str, Any]] = []
    topics = sorted(queues)
    while topics:
        remaining: list[str] = []
        for topic in topics:
            queue = queues[topic]
            if queue:
                ordered.append(queue.popleft())
            if queue:
                remaining.append(topic)
        topics = remaining
    return ordered


def stratified_sample(records: list[dict[str, Any]], target: int) -> list[dict[str, Any]]:
    if len(records) <= target:
        return list(records)
    dates = sorted(records, key=lambda item: str(item.get("published_on") or ""))
    date_band: dict[str, int] = {}
    for index, item in enumerate(dates):
        date_band[str(item["video_id"])] = min(2, index * 3 // len(dates))

    engagements = sorted(
        records,
        key=lambda item: _number(item.get("digg_count"))
        + _number(item.get("comment_count"))
        + _number(item.get("share_count")),
    )
    engagement_band: dict[str, int] = {}
    for index, item in enumerate(engagements):
        engagement_band[str(item["video_id"])] = min(2, index * 3 // len(engagements))

    buckets: dict[tuple[str, int, int], deque[dict[str, Any]]] = defaultdict(deque)
    for item in sorted(records, key=lambda value: str(value["video_id"])):
        video_id = str(item["video_id"])
        key = (str(item.get("topic") or "unlabeled"), date_band[video_id], engagement_band[video_id])
        buckets[key].append(item)

    selected: list[dict[str, Any]] = []
    keys = sorted(buckets)
    while len(selected) < target and keys:
        next_keys: list[tuple[str, int, int]] = []
        for key in keys:
            bucket = buckets[key]
            if bucket and len(selected) < target:
                selected.append(bucket.popleft())
            if bucket:
                next_keys.append(key)
        keys = next_keys
    return interleave_topics(selected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--links", type=Path, required=True, help="Playwright-exported JSON array")
    parser.add_argument("--profile-text", type=Path, required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--expected-handle", default="shibu71947")
    parser.add_argument("--expected-name", default="石不说古天珠瓷书画")
    parser.add_argument("--target", type=int, default=80)
    args = parser.parse_args()

    if args.target < 1:
        parser.error("--target must be positive")
    profile_text = args.profile_text.read_text(encoding="utf-8-sig")
    try:
        verify_profile(profile_text, args.expected_handle, args.expected_name)
    except ValueError as error:
        parser.error(str(error))

    captured_on = datetime.now(timezone.utc).isoformat()
    raw_links = read_json(args.links)
    if not isinstance(raw_links, list):
        parser.error("--links must contain a JSON array")
    incoming = [record for item in raw_links if (record := normalize_link(item, captured_on))]
    if not incoming:
        parser.error("No canonical /video/<id> links found")

    merged = merge_records(read_jsonl(args.inventory), incoming)
    speech_candidates = [item for item in merged if _number(item.get("speech_score")) >= 1]
    selection_pool = speech_candidates if len(speech_candidates) >= args.target else merged
    selected = stratified_sample(selection_pool, args.target)
    write_jsonl(args.inventory, merged)
    write_jsonl(args.selection, selected)
    print(f"Verified profile; inventory={len(merged)}, selected={len(selected)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
