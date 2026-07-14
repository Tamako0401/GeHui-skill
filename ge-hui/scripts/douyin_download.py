#!/usr/bin/env python3
"""Download selected public Douyin clips at low resolution and retain private FLAC audio."""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse
from urllib.request import Request, urlopen


AUTH_BLOCK = re.compile(
    r"captcha|verify|verification|fresh cookies|(?:log|sign)[ -]?in|required|"
    r"(?:http(?: status)?\s*)?429|too many requests|验证码|登录",
    re.IGNORECASE,
)
MEDIA_SUFFIXES = {".mp4", ".webm", ".mov", ".mkv", ".flv"}


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8-sig").splitlines()
        if line.strip()
    ]


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ffprobe_duration(path: Path) -> float:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    return float(result.stdout.strip())


def has_audio_stream(path: Path) -> bool:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a",
            "-show_entries",
            "stream=index",
            "-of",
            "csv=p=0",
            str(path),
        ],
        capture_output=True,
        text=True,
    )
    return result.returncode == 0 and bool(result.stdout.strip())


def find_media(media_dir: Path, video_id: str) -> Path | None:
    candidates = [
        path
        for path in media_dir.glob(f"{video_id}.*")
        if path.suffix.lower() in MEDIA_SUFFIXES and not path.name.endswith(".part")
    ]
    return max(candidates, key=lambda path: path.stat().st_mtime) if candidates else None


