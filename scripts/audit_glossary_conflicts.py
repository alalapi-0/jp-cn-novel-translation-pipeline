#!/usr/bin/env python3
"""Audit glossary conflicts against entity index (FS-034, Level 2).

Compares entity index + glossary (and optional term usage index) for:
- locked / approved term violations (blocking)
- divergent_translation / shared_target (non-blocking)
- unlisted high-frequency source candidates (non-blocking)

Output: workspace/consistency_audit/glossary_conflict_audit.json (gitignored path).
Stdout: statistics only — never source/draft text.

Usage:
    python3 scripts/audit_glossary_conflicts.py --json
    python3 scripts/audit_glossary_conflicts.py --entity-index path/to/entity_index.json --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from consistency.conflict_audit import audit_glossary_conflicts, audit_summary  # noqa: E402
from glossary import GlossaryStore  # noqa: E402

DEFAULT_GLOSSARY = REPO_ROOT / "workspace" / "configs" / "glossary.yaml"
DEFAULT_ENTITY_INDEX = REPO_ROOT / "workspace" / "indexes" / "entity_index.json"
DEFAULT_TERM_USAGE_INDEX = REPO_ROOT / "workspace" / "indexes" / "term_usage_index.json"
DEFAULT_OUTPUT = REPO_ROOT / "workspace" / "consistency_audit" / "glossary_conflict_audit.json"


def _load_json(path: Path, label: str) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"audit_glossary_conflicts: invalid JSON in {label}: {path}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Audit glossary conflicts (stats only on stdout)"
    )
    parser.add_argument("--glossary", type=Path, default=DEFAULT_GLOSSARY)
    parser.add_argument("--entity-index", type=Path, default=DEFAULT_ENTITY_INDEX)
    parser.add_argument(
        "--term-usage-index",
        type=Path,
        default=None,
        help="Optional FS-015 index for locked/approved checks on non-entity categories",
    )
    parser.add_argument(
        "--skip-term-usage-index",
        action="store_true",
        help="Do not load term usage index even if present",
    )
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
    glossary_path = args.glossary if args.glossary.is_absolute() else repo_root / args.glossary
    entity_path = (
        args.entity_index if args.entity_index.is_absolute() else repo_root / args.entity_index
    )
    output_path = args.output if args.output.is_absolute() else repo_root / args.output

    if not glossary_path.is_file():
        print(f"audit_glossary_conflicts: FAIL glossary not found: {glossary_path}")
        return 2
    if not entity_path.is_file():
        print(f"audit_glossary_conflicts: FAIL entity index not found: {entity_path}")
        return 2

    term_usage_index = None
    if not args.skip_term_usage_index:
        usage_path = args.term_usage_index
        if usage_path is None:
            usage_path = DEFAULT_TERM_USAGE_INDEX
        elif not usage_path.is_absolute():
            usage_path = repo_root / usage_path
        if usage_path.is_file():
            term_usage_index = _load_json(usage_path, "term usage index")

    terms = GlossaryStore(glossary_path).entries()
    entity_index = _load_json(entity_path, "entity index")
    report = audit_glossary_conflicts(
        terms,
        entity_index,
        term_usage_index=term_usage_index,
    )

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
        kind_bits = " ".join(f"{k}={v}" for k, v in sorted(by_kind.items()))
        print(
            f"audit_glossary_conflicts: {summary['status']} "
            f"findings={summary['findings_total']} "
            f"blocking={summary['blocking_count']} "
            f"non_blocking={summary['non_blocking_count']} "
            f"({kind_bits}) -> {display_output}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
