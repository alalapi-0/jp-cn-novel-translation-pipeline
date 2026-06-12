#!/usr/bin/env python3
"""Apply deterministic term fixes from local fix plan (FS-036).

Dry-run (default) prints per-segment unified diffs without writing files.
Apply mode updates draft_text in segments.json only — never source text or
run checkpoint / progress files.

Usage:
    python3 scripts/apply_term_fixes.py --dry-run
    python3 scripts/apply_term_fixes.py --plan path/to/local_fix_plan.json --apply
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from consistency.local_fix_plan import apply_term_fixes  # noqa: E402

DEFAULT_PLAN = REPO_ROOT / "workspace" / "consistency_audit" / "local_fix_plan.json"


def _load_json(path: Path, label: str) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"apply_term_fixes: invalid JSON in {label}: {path}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Apply term fixes from local fix plan")
    parser.add_argument("--plan", type=Path, default=DEFAULT_PLAN)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root (default: script parent directory)",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", default=True, help="Preview diffs only (default)")
    mode.add_argument("--apply", action="store_true", help="Write draft_text patches to segments.json")
    parser.add_argument("--json", action="store_true", help="Print machine-readable result")
    args = parser.parse_args(argv)

    repo_root = args.repo_root if args.repo_root.is_absolute() else REPO_ROOT / args.repo_root
    plan_path = args.plan if args.plan.is_absolute() else repo_root / args.plan

    if not plan_path.is_file():
        print(f"apply_term_fixes: FAIL plan not found: {plan_path}")
        return 2

    plan = _load_json(plan_path, "fix plan")
    dry_run = not args.apply
    result = apply_term_fixes(plan, repo_root, dry_run=dry_run)

    if args.json:
        payload = {
            "dry_run": dry_run,
            "applied_count": result["applied_count"],
            "skipped_count": result["skipped_count"],
            "modified_files": result["modified_files"],
            "previews": [
                {
                    "segment_id": p["segment_id"],
                    "changed": p["changed"],
                    "missing": p.get("missing", False),
                    "diff": p.get("diff", ""),
                }
                for p in result.get("previews") or []
                if p.get("changed")
            ],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"apply_term_fixes: {'DRY_RUN' if dry_run else 'APPLIED'} "
            f"applied={result['applied_count']} skipped={result['skipped_count']}"
        )
        for preview in result.get("previews") or []:
            if preview.get("changed") and preview.get("diff"):
                print(preview["diff"])

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
