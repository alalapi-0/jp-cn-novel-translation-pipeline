#!/usr/bin/env python3
"""Local scheduler single-tick CLI (FS-003/FS-004/FS-007, spec §9.1).

Usage:
    python3 scripts/local_scheduler_tick.py --dry-run            # default mode
    python3 scripts/local_scheduler_tick.py --dry-run --json     # full JSON
    python3 scripts/local_scheduler_tick.py --real-api --max-api-calls 5

Real mode requires an explicit positive --max-api-calls budget; pause file,
lock, orphan checks, throughput gate and cost guard all still apply.

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
    plan = result.get("plan") or {}
    execution = result.get("execution") or {}
    lines = [
        f"tick={result['tick_id']} mode={result['mode']} status={result['status']}",
        f"task={task.get('task') or '-'}"
        f" round={task.get('round_id') or '-'}"
        f" range={task.get('chapter_range') or '-'}"
        f" phase={task.get('phase') or '-'}",
        f"plan={plan.get('task_type') or '-'}"
        f" implemented={plan.get('implemented')}"
        f" plan_round={plan.get('round_id') or '-'}"
        f" plan_range={plan.get('chapter_range') or '-'}",
    ]
    if plan.get("command"):
        lines.append("command=" + " ".join(plan["command"]))
    if execution.get("not_implemented"):
        lines.append(f"execution=not_implemented ({execution.get('reason')})")
    elif execution:
        lines.append(f"execution=rc:{execution.get('returncode')}")
    lines.extend(
        [
            f"blocked_reason={result.get('blocked_reason') or '-'}",
            f"report={result.get('report_path') or '-'}",
            f"exit_code={result['exit_code']}",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one local scheduler tick")
    mode_group = parser.add_mutually_exclusive_group()
    mode_group.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="dry-run mode (default): plan + run_micro_round --dry-run, no API",
    )
    mode_group.add_argument(
        "--real-api",
        action="store_true",
        help="real mode (FS-007): requires --max-api-calls > 0",
    )
    parser.add_argument("--json", action="store_true", help="emit JSON")
    # Budget pass-through to the planned task command line.
    parser.add_argument("--max-api-calls", type=int, default=None)
    parser.add_argument("--max-segments", type=int, default=None)
    parser.add_argument("--max-wall-time-minutes", type=float, default=None)
    parser.add_argument("--batch-token-budget", type=int, default=None)
    parser.add_argument("--max-segments-per-call", type=int, default=None)
    # Hidden: lets tests point the tick at a fixture repo.
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT, help=argparse.SUPPRESS)
    args = parser.parse_args()

    budgets = {
        key: value
        for key, value in {
            "max_api_calls": args.max_api_calls,
            "max_segments": args.max_segments,
            "max_wall_time_minutes": args.max_wall_time_minutes,
            "batch_token_budget": args.batch_token_budget,
            "max_segments_per_call": args.max_segments_per_call,
        }.items()
        if value is not None
    }
    dry_run = not args.real_api
    if not dry_run and int(budgets.get("max_api_calls") or 0) <= 0:
        parser.error("--real-api requires --max-api-calls > 0")
    result = run_tick(args.repo_root, dry_run=dry_run, budgets=budgets)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(_human(result))
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