def write_status(status_dir: Path, video_id: str, payload: dict[str, Any]) -> None:
    status_dir.mkdir(parents=True, exist_ok=True)
    (status_dir / f"{video_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def download_direct(media_url: str, target: Path, user_agent: str) -> str | None:
    """Download a browser-resolved signed media URL without persisting it in logs."""
    part = target.with_suffix(target.suffix + ".part")
    last_error = "direct download failed"
    for attempt in range(3):
        try:
            request = Request(
                media_url,
                headers={
                    "User-Agent": user_agent,
                    "Referer": "https://www.douyin.com/",
                },
            )
            with urlopen(request, timeout=120) as response, part.open("wb") as output:
                shutil.copyfileobj(response, output, length=1024 * 1024)
            if part.stat().st_size < 1024:
                raise OSError("downloaded media is unexpectedly small")
            part.replace(target)
            return None
        except HTTPError as error:
            last_error = f"HTTP {error.code} while downloading browser-resolved media"
            if error.code in {401, 403, 429}:
                break
        except (OSError, URLError) as error:
            last_error = f"{type(error).__name__}: {error}"
        part.unlink(missing_ok=True)
        if attempt < 2:
            time.sleep((2**attempt) + random.uniform(0.5, 1.5))
    part.unlink(missing_ok=True)
    return last_error


def download_one(
    record: dict[str, Any],
    root: Path,
    cookies: Path,
    keep_video: bool,
    resolved: dict[str, Any] | None = None,
) -> tuple[str, str]:
    video_id = str(record["video_id"])
    source_url = str(record["source_url"])
    media_dir = root / "media"
    audio_dir = root / "audio"
    metadata_dir = root / "metadata"
    status_dir = root / "status"
    for directory in (media_dir, audio_dir, metadata_dir, status_dir):
        directory.mkdir(parents=True, exist_ok=True)

    audio_path = audio_dir / f"{video_id}.flac"
    if audio_path.exists():
        return video_id, "already-complete"

    source_method = "yt-dlp"
    media_definition: str | None = None
    if resolved:
        source_method = str(resolved.get("method") or "playwright-currentSrc")
        media_urls = [str(value) for value in resolved.get("media_urls") or [] if value]
        if not media_urls:
            media_urls = [str(resolved.get("media_url") or "")]
        user_agent = str(resolved.get("user_agent") or "Mozilla/5.0")
        media_path = media_dir / f"{video_id}.mp4"
        error = "No browser-resolved media URL contained an audio stream"
        selected_media_url: str | None = None
        for media_url in media_urls:
            if not media_url or media_url.startswith("blob:"):
                continue
            error = download_direct(media_url, media_path, user_agent)
            if error is None and has_audio_stream(media_path):
                selected_media_url = media_url
                break
            media_path.unlink(missing_ok=True)
            if error is None:
                error = "Browser-resolved media stream had no audio track"
        if selected_media_url is None:
            reason = "manual-auth-required" if AUTH_BLOCK.search(error) else "download-failed"
            write_status(
                status_dir,
                video_id,
                {
                    "source_id": record.get("source_id"),
                    "source_url": source_url,
                    "status": reason,
                    "checked_on": datetime.now(timezone.utc).isoformat(),
                    "message": error,
                },
            )
            return video_id, reason
        query = parse_qs(urlparse(selected_media_url).query)
        media_definition = (query.get("definition") or [None])[0]
    else:
        output_template = str(media_dir / f"{video_id}.%(ext)s")
        command = [
            sys.executable,
            "-m",
            "yt_dlp",
            "--no-playlist",
            "--cookies",
            str(cookies),
            "--sleep-requests",
            "3",
            "--sleep-interval",
            "3",
            "--max-sleep-interval",
            "8",
            "--retries",
            "5",
            "--fragment-retries",
            "5",
            "--download-archive",
            str(root / "download-archive.txt"),
            "--write-info-json",
            "--format",
            "worst[height<=480][acodec!=none]/worst[acodec!=none]",
            "--output",
            output_template,
            source_url,
        ]
        completed = subprocess.run(command, capture_output=True, text=True)
        combined_output = f"{completed.stdout}\n{completed.stderr}"
        if completed.returncode:
            reason = "manual-auth-required" if AUTH_BLOCK.search(combined_output) else "download-failed"
            write_status(
                status_dir,
                video_id,
                {
                    "source_id": record.get("source_id"),
                    "source_url": source_url,
                    "status": reason,
                    "checked_on": datetime.now(timezone.utc).isoformat(),
                    "message": combined_output[-2000:],
                },
            )
            return video_id, reason

        media_path = find_media(media_dir, video_id)
        if media_path is None:
            return video_id, "media-not-found"

    duration = ffprobe_duration(media_path)
    subprocess.run(
        [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-y",
            "-i",
            str(media_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "flac",
            str(audio_path),
        ],
        check=True,
    )
    audio_duration = ffprobe_duration(audio_path)
    if abs(duration - audio_duration) > max(1.0, duration * 0.02):
        audio_path.unlink(missing_ok=True)
        return video_id, "duration-mismatch"

    metadata = {
        **record,
        "captured_media_on": datetime.now(timezone.utc).isoformat(),
        "media_duration_seconds": duration,
        "audio_duration_seconds": audio_duration,
        "audio_path": str(audio_path.relative_to(root)),
        "audio_sha256": sha256(audio_path),
        "temporary_media_sha256": sha256(media_path),
        "temporary_media_deleted": not keep_video,
        "media_source_method": source_method,
        "media_definition": media_definition,
        "transcript_method": "openai-whisper-turbo-cuda",
        "review_status": "pending",
    }
    (metadata_dir / f"{video_id}.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    write_status(
        status_dir,
        video_id,
        {"source_id": record.get("source_id"), "status": "audio-ready"},
    )
    if not keep_video:
        media_path.unlink(missing_ok=True)
        if source_method == "yt-dlp":
            info_json = media_dir / f"{video_id}.info.json"
            if info_json.exists():
                shutil.move(str(info_json), metadata_dir / f"{video_id}.yt-dlp.json")
    return video_id, "audio-ready"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--private-root", type=Path, required=True)
    parser.add_argument("--cookies", type=Path, required=True)
    parser.add_argument(
        "--resolved-media",
        type=Path,
        help="Private JSONL produced by playwright_douyin.ps1 -Action resolve-media",
    )
    parser.add_argument(
        "--resolved-only",
        action="store_true",
        help="Process only IDs present in --resolved-media, preserving its order for batching",
    )
    parser.add_argument("--limit", type=int, default=10)
    parser.add_argument("--keep-video", action="store_true")
    args = parser.parse_args()

    if not args.cookies.is_file():
        parser.error("Cookie file not found; complete Playwright login and export it first")
    if shutil.which("ffmpeg") is None or shutil.which("ffprobe") is None:
        parser.error("ffmpeg and ffprobe are required")

    all_records = read_jsonl(args.selection)
    if not all_records:
        parser.error("Selection is empty")

    resolved_by_id: dict[str, dict[str, Any]] = {}
    resolved_items: list[dict[str, Any]] = []
    if args.resolved_media:
        if not args.resolved_media.is_file():
            parser.error("--resolved-media file not found")
        resolved_items = read_jsonl(args.resolved_media)
        resolved_by_id = {str(item.get("video_id")): item for item in resolved_items}
    if args.resolved_only:
        if not args.resolved_media:
            parser.error("--resolved-only requires --resolved-media")
        selection_by_id = {str(item["video_id"]): item for item in all_records}
        records = [
            selection_by_id[video_id]
            for item in resolved_items
            if (video_id := str(item.get("video_id"))) in selection_by_id
        ][: args.limit]
    else:
        records = all_records[: args.limit]
    if not records:
        parser.error("No matching records selected for download")

    counts: dict[str, int] = {}
    for index, record in enumerate(records):
        if index:
            time.sleep(random.uniform(3, 8))
        video_id = str(record["video_id"])
        resolved = resolved_by_id.get(video_id)
        audio_exists = (args.private_root / "audio" / f"{video_id}.flac").exists()
        if args.resolved_media and not resolved and not audio_exists:
            print(f"{video_id}: resolved-media-missing")
            counts["resolved-media-missing"] = counts.get("resolved-media-missing", 0) + 1
            return 2
        video_id, status = download_one(
            record, args.private_root, args.cookies, args.keep_video, resolved
        )
        counts[status] = counts.get(status, 0) + 1
        print(f"{video_id}: {status}")
        if status == "manual-auth-required":
            print("Stopped: complete the Douyin verification/login in Playwright, then retry.")
            return 2
    print(json.dumps(counts, ensure_ascii=False, sort_keys=True))
    return 0 if counts.get("audio-ready", 0) or counts.get("already-complete", 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
