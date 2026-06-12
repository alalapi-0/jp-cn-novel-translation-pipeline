#!/usr/bin/env python3
"""Lock draft baseline snapshot + metadata (FS-038)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from translation.baseline_lock import lock_baseline  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Lock draft_full_baseline snapshot (FS-038)")
    parser.add_argument("--dry-run", action="store_true", help="Validate and plan without writing")
    parser.add_argument("--force", action="store_true", help="Re-lock even if metadata shows locked")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args()

    try:
        result = lock_baseline(args.repo_root, dry_run=args.dry_run, force=args.force)
    except RuntimeError as exc:
        payload = {"status": "rejected", "error": str(exc)}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"lock_baseline: REJECTED — {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"lock_baseline: {result['status']} "
            f"chapters={result['chapter_count']} "
            f"aggregate={result['aggregate_hash'][:16]}..."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
