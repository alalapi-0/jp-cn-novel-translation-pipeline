#!/usr/bin/env python3
"""Run one 20-chapter translation recovery round (Phase A draft)."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from local_env import apply_local_env  # noqa: E402

ROUND_PLAN: dict[str, dict[str, object]] = {
    "T-001": {
        "offset": 170,
        "limit": 20,
        "resume_run_id": "run_20260607_040204_draft_stage_b_50ch",
    },
    "T-002": {
        "offset": 190,
        "limit": 20,
        "resume_run_id": "",
    },
}

DEFAULT_ASSET = "workspace/assets/translation_memory/pw-user-assets-flow.json"


def _python() -> str:
    venv = REPO_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


def _run(cmd: list[str]) -> int:
    print("+", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=REPO_ROOT).returncode


def main() -> int:
    parser = argparse.ArgumentParser(description="Run 20-chapter translation recovery round")
    parser.add_argument("--round-id", default="T-001")
    parser.add_argument("--phase", choices=["draft"], default="draft")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--skip-gate", action="store_true")
    parser.add_argument("--skip-heal", action="store_true")
    args = parser.parse_args()
    apply_local_env(REPO_ROOT)

    plan = ROUND_PLAN.get(args.round_id)
    if not plan:
        print(f"unknown round_id={args.round_id}; extend ROUND_PLAN in script", file=sys.stderr)
        return 2

    py = _python()

    if not args.skip_heal:
        _run([py, "scripts/pipeline_worker_registry.py", "--heal", "--json"])

    if not args.skip_gate:
        gate = subprocess.run(
            [py, "scripts/throughput_gate.py", "--json"],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
        )
        if gate.stdout.strip():
            doc = json.loads(gate.stdout)
            print(f"throughput_gate: {doc.get('decision')}")
            if doc.get("decision") == "BLOCK":
                for step in doc.get("fix_paths") or []:
                    print(f"  → {step}")
                return 2
            if doc.get("active_worker_count", 0) > 0:
                print("BLOCK: active workers present", file=sys.stderr)
                return 2

    offset = int(plan["offset"])
    limit = int(plan["limit"])
    run_id = str(plan.get("resume_run_id") or "").strip()

    if args.dry_run:
        print(
            json.dumps(
                {
                    "dry_run": True,
                    "round_id": args.round_id,
                    "offset": offset,
                    "limit": limit,
                    "run_id": run_id or "(new)",
                },
                indent=2,
            )
        )
        return 0

    resume_cmd = [
        py,
        "scripts/resume_production.py",
        "--chapter-offset",
        str(offset),
        "--target-new-chapters",
        str(limit),
    ]
    if run_id:
        resume_cmd.extend(["--run-id", run_id, "--hydrate-apply"])
    else:
        resume_cmd.append("--new-run")

    env = os.environ.copy()
    env["REAL_API_TESTS_ENABLED"] = "1"
    env["CONTROLLED_RUN_ENABLED"] = "1"
    print("+", " ".join(resume_cmd), flush=True)
    rc = subprocess.run(resume_cmd, cwd=REPO_ROOT, env=env).returncode
    if rc != 0:
        return rc

    report_rc = _run(
        [
            py,
            "scripts/generate_translation_round_report.py",
            "--round-id",
            args.round_id,
            *(["--run-id", run_id] if run_id else []),
        ]
    )
    return 0 if report_rc == 0 else report_rc


if __name__ == "__main__":
    raise SystemExit(main())
