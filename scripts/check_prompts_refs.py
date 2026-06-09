#!/usr/bin/env python3
"""Verify docs/PROMPTS.md references exist in the repo (dry-run)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PROMPTS = REPO_ROOT / "docs" / "PROMPTS.md"

REF_PATTERN = re.compile(
    r"(?:Read first:|Read:|see )[`']?(docs/[\w./_-]+|AGENTS\.md|agent_[\w.]+\.yaml|reports/[\w./_-]+|scripts/[\w./_-]+)[`']?",
    re.I,
)
BACKTICK = re.compile(r"`(docs/[\w./_-]+|AGENTS\.md|agent_[\w.]+\.yaml|reports/[\w./_-]+|scripts/[\w./_-]+)`")


def extract_refs(text: str) -> set[str]:
    refs: set[str] = set()
    for pat in (REF_PATTERN, BACKTICK):
        refs.update(pat.findall(text))
    return refs


def main() -> int:
    if not PROMPTS.is_file():
        print("check_prompts_refs: missing docs/PROMPTS.md", file=sys.stderr)
        return 2
    text = PROMPTS.read_text(encoding="utf-8")
    missing: list[str] = []
    for ref in sorted(extract_refs(text)):
        path = REPO_ROOT / ref
        if not path.exists():
            missing.append(ref)
    if missing:
        print("check_prompts_refs: FAIL")
        for m in missing:
            print(f"  missing: {m}")
        return 1
    print(f"check_prompts_refs: PASS ({len(extract_refs(text))} refs)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
