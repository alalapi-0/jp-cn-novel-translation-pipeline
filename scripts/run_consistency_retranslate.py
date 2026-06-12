#!/usr/bin/env python3
"""Execute localized segment retranslation from local fix plan (FS-037, Level 5).

Batched with checkpoint/resume and cost guard. Default dry-run; use --real-api
with --max-api-calls for production pilot batches.

Usage:
    python3 scripts/run_consistency_retranslate.py --dry-run --limit 20 --json
    python3 scripts/run_consistency_retranslate.py --real-api --max-api-calls 10 --limit 20 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from consistency.retranslate import (  # noqa: E402
    DEFAULT_CHECKPOINT_REL,
    DEFAULT_MAX_SEGMENTS_PER_CALL,
    build_fix_plan_status,
    run_consistency_retranslate,
)
from providers.cost_guard import CostGuard, CostGuardConfig  # noqa: E402
from providers.fake_provider import FakeProvider  # noqa: E402
from providers.registry import ProviderMode, get_provider  # noqa: E402
from translation.run_progress import safe_load_json  # noqa: E402

DEFAULT_FIX_PLAN = REPO_ROOT / "workspace" / "consistency_audit" / "local_fix_plan.json"
DEFAULT_STATUS = REPO_ROOT / "workspace" / "consistency_audit" / "fix_plan_status.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Localized consistency retranslate (FS-037)")
    parser.add_argument("--fix-plan", type=Path, default=DEFAULT_FIX_PLAN)
    parser.add_argument("--checkpoint", type=Path, default=None)
    parser.add_argument("--status-output", type=Path, default=DEFAULT_STATUS)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--max-api-calls", type=int, default=0)
    parser.add_argument("--max-segments", type=int, default=DEFAULT_MAX_SEGMENTS_PER_CALL)
    parser.add_argument("--limit", type=int, default=0, help="Pilot cap: process at most N pending segments")
    parser.add_argument("--dry-run", action="store_true", help="Simulate without API or disk writes to drafts")
    parser.add_argument("--real-api", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    repo_root = args.repo_root if args.repo_root.is_absolute() else REPO_ROOT / args.repo_root
    plan_path = args.fix_plan if args.fix_plan.is_absolute() else repo_root / args.fix_plan
    cp_path = args.checkpoint or (repo_root / DEFAULT_CHECKPOINT_REL)
    status_path = args.status_output if args.status_output.is_absolute() else repo_root / args.status_output

    if not plan_path.is_file():
        print(f"run_consistency_retranslate: FAIL fix plan not found: {plan_path}")
        return 2

    plan = safe_load_json(plan_path) or {}
    dry_run = args.dry_run or not args.real_api

    if args.real_api and not dry_run:
        guard = CostGuard(CostGuardConfig.from_env(log_dir=repo_root / "workspace" / "model_runs"))
        if not guard.allow_real_network():
            print("run_consistency_retranslate: FAIL real API not enabled (set REAL_API_TESTS_ENABLED=1)")
            return 2
        if int(args.max_api_calls or 0) <= 0:
            print("run_consistency_retranslate: FAIL --real-api requires --max-api-calls > 0")
            return 2
        provider = get_provider(ProviderMode.REAL, cost_guard=guard)
    else:
        guard = CostGuard(CostGuardConfig.from_env(log_dir=repo_root / "workspace" / "model_runs"))
        provider = FakeProvider(cost_guard=guard)

    result = run_consistency_retranslate(
        plan,
        repo_root,
        provider=provider,
        max_api_calls=args.max_api_calls,
        max_segments=args.max_segments,
        limit=args.limit,
        dry_run=dry_run,
        checkpoint_path=cp_path,
    )
    fix_status = build_fix_plan_status(plan, result)
    status_path.parent.mkdir(parents=True, exist_ok=True)
    status_path.write_text(json.dumps(fix_status, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {
        "fix_plan_status": str(status_path.relative_to(repo_root)),
        **result,
    }
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"run_consistency_retranslate: status={result['status']} "
            f"completed={result['completed_segments']}/{result['total_segments']} "
            f"api_calls={result['api_calls']} dry_run={result['dry_run']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
