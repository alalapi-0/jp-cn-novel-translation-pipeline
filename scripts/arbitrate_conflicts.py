#!/usr/bin/env python3
"""Model arbitration for rule-undecidable glossary conflicts (FS-037, Level 4).

Usage:
    python3 scripts/arbitrate_conflicts.py --dry-run --json
    python3 scripts/arbitrate_conflicts.py --real-api --max-api-calls 5 --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from consistency.arbitration import (  # noqa: E402
    DEFAULT_MAX_API_CALLS,
    arbitration_summary,
    run_arbitration,
    select_arbitration_candidates,
)
from providers.cost_guard import CostGuard, CostGuardConfig  # noqa: E402
from providers.fake_provider import FakeProvider  # noqa: E402
from providers.registry import ProviderMode, get_provider  # noqa: E402
from translation.run_progress import safe_load_json  # noqa: E402

DEFAULT_GLOSSARY_AUDIT_REL = Path("workspace") / "consistency_audit" / "glossary_conflict_audit.json"
DEFAULT_OUTPUT_REL = Path("workspace") / "consistency_audit" / "arbitration_report.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Arbitrate rule-undecidable glossary conflicts (FS-037)")
    parser.add_argument("--glossary-audit", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--max-api-calls", type=int, default=DEFAULT_MAX_API_CALLS)
    parser.add_argument("--dry-run", action="store_true", help="No API calls; emit placeholder decisions")
    parser.add_argument("--real-api", action="store_true", help="Use real provider (requires cost guard env)")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    repo_root = args.repo_root if args.repo_root.is_absolute() else REPO_ROOT / args.repo_root
    glossary_audit = args.glossary_audit or DEFAULT_GLOSSARY_AUDIT_REL
    audit_path = glossary_audit if glossary_audit.is_absolute() else repo_root / glossary_audit
    output = args.output or DEFAULT_OUTPUT_REL
    output_path = output if output.is_absolute() else repo_root / output

    if not audit_path.is_file():
        print(f"arbitrate_conflicts: FAIL glossary audit not found: {audit_path}")
        return 2

    glossary_audit = safe_load_json(audit_path) or {}
    candidates = select_arbitration_candidates(glossary_audit)

    if args.real_api and not args.dry_run:
        guard = CostGuard(
            CostGuardConfig.from_env(log_dir=repo_root / "workspace" / "model_runs"),
        )
        if not guard.allow_real_network():
            print("arbitrate_conflicts: FAIL real API not enabled (set REAL_API_TESTS_ENABLED=1)")
            return 2
        provider = get_provider(ProviderMode.REAL, cost_guard=guard)
    else:
        guard = CostGuard(CostGuardConfig.from_env(log_dir=repo_root / "workspace" / "model_runs"))
        provider = FakeProvider(cost_guard=guard)

    report = run_arbitration(
        candidates,
        provider=provider,
        max_api_calls=args.max_api_calls,
        dry_run=args.dry_run or not args.real_api,
    )
    if args.real_api and not args.dry_run:
        report["dry_run"] = False

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        display_output = str(output_path.relative_to(repo_root))
    except ValueError:
        display_output = str(output_path)
    summary = {"output": display_output, **arbitration_summary(report)}
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"arbitrate_conflicts: {summary['status']} "
            f"candidates={summary['candidate_count']} "
            f"api_calls={summary['api_calls']}/{summary['max_api_calls']} "
            f"-> {summary['output']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
