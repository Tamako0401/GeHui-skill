#!/usr/bin/env python3
"""Build a private hotword review queue and apply only approved contextual rules."""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


FIELDS = [
    "canonical",
    "observed",
    "pinyin",
    "domains",
    "context_regex",
    "evidence_source",
    "evidence_context",
    "evidence_count",
    "status",
    "reviewer",
    "updated_at",
]


def load_rules(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return [dict(row) for row in csv.DictReader(handle, delimiter="\t")]


def write_tsv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=FIELDS, delimiter="\t", extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def scan_candidates(
    raw_json_dir: Path, approved: Path, qc_dir: Path | None = None
) -> list[dict[str, Any]]:
    rules = load_rules(approved)
    occurrences: dict[tuple[str, str], dict[str, Any]] = {}
    for path in sorted(raw_json_dir.glob("*.json")):
        if qc_dir is not None:
            qc_path = qc_dir / path.name
            if not qc_path.exists():
                continue
            qc = json.loads(qc_path.read_text(encoding="utf-8-sig"))
            if qc.get("quality") not in {"high", "medium"}:
                continue
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        source_id = str(payload.get("source_id") or path.stem)
        for segment in payload.get("segments", []):
            text = str(segment.get("text") or "").strip()
            evidence = f"{source_id}@{segment.get('start', 0):.2f}-{segment.get('end', 0):.2f}"
            for rule in rules:
                canonical = (rule.get("canonical") or "").strip()
                for variant in filter(None, re.split(r"[|,，;；]", rule.get("variants") or "")):
                    variant = variant.strip()
                    if variant and variant in text:
                        key = (canonical, variant)
                        row = occurrences.setdefault(
                            key,
                            {
                                "canonical": canonical,
                                "observed": variant,
                                "pinyin": rule.get("pinyin", ""),
                                "domains": rule.get("domains", ""),
                                "context_regex": rule.get("context_regex", ""),
                                "evidence_source": [],
                                "evidence_context": [],
                                "evidence_count": 0,
                                "status": "candidate",
                                "reviewer": "",
                                "updated_at": datetime.now(timezone.utc).date().isoformat(),
                            },
                        )
                        row["evidence_source"].append(evidence)
                        row["evidence_context"].append(text)
                        row["evidence_count"] += 1

            reasons = []
            if float(segment.get("avg_logprob", 0)) < -1.0:
                reasons.append("low-logprob")
            if float(segment.get("compression_ratio", 0)) > 2.4:
                reasons.append("high-compression")
            if reasons:
                key = ("", text)
                row = occurrences.setdefault(
                    key,
                    {
                        "canonical": "",
                        "observed": text,
                        "pinyin": "",
                        "domains": "short-video",
                        "context_regex": "",
                        "evidence_source": [],
                        "evidence_context": [],
                        "evidence_count": 0,
                        "status": "needs-term-review",
                        "reviewer": "",
                        "updated_at": datetime.now(timezone.utc).date().isoformat(),
                    },
                )
                row["evidence_source"].append(evidence)
                row["evidence_context"].append(f"[{','.join(reasons)}] {text}")
                row["evidence_count"] += 1

    rows: list[dict[str, Any]] = []
    for row in occurrences.values():
        row["evidence_source"] = " | ".join(row["evidence_source"][:10])
        row["evidence_context"] = " | ".join(row["evidence_context"][:5])
        rows.append(row)
    return sorted(rows, key=lambda row: (-int(row["evidence_count"]), str(row["observed"])))


def parse_srt(path: Path) -> list[list[str]]:
    blocks = re.split(r"\r?\n\r?\n+", path.read_text(encoding="utf-8-sig").strip())
    return [block.splitlines() for block in blocks if block.strip()]


def apply_rules(raw_srt: Path, clean_srt: Path, audit_path: Path, approved: Path) -> int:
    rules = [row for row in load_rules(approved) if row.get("status") == "approved"]
    blocks = parse_srt(raw_srt)
    changes: list[dict[str, Any]] = []
    all_text = "\n".join(" ".join(block[2:]) for block in blocks if len(block) >= 3)

    for block_index, block in enumerate(blocks):
        if len(block) < 3:
            continue
        for line_index in range(2, len(block)):
            original = block[line_index]
            corrected = original
            context_start = max(0, block_index - 1)
            context_end = min(len(blocks), block_index + 2)
            context = " ".join(
                " ".join(item[2:]) for item in blocks[context_start:context_end] if len(item) >= 3
            )
            for rule in rules:
                canonical = (rule.get("canonical") or "").strip()
                context_regex = (rule.get("context_regex") or "").strip()
                if context_regex:
                    try:
                        if not re.search(context_regex, context):
                            continue
                    except re.error:
                        continue
                variants = [
                    value.strip()
                    for value in re.split(r"[|,，;；]", rule.get("variants") or "")
                    if value.strip()
                ]
                for variant in variants:
                    if variant in corrected:
                        corrected = corrected.replace(variant, canonical)
                        changes.append(
                            {
                                "block": block_index + 1,
                                "timestamp": block[1] if len(block) > 1 else "",
                                "before": variant,
                                "after": canonical,
                                "context": context,
                                "rule_evidence": rule.get("evidence"),
                            }
                        )
            block[line_index] = corrected

    clean_srt.parent.mkdir(parents=True, exist_ok=True)
    clean_srt.write_text(
        "\n\n".join("\n".join(block) for block in blocks) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    audit_path.write_text(
        json.dumps(
            {
                "raw_file": str(raw_srt),
                "clean_file": str(clean_srt),
                "applied_on": datetime.now(timezone.utc).isoformat(),
                "source_text_sha256_note": "Raw file is retained unchanged.",
                "changes": changes,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return len(changes)


def batch_apply(
    raw_srt_dir: Path,
    qc_dir: Path,
    clean_srt_dir: Path,
    audit_dir: Path,
    approved: Path,
) -> tuple[int, int]:
    """Create traceable clean copies for high/medium transcripts only."""
    processed = 0
    changes = 0
    for raw_srt in sorted(raw_srt_dir.glob("*.srt")):
        qc_path = qc_dir / f"{raw_srt.stem}.json"
        if not qc_path.exists():
            continue
        qc = json.loads(qc_path.read_text(encoding="utf-8-sig"))
        if qc.get("quality") not in {"high", "medium"}:
            continue
        changes += apply_rules(
            raw_srt,
            clean_srt_dir / raw_srt.name,
            audit_dir / f"{raw_srt.stem}.json",
            approved,
        )
        processed += 1
    return processed, changes


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    candidates = subparsers.add_parser("candidates")
    candidates.add_argument("--raw-json-dir", type=Path, required=True)
    candidates.add_argument(
        "--qc-dir",
        type=Path,
        required=True,
        help="Only high/medium transcript JSON with matching QC files is scanned",
    )
    candidates.add_argument("--approved", type=Path, required=True)
    candidates.add_argument("--output", type=Path, required=True)

    apply = subparsers.add_parser("apply")
    apply.add_argument("--raw-srt", type=Path, required=True)
    apply.add_argument("--clean-srt", type=Path, required=True)
    apply.add_argument("--audit", type=Path, required=True)
    apply.add_argument("--approved", type=Path, required=True)

    batch = subparsers.add_parser("batch-apply")
    batch.add_argument("--raw-srt-dir", type=Path, required=True)
    batch.add_argument("--qc-dir", type=Path, required=True)
    batch.add_argument("--clean-srt-dir", type=Path, required=True)
    batch.add_argument("--audit-dir", type=Path, required=True)
    batch.add_argument("--approved", type=Path, required=True)
    args = parser.parse_args()

    if args.command == "candidates":
        rows = scan_candidates(args.raw_json_dir, args.approved, args.qc_dir)
        write_tsv(args.output, rows)
        print(f"Wrote {len(rows)} candidates to {args.output}; none were auto-approved.")
        return 0

    if args.command == "apply":
        changes = apply_rules(args.raw_srt, args.clean_srt, args.audit, args.approved)
        print(f"Applied {changes} approved contextual replacements; raw SRT unchanged.")
        return 0

    processed, changes = batch_apply(
        args.raw_srt_dir,
        args.qc_dir,
        args.clean_srt_dir,
        args.audit_dir,
        args.approved,
    )
    print(
        f"Created {processed} clean transcripts with {changes} approved replacements; "
        "raw SRT files unchanged."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
