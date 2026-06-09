#!/usr/bin/env python3
"""Validate micro_round_progress.json checkpoint shape (read-only)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

REQUIRED = ("schema_version", "run_id", "status", "updated_at")


def validate(doc: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED:
        if key not in doc:
            errors.append(f"missing {key}")
    progress = doc.get("progress")
    if progress is not None and not isinstance(progress, str):
        errors.append("progress must be string like N/M")
    budget = doc.get("budget")
    if budget is not None and not isinstance(budget, dict):
        errors.append("budget must be object")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate micro_round_progress.json")
    parser.add_argument("path", type=Path, nargs="?", help="Progress JSON path")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.path:
        path = args.path if args.path.is_absolute() else REPO_ROOT / args.path
    else:
        matches = list((REPO_ROOT / "workspace").glob("**/micro_round_progress.json"))
        if not matches:
            print("validate_micro_round_progress: SKIP (no files under workspace/)")
            return 0
        path = matches[0]
    if not path.is_file():
        print(f"validate_micro_round_progress: missing {path}", file=sys.stderr)
        return 2
    doc = json.loads(path.read_text(encoding="utf-8"))
    errors = validate(doc)
    payload = {"path": str(path), "valid": not errors, "errors": errors}
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif errors:
        for e in errors:
            print(f"  - {e}")
        return 1
    print("validate_micro_round_progress: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
