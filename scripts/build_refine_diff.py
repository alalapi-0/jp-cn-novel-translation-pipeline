#!/usr/bin/env python3
"""Legacy refine diff builder CLI (disabled by default).

Usage:
    python3 scripts/build_refine_diff.py --run-id micro_validate_refine_e2e --json
    python3 scripts/build_refine_diff.py --run-dir workspace/runs/run_xxx_refine_stage_c
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

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
    parser = argparse.ArgumentParser(description="Legacy refine diff + change_log (disabled by default)")
    parser.add_argument("--run-id", default="", help="Run id under workspace/runs/")
    parser.add_argument("--run-dir", type=Path, default=None, help="Explicit run directory")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--json", action="store_true", help="Print summary JSON to stdout")
    args = parser.parse_args(argv)

    if os.environ.get("ALLOW_LEGACY_REFINEMENT") != "1":
        payload = {
            "status": "blocked",
            "reason": "legacy_refinement_disabled",
            "message": (
                "build_refine_diff.py belongs to the deprecated refinement route. "
                "Use user revision / consistency diff tooling instead."
            ),
        }
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(payload["message"], file=sys.stderr)
        return 2

    repo_root = args.repo_root if args.repo_root.is_absolute() else REPO_ROOT / args.repo_root
    try:
        run_root = _resolve_run_root(repo_root, args.run_id.strip() or None, args.run_dir)
        summary = build_refine_diff_for_run(run_root)
    except FileNotFoundError as exc:
        payload = {"error": str(exc), "status": "missing_segments"}
        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(f"build_refine_diff: ERROR {exc}", file=sys.stderr)
        return 2

    rel_diff = Path(summary["diff_path"]).relative_to(repo_root)
    rel_log = Path(summary["change_log_path"]).relative_to(repo_root)
    summary["diff_output"] = str(rel_diff)
    summary["change_log_output"] = str(rel_log)
    summary["status"] = "ok"

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            "build_refine_diff: "
            f"run_id={summary['run_id']} "
            f"segments={summary['total_segments']} "
            f"changed={summary['changed_segments']} "
            f"avg_diff_ratio={summary['avg_diff_ratio']} "
            f"-> {rel_diff} + {rel_log}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
