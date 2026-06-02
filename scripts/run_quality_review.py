#!/usr/bin/env python3
"""Run deterministic quality review checkers on synthetic fixtures.

Read-only on human_edited segments: issues are reported, never applied.
No LLM, no .env, no real API. Exit: 0=OK with issues, 1=no issues, 2=validation error.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from quality_review.runner import (  # noqa: E402
    EXAMPLE_REPORT,
    DEFAULT_GLOSSARY,
    DEFAULT_SEGMENTS,
    SCHEMA_PATH,
    aggregate_exit_code,
    run_review,
    validate_report_dict,
    write_report,
)

DEFAULT_WORKSPACE_REPORT = REPO_ROOT / "workspace" / "review" / "issue_report.json"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Deterministic translation quality review")
    parser.add_argument(
        "--segments",
        type=Path,
        default=DEFAULT_SEGMENTS,
        help="Segments fixture JSON",
    )
    parser.add_argument(
        "--glossary",
        type=Path,
        default=DEFAULT_GLOSSARY,
        help="Glossary fixture JSON",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write report JSON (default: stdout only unless --write-example)",
    )
    parser.add_argument(
        "--write-example",
        action="store_true",
        help=f"Also write {EXAMPLE_REPORT.relative_to(REPO_ROOT)}",
    )
    parser.add_argument(
        "--workspace",
        action="store_true",
        help=f"Write {DEFAULT_WORKSPACE_REPORT.relative_to(REPO_ROOT)} (gitignored)",
    )
    parser.add_argument("--json", action="store_true", help="Print report JSON to stdout")
    args = parser.parse_args(argv)

    if not args.segments.is_file():
        print(f"missing segments fixture: {args.segments}", file=sys.stderr)
        return 2
    if not args.glossary.is_file():
        print(f"missing glossary fixture: {args.glossary}", file=sys.stderr)
        return 2
    if not SCHEMA_PATH.is_file():
        print(f"missing schema: {SCHEMA_PATH}", file=sys.stderr)
        return 2

    report = run_review(args.segments, args.glossary)
    payload = report.to_dict()
    errors = validate_report_dict(payload)
    exit_code = aggregate_exit_code(errors, len(report.issues))

    if args.write_example:
        write_report(report, EXAMPLE_REPORT)
    if args.workspace:
        write_report(report, DEFAULT_WORKSPACE_REPORT)
    if args.output:
        write_report(report, args.output)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        label = {0: "PASS", 1: "WARNING", 2: "BLOCKED"}[exit_code]
        print(f"quality_review: {label} (exit {exit_code})")
        print(f"issues={report.summary['total']} status={report.review_status}")
        for itype, count in sorted(report.summary["by_type"].items()):
            print(f"  {itype}: {count}")
        if errors:
            for err in errors:
                print(f"  error: {err}", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
