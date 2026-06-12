#!/usr/bin/env python3
"""Audit draft structure: missing segments, misalignment, source residual, format (FS-035).

Integrates FS-032 segment index with kana-only source residual heuristics (P1 fix:
Chinese Han no longer triggers residual). Output: workspace/consistency_audit/
draft_structure_audit.json (gitignored path). Stdout: statistics only — never body text.

Usage:
    python3 scripts/audit_draft_structure.py --json
    python3 scripts/audit_draft_structure.py --segment-index path/to/segment_index.json --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from consistency.draft_structure_audit import audit_draft_structure, audit_summary  # noqa: E402

DEFAULT_SEGMENT_INDEX = REPO_ROOT / "workspace" / "indexes" / "segment_index.json"
DEFAULT_OUTPUT = REPO_ROOT / "workspace" / "consistency_audit" / "draft_structure_audit.json"


def _load_json(path: Path, label: str) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"audit_draft_structure: invalid JSON in {label}: {path}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit draft structure (stats only on stdout)"
    )
    parser.add_argument("--segment-index", type=Path, default=DEFAULT_SEGMENT_INDEX)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=REPO_ROOT,
        help="Repository root (default: script parent directory)",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable summary")
    args = parser.parse_args(argv)

    repo_root = args.repo_root if args.repo_root.is_absolute() else REPO_ROOT / args.repo_root
    index_path = (
        args.segment_index if args.segment_index.is_absolute() else repo_root / args.segment_index
    )
    output_path = args.output if args.output.is_absolute() else repo_root / args.output

    if not index_path.is_file():
        print(f"audit_draft_structure: FAIL segment index not found: {index_path}")
        return 2

    segment_index = _load_json(index_path, "segment index")
    report = audit_draft_structure(segment_index, repo_root)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        display_output = str(output_path.relative_to(repo_root))
    except ValueError:
        display_output = str(output_path)

    summary = {"output": display_output, **audit_summary(report)}
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        by_kind = summary.get("by_kind") or {}
        by_severity = summary.get("by_severity") or {}
        kind_bits = " ".join(f"{k}={v}" for k, v in sorted(by_kind.items()))
        sev_bits = " ".join(f"{k}={v}" for k, v in sorted(by_severity.items()))
        print(
            f"audit_draft_structure: {summary['status']} "
            f"findings={summary['findings_total']} "
            f"blocking={summary['blocking_count']} "
            f"non_blocking={summary['non_blocking_count']} "
            f"({kind_bits}) severity=({sev_bits}) -> {display_output}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
