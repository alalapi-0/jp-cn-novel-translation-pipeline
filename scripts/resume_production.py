#!/usr/bin/env python3
"""Controlled production resume: gate check → optional hydrate → translate Stage B."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from local_env import apply_local_env  # noqa: E402
from translation.run_progress import PRODUCTION_STAGE_STATE_REL  # noqa: E402

DEFAULT_ASSET_CONTEXT = "workspace/assets/translation_memory/pw-user-assets-flow.json"
DEFAULT_RESUME_RUN = "run_20260605_111734_draft_stage_b_50ch"
DEFAULT_OFFSET = 150


def _python() -> str:
    venv = REPO_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


def _run(
    cmd: list[str],
    *,
    check: bool = True,
    capture: bool = False,
    with_production_env: bool = False,
) -> subprocess.CompletedProcess[str]:
    print("+", " ".join(cmd), flush=True)
    kwargs: dict = {
        "cwd": REPO_ROOT,
        "check": check,
        "text": True,
        "capture_output": capture,
    }
    if with_production_env:
        kwargs["env"] = _production_env()
    return subprocess.run(cmd, **kwargs)


def _production_env() -> dict[str, str]:
    """Align with production_pipeline.sh for controlled real-API resume."""
    env = os.environ.copy()
    env["REAL_API_TESTS_ENABLED"] = "1"
    env["CONTROLLED_RUN_ENABLED"] = "1"
    return env


def _ensure_production_env() -> None:
    for key, value in _production_env().items():
        if key in ("REAL_API_TESTS_ENABLED", "CONTROLLED_RUN_ENABLED"):
            os.environ[key] = value


def _run_gate_json(py: str) -> dict:
    gate = _run([py, "scripts/throughput_gate.py", "--json"], check=False, capture=True)
    raw = gate.stdout or ""
    if not raw.strip():
        err = (gate.stderr or "").strip()
        raise json.JSONDecodeError(
            f"empty gate stdout (exit {gate.returncode})" + (f": {err}" if err else ""),
            raw,
            0,
        )
    return json.loads(raw)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resume production draft translation with gate + hydrate safeguards",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例（从第 151 章续跑 20 章）::

  python3 scripts/resume_production.py \\
    --run-id run_20260605_111734_draft_stage_b_50ch \\
    --chapter-offset 150 \\
    --target-new-chapters 20 \\
    --hydrate-apply

续跑后精修 Stage C（151–170，需 gate ALLOW 且用户授权预算）::

  python3 scripts/resume_production.py --refine --run-id <run_id>

环境要求: .env 中 OPENROUTER_API_KEY 非空、REAL_API_TESTS_ENABLED=true、MAX_TEST_COST_USD>0
        """,
    )
    parser.add_argument("--run-id", default=DEFAULT_RESUME_RUN)
    parser.add_argument("--chapter-offset", type=int, default=DEFAULT_OFFSET)
    parser.add_argument(
        "--target-new-chapters",
        type=int,
        default=20,
        help="Chapter batch size for this resume (maps to translate --limit-chapters; 恢复推进默认 20 章/轮)",
    )
    parser.add_argument("--asset-context", type=Path, default=Path(DEFAULT_ASSET_CONTEXT))
    parser.add_argument("--no-hydrate", action="store_true", help="Skip hydrate_checkpoint (default: run hydrate)")
    parser.add_argument("--hydrate-apply", action="store_true", help="Pass --apply to hydrate_checkpoint")
    parser.add_argument("--skip-gate", action="store_true", help="Skip throughput_gate (not recommended)")
    parser.add_argument(
        "--refine",
        action="store_true",
        help="Run Stage C refine on completed draft run (scripts/refine_stage_c.py)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only gate + hydrate plan, no translate/refine")
    args = parser.parse_args()

    apply_local_env(REPO_ROOT)
    _ensure_production_env()
    py = _python()

    if not args.skip_gate:
        try:
            gate_doc = _run_gate_json(py)
        except json.JSONDecodeError as exc:
            print(f"throughput_gate: invalid JSON output ({exc})", file=sys.stderr)
            return 2
        decision = gate_doc.get("decision")
        print(f"throughput_gate: {decision}")
        if decision == "BLOCK":
            for step in gate_doc.get("fix_paths") or []:
                print(f"  → {step}")
            return 2

    if not args.no_hydrate:
        hydrate_cmd = [
            py,
            "scripts/hydrate_checkpoint.py",
            "--run-id",
            args.run_id,
            "--chapter-offset",
            str(args.chapter_offset),
            "--limit-chapters",
            str(args.target_new_chapters),
            "--json",
        ]
        if args.hydrate_apply:
            hydrate_cmd.append("--apply")
        _run(hydrate_cmd, with_production_env=True)

    if args.refine:
        refine_cmd = [
            py,
            "scripts/refine_stage_c.py",
            "--run-id",
            args.run_id,
            "--stage-state-path",
            str(REPO_ROOT / PRODUCTION_STAGE_STATE_REL),
        ]
        if args.dry_run:
            refine_cmd.append("--dry-run")
        return _run(refine_cmd, with_production_env=True).returncode

    if args.dry_run:
        print("resume_production: dry-run complete (no translate/refine)")
        return 0

    asset = args.asset_context
    if not asset.is_absolute():
        asset = REPO_ROOT / asset

    translate_cmd = [
        py,
        "scripts/translate.py",
        "--phase",
        "draft",
        "--stage",
        "stage_b",
        "--chapter-offset",
        str(args.chapter_offset),
        "--limit-chapters",
        str(args.target_new_chapters),
        "--run-id",
        args.run_id,
        "--asset-context",
        str(asset),
        "--stage-state-path",
        PRODUCTION_STAGE_STATE_REL,
    ]
    return _run(translate_cmd, with_production_env=True).returncode


if __name__ == "__main__":
    raise SystemExit(main())
