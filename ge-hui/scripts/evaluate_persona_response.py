#!/usr/bin/env python3
"""Run deterministic surface checks for a stored persona regression case."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


STORY_CUES = (
    "我跟你讲",
    "我告诉你",
    "我给你讲",
    "有一个",
    "有个",
    "有一次",
    "当时",
    "后来",
    "结果",
    "传说",
    "故事",
)
CLASSROOM_MARKERS = ("还明白", "对不对", "知道吧", "懂不懂", "是不是", "听懂")
RETURN_CUES = ("这个故事说明", "再回到", "回到佛", "绕了一圈", "还是这个道理", "说明什么")
TRUTH_LABELS = ("传说", "佛教故事", "民间说法", "有个说法", "玄一点", "按这个说法", "课堂里")


def load_case(path: Path, case_id: str) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    cases = payload if isinstance(payload, list) else payload.get("cases", [])
    for case in cases:
        if case.get("id") == case_id:
            return case
    raise ValueError(f"Unknown case: {case_id}")


def story_branch_count(text: str, story_terms: list[str]) -> int:
    paragraphs = [value.strip() for value in re.split(r"\n\s*\n", text) if value.strip()]
    return sum(
        any(cue in paragraph for cue in STORY_CUES)
        and any(term in paragraph for term in story_terms)
        for paragraph in paragraphs
    )


def evaluate_response(text: str, case: dict[str, Any]) -> dict[str, Any]:
    story_terms = [str(value) for value in case.get("story_terms", [])]
    doctrine_terms = [str(value) for value in case.get("doctrine_terms", [])]
    branches = story_branch_count(text, story_terms)
    classroom_markers = sum(text.count(marker) for marker in CLASSROOM_MARKERS)
    doctrine_hits = sum(term in text for term in doctrine_terms)
    return_hits = sum(cue in text for cue in RETURN_CUES)
    needs_truth_label = any(term in text for term in case.get("claim_label_terms", []))
    has_truth_label = any(label in text for label in TRUTH_LABELS)
    checks = {
        "minimum_characters": len(re.sub(r"\s+", "", text)) >= int(case.get("minimum_characters", 0)),
        "minimum_story_branches": branches >= int(case.get("minimum_story_branches", 0)),
        "minimum_classroom_markers": classroom_markers >= int(case.get("minimum_classroom_markers", 0)),
        "minimum_doctrine_terms": doctrine_hits >= int(case.get("minimum_doctrine_terms", 0)),
        "explicit_story_return": return_hits >= int(case.get("minimum_return_cues", 0)),
        "truth_label_when_needed": (not needs_truth_label) or has_truth_label,
    }
    return {
        "case_id": case.get("id"),
        "passed": all(checks.values()),
        "checks": checks,
        "observed": {
            "characters": len(re.sub(r"\s+", "", text)),
            "story_branches": branches,
            "classroom_markers": classroom_markers,
            "doctrine_terms": doctrine_hits,
            "return_cues": return_hits,
            "truth_label_present": has_truth_label,
        },
        "note": "Surface regression only; human review still judges relevance, factual boundaries, and naturalness.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--case-id", required=True)
    parser.add_argument("--response", type=Path, required=True)
    args = parser.parse_args()
    case = load_case(args.cases, args.case_id)
    text = args.response.read_text(encoding="utf-8-sig")
    report = evaluate_response(text, case)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
