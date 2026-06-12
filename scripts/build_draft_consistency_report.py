#!/usr/bin/env python3
"""Build full draft consistency report (FS-037, Phase B).

Aggregates Level 0–5 artifacts into workspace/consistency_audit/draft_consistency_report.json.

Usage:
    python3 scripts/build_draft_consistency_report.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from consistency.draft_consistency_report import (  # noqa: E402
    build_draft_consistency_report,
    report_summary,
)

DEFAULT_OUTPUT = REPO_ROOT / "workspace" / "consistency_audit" / "draft_consistency_report.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build full draft consistency report (FS-037)")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    repo_root = args.repo_root if args.repo_root.is_absolute() else REPO_ROOT / args.repo_root
    output_path = args.output if args.output.is_absolute() else repo_root / args.output

    report = build_draft_consistency_report(repo_root)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    summary = {"output": str(output_path.relative_to(repo_root)), **report_summary(report)}
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"build_draft_consistency_report: {summary['status']} "
            f"blocking={summary['blocking_conflicts']} "
            f"retranslate_remaining={summary['retranslate_remaining']} "
            f"-> {summary['output']}"
        )
    return 0 if report.get("status") == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
