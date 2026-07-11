#!/usr/bin/env python3
"""Search SRT files and print citation-ready matches with timestamps."""

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
        if len(lines) < 3:
            continue
        match = TIME.match(lines[1])
        if match:
            records.append((match["start"], match["end"], " ".join(lines[2:])))
    return records


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("query", help="Literal text by default; use --regex for a regular expression")
    parser.add_argument("--corpus-root", type=Path, required=True, help="Directory containing subtitles-raw/")
    parser.add_argument("--context", type=int, default=0, help="Subtitle blocks to include before and after a match")
    parser.add_argument("--regex", action="store_true", help="Interpret query as a regular expression")
    parser.add_argument("--ignore-case", action="store_true", help="Match without case sensitivity")
    parser.add_argument("--max-results", type=int, default=20, help="Maximum matching blocks to print")
    args = parser.parse_args()

    if args.context < 0 or args.max_results < 1:
        parser.error("--context must be non-negative and --max-results must be positive")
    subtitle_dir = args.corpus_root / "subtitles-raw"
    if not subtitle_dir.is_dir():
        parser.error(f"Cannot find subtitles-raw under {args.corpus_root}")
    pattern = args.query if args.regex else re.escape(args.query)
    try:
        matcher = re.compile(pattern, re.IGNORECASE if args.ignore_case else 0)
    except re.error as error:
        parser.error(f"Invalid pattern: {error}")

    found = 0
    for file_path in sorted(subtitle_dir.glob("*.srt")):
        records = parse_srt(file_path)
        for index, (_, _, text) in enumerate(records):
            if not matcher.search(text):
                continue
            start = max(0, index - args.context)
            end = min(len(records), index + args.context + 1)
            print(f"{file_path.name} | {records[index][0]}–{records[index][1]}")
            for record_start, record_end, record_text in records[start:end]:
                print(f"  [{record_start}–{record_end}] {record_text}")
            found += 1
            if found >= args.max_results:
                return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
