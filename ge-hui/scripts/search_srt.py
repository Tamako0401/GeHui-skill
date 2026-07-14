#!/usr/bin/env python3
"""Search classroom and private short-video SRT files with citation-ready timestamps."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


TIME = re.compile(
    r"^(?P<start>\d{2}:\d{2}:\d{2},\d{3})\s+-->\s+(?P<end>\d{2}:\d{2}:\d{2},\d{3})$"
)


def parse_srt(path: Path) -> list[tuple[str, str, str]]:
    blocks = re.split(r"\r?\n\r?\n+", path.read_text(encoding="utf-8-sig").strip())
    records: list[tuple[str, str, str]] = []
    for block in blocks:
        lines = [line.strip() for line in block.splitlines() if line.strip()]
        time_index = next((i for i, line in enumerate(lines) if TIME.match(line)), None)
        if time_index is None or time_index + 1 >= len(lines):
            continue
        match = TIME.match(lines[time_index])
        assert match is not None
        records.append(
            (match["start"], match["end"], " ".join(lines[time_index + 1 :]))
        )
    return records


def subtitle_files(corpus_root: Path, source: str) -> list[tuple[str, Path]]:
    locations: list[tuple[str, Path]] = []
    if source in {"classroom", "all"}:
        locations.append(("classroom", corpus_root / "subtitles-raw"))
    if source in {"short-video", "all"}:
        locations.append(
            (
                "short-video",
                corpus_root / "local-data" / "short-video" / "transcripts" / "clean",
            )
        )

    files: list[tuple[str, Path]] = []
    for label, directory in locations:
        if directory.is_dir():
            files.extend((label, path) for path in sorted(directory.glob("*.srt")))
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Literal text by default; use --regex for a regex")
    parser.add_argument("--corpus-root", type=Path, required=True)
    parser.add_argument(
        "--source",
        choices=("classroom", "short-video", "all"),
        default="classroom",
    )
    parser.add_argument("--context", type=int, default=0)
    parser.add_argument("--regex", action="store_true")
    parser.add_argument("--ignore-case", action="store_true")
    parser.add_argument("--max-results", type=int, default=20)
    args = parser.parse_args()

    if args.context < 0 or args.max_results < 1:
        parser.error("--context must be non-negative and --max-results positive")

    pattern = args.query if args.regex else re.escape(args.query)
    try:
        matcher = re.compile(pattern, re.IGNORECASE if args.ignore_case else 0)
    except re.error as error:
        parser.error(f"Invalid pattern: {error}")

    files = subtitle_files(args.corpus_root.resolve(), args.source)
    if not files:
        parser.error(f"No {args.source} SRT files found under {args.corpus_root}")

    found = 0
    for source, file_path in files:
        records = parse_srt(file_path)
        for index, (_, _, value) in enumerate(records):
            if not matcher.search(value):
                continue
            start = max(0, index - args.context)
            end = min(len(records), index + args.context + 1)
            print(
                f"{source} | {file_path.name} | "
                f"{records[index][0]}–{records[index][1]}"
            )
            for record_start, record_end, text in records[start:end]:
                print(f"  [{record_start}–{record_end}] {text}")
            found += 1
            if found >= args.max_results:
                return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
