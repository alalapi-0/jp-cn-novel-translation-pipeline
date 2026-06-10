#!/usr/bin/env python3
"""Local scheduler single-tick CLI (FS-003, spec §9.1).

Usage:
    python3 scripts/local_scheduler_tick.py --dry-run          # human summary
    python3 scripts/local_scheduler_tick.py --dry-run --json   # full JSON

FS-003 ships the dry-run skeleton only; there is intentionally no real-API
flag yet (task planner: FS-004, real smoke: FS-007).

Exit codes: 0 completed or politely skipped, 1 error, 2 blocked.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from scheduler.tick import run_tick  # noqa: E402


def _human(result: dict) -> str:
    task = result.get("next_task") or {}
    lines = [
        f"tick={result['tick_id']} mode={result['mode']} status={result['status']}",
        f"task={task.get('task') or '-'}"
        f" round={task.get('round_id') or '-'}"
        f" range={task.get('chapter_range') or '-'}"
        f" phase={task.get('phase') or '-'}",
        f"blocked_reason={result.get('blocked_reason') or '-'}",
        f"report={result.get('report_path') or '-'}",
        f"exit_code={result['exit_code']}",
    ]
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one local scheduler tick")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="dry-run mode (the only mode in FS-003; always on)",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    # Hidden: lets tests point the tick at a fixture repo.
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args()

    result = run_tick(args.repo_root, dry_run=True)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(_human(result))
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
