#!/usr/bin/env python3
"""Build local fix plan from FS-034 / FS-035 audit outputs (FS-036).

Aggregates glossary conflict audit + draft structure audit into term patches,
segment retranslate tasks, and deferred items. Output:
workspace/consistency_audit/local_fix_plan.json (gitignored).

Usage:
    python3 scripts/build_local_fix_plan.py --json
    python3 scripts/build_local_fix_plan.py \\
        --glossary-audit path/to/glossary_conflict_audit.json \\
        --structure-audit path/to/draft_structure_audit.json --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from consistency.local_fix_plan import build_local_fix_plan, plan_summary  # noqa: E402

DEFAULT_GLOSSARY_AUDIT = REPO_ROOT / "workspace" / "consistency_audit" / "glossary_conflict_audit.json"
DEFAULT_STRUCTURE_AUDIT = REPO_ROOT / "workspace" / "consistency_audit" / "draft_structure_audit.json"
DEFAULT_OUTPUT = REPO_ROOT / "workspace" / "consistency_audit" / "local_fix_plan.json"


def _load_json(path: Path, label: str) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"build_local_fix_plan: invalid JSON in {label}: {path}") from exc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build local fix plan (FS-036)")
    parser.add_argument("--glossary-audit", type=Path, default=DEFAULT_GLOSSARY_AUDIT)
    parser.add_argument("--structure-audit", type=Path, default=DEFAULT_STRUCTURE_AUDIT)
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
    glossary_path = (
        args.glossary_audit if args.glossary_audit.is_absolute() else repo_root / args.glossary_audit
    )
    structure_path = (
        args.structure_audit if args.structure_audit.is_absolute() else repo_root / args.structure_audit
    )
    output_path = args.output if args.output.is_absolute() else repo_root / args.output

    if not glossary_path.is_file():
        print(f"build_local_fix_plan: FAIL glossary audit not found: {glossary_path}")
        return 2
    if not structure_path.is_file():
        print(f"build_local_fix_plan: FAIL structure audit not found: {structure_path}")
        return 2

    glossary_audit = _load_json(glossary_path, "glossary audit")
    structure_audit = _load_json(structure_path, "structure audit")
    plan = build_local_fix_plan(glossary_audit, structure_audit)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    try:
        display_output = str(output_path.relative_to(repo_root))
    except ValueError:
        display_output = str(output_path)

    summary = {"output": display_output, **plan_summary(plan)}
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        cat = summary.get("categorization") or {}
        print(
            f"build_local_fix_plan: {summary['status']} "
            f"term_fixes={summary['term_fix_count']} "
            f"retranslate_tasks={summary['retranslate_task_count']} "
            f"deferred={summary['deferred_count']} "
            f"retranslate_segments={summary['retranslate_segment_count']} "
            f"term_replace={cat.get('term_replace')} "
            f"retranslate={cat.get('segment_retranslate')} "
            f"-> {display_output}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
