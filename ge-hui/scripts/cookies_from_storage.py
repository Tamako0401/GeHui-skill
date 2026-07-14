#!/usr/bin/env python3
"""Export only Douyin cookies from Playwright storage state to Netscape format."""

from __future__ import annotations

import argparse
import json
import os
import tempfile
from pathlib import Path


ALLOWED_DOMAINS = ("douyin.com", ".douyin.com")


def is_douyin_domain(domain: str) -> bool:
    value = domain.lower().lstrip(".")
    return value == "douyin.com" or value.endswith(".douyin.com")


def netscape_lines(storage: dict) -> list[str]:
    lines = ["# Netscape HTTP Cookie File", "# Exported from Playwright; Douyin only."]
    for cookie in storage.get("cookies", []):
        domain = str(cookie.get("domain", ""))
        if not is_douyin_domain(domain):
            continue
        http_only = bool(cookie.get("httpOnly", False))
        output_domain = f"#HttpOnly_{domain}" if http_only else domain
        include_subdomains = "TRUE" if domain.startswith(".") else "FALSE"
        path = str(cookie.get("path") or "/")
        secure = "TRUE" if cookie.get("secure") else "FALSE"
        expires_value = cookie.get("expires", 0)
        try:
            expires = int(float(expires_value)) if float(expires_value) > 0 else 0
        except (TypeError, ValueError):
            expires = 0
        name = str(cookie.get("name", "")).replace("\t", "")
        value = str(cookie.get("value", "")).replace("\t", "")
        if not name:
            continue
        lines.append(
            "\t".join(
                [output_domain, include_subdomains, path, secure, str(expires), name, value]
            )
        )
    return lines


def write_private(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", newline="\n", delete=False, dir=path.parent
    ) as handle:
        handle.write(text)
        temp_name = handle.name
    os.replace(temp_name, path)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("storage_state", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()

    storage = json.loads(args.storage_state.read_text(encoding="utf-8"))
    lines = netscape_lines(storage)
    cookie_count = max(0, len(lines) - 2)
    if not cookie_count:
        parser.error("Storage state contains no Douyin-domain cookies")
    write_private(args.output, "\n".join(lines) + "\n")
    print(f"Exported {cookie_count} Douyin cookies to {args.output}; values were not logged.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
