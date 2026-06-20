#!/usr/bin/env python3
"""Legacy Phase D refinement quality checkers (disabled by default).

Three deterministic checkers (no LLM, no real API):
  - over_refinement (FS-042 change_log diff_ratio / length expansion)
  - terminology_preservation (locked glossary terms)
  - character_voice (character_profile markers)

Exit codes: 0=pass (no blocking), 2=blocking or validation error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from refinement.checkers import (  # noqa: E402
    aggregate_exit_code,
    run_refinement_checks,
    run_refinement_checks_for_run,
    write_refinement_quality_report,
)
from refinement.diff_builder import build_refine_diff_for_run  # noqa: E402

DEFAULT_RUNS_ROOT = REPO_ROOT / "workspace" / "runs"


def _resolve_run_root(repo_root: Path, run_id: str | None, run_dir: Path | None) -> Path:
    if run_dir is not None:
        path = run_dir if run_dir.is_absolute() else repo_root / run_dir
        return path.resolve()
    if not run_id:
        raise ValueError("provide --run-id or --run-dir")
    return (repo_root / "workspace" / "runs" / run_id).resolve()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Legacy refinement quality checkers (disabled by default)")
    parser.add_argument("--run-id", default="", help="Run id under workspace/runs/")
    parser.add_argument("--run-dir", type=Path, default=None, help="Explicit run directory")
    parser.add_argument(
        "--segments",
        type=Path,
        default=None,
        help="segments.json fixture (instead of --run-dir)",
    )
    parser.add_argument("--glossary", type=Path, default=None, help="Glossary YAML override")
    parser.add_argument(
        "--character-profile",
        type=Path,
        default=None,
        help="character_profile.yaml override",
    )
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument(
        "--build-diff",
        action="store_true",
        help="Ensure change_log exists via build_refine_diff before checking",
    )
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write refinement_quality_report.json into run directory",
    )
    parser.add_argument("--json", action="store_true", help="Print report JSON to stdout")
    args = parser.parse_args(argv)

    if os.environ.get("ALLOW_LEGACY_REFINEMENT") != "1":
        payload = {
            "status": "blocked",
            "reason": "legacy_refinement_disabled",
            "message": (
                "check_refinement_quality.py belongs to the deprecated refinement route. "
                "Use docs/translation_consistency_protocol.md for current consistency checks."
            ),
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(payload["message"], file=sys.stderr)
        return 2

    repo_root = args.repo_root if args.repo_root.is_absolute() else REPO_ROOT / args.repo_root

    try:
        if args.segments is not None:
            seg_path = args.segments if args.segments.is_absolute() else repo_root / args.segments
            if not seg_path.is_file():
                raise FileNotFoundError(f"segments fixture not found: {seg_path}")
            segments_doc = json.loads(seg_path.read_text(encoding="utf-8"))
            glossary = args.glossary
            if glossary and not glossary.is_absolute():
                glossary = repo_root / glossary
            character = args.character_profile
            if character and not character.is_absolute():
                character = repo_root / character
            report = run_refinement_checks(
                segments_doc,
                glossary_path=glossary,
                character_path=character,
            )
        else:
            run_root = _resolve_run_root(repo_root, args.run_id.strip() or None, args.run_dir)
            if args.build_diff or not (run_root / "change_log.json").is_file():
                build_refine_diff_for_run(run_root)
            glossary = args.glossary
            if glossary and not glossary.is_absolute():
                glossary = repo_root / glossary
            character = args.character_profile
            if character and not character.is_absolute():
                character = repo_root / character
            report = run_refinement_checks_for_run(
                run_root,
                repo_root=repo_root,
                glossary_path=glossary,
                character_path=character,
            )
            if args.write_report:
                out_path = write_refinement_quality_report(run_root, report)
                report.stats["report_path"] = str(out_path)
    except (FileNotFoundError, ValueError) as exc:
        payload = {"error": str(exc), "status": "error"}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"check_refinement_quality: ERROR {exc}", file=sys.stderr)
        return 2

    exit_code = aggregate_exit_code(report)
    payload = report.to_dict()
    payload["exit_code"] = exit_code

    if args.write_report and "report_path" in report.stats:
        rel = Path(report.stats["report_path"])
        try:
            payload["report_output"] = str(rel.relative_to(repo_root))
        except ValueError:
            payload["report_output"] = str(rel)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        label = {0: "PASS", 2: "BLOCKING"}[exit_code]
        print(f"check_refinement_quality: {label} status={report.status}")
        print(
            f"blocking={report.blocking_count} warning={report.warning_count} "
            f"run_id={report.run_id or 'fixture'}"
        )
        for checker in report.checkers:
            print(f"  {checker.checker}: {checker.status} (checked={checker.segments_checked})")

    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
