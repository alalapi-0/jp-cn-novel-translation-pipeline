#!/usr/bin/env python3
"""Validate segment JSON chapter bounds and expected_segment_ids alignment."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_FIXTURE = REPO_ROOT / "data" / "examples" / "review_segments.fixture.json"


def validate_segments(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    chapter_id = doc.get("chapter_id")
    if not chapter_id:
        errors.append("missing chapter_id")
    expected = doc.get("expected_segment_ids")
    if not isinstance(expected, list):
        errors.append("expected_segment_ids must be a list")
        expected = []
    seen: set[str] = set()
    for para in doc.get("paragraphs") or []:
        if not isinstance(para, dict):
            errors.append("paragraph entry must be object")
            continue
        for seg in para.get("segments") or []:
            if not isinstance(seg, dict):
                errors.append("segment entry must be object")
                continue
            sid = seg.get("segment_id")
            if not sid:
                errors.append("segment missing segment_id")
                continue
            if sid in seen:
                errors.append(f"duplicate segment_id: {sid}")
            seen.add(str(sid))
    missing = [e for e in expected if e not in seen]
    extra = [s for s in seen if expected and s not in expected]
    if missing:
        errors.append(f"missing expected segments: {missing}")
    if extra:
        errors.append(f"unexpected segments not in expected_segment_ids: {extra}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Chapter/segment integrity check")
    parser.add_argument("--segments", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    path = args.segments if args.segments.is_absolute() else REPO_ROOT / args.segments
    if not path.is_file():
        print(f"check_chapter_integrity: missing {path}", file=sys.stderr)
        return 2
    doc = json.loads(path.read_text(encoding="utf-8"))
    errors = validate_segments(doc)
    payload = {"path": str(path.relative_to(REPO_ROOT)), "valid": not errors, "errors": errors}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif errors:
        print("check_chapter_integrity: FAIL")
        for e in errors:
            print(f"  - {e}")
        return 1
    print("check_chapter_integrity: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
