#!/usr/bin/env python3
"""Compatibility wrapper for governed production resume.

Older Cursor prompts used this script to call ``translate.py --stage stage_b``
directly. That bypasses the current singleton-final scheduler gates, so the
entrypoint now delegates to ``scripts/local_scheduler_tick.py`` instead.
"""

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


def _scheduler_tick_command(py: str, args: argparse.Namespace) -> list[str]:
    cmd = [py, "scripts/local_scheduler_tick.py", "--json"]
    if args.real_api:
        cmd.append("--real-api")
    else:
        cmd.append("--dry-run")
    for attr, flag in (
        ("max_api_calls", "--max-api-calls"),
        ("max_segments", "--max-segments"),
        ("max_wall_time_minutes", "--max-wall-time-minutes"),
        ("batch_token_budget", "--batch-token-budget"),
        ("max_segments_per_call", "--max-segments-per-call"),
    ):
        value = getattr(args, attr, None)
        if value is not None:
            cmd.extend([flag, str(value)])
    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Resume governed production translation via local_scheduler_tick.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例（先 dry-run 检查下一步，不调用 API）::

  python3 scripts/resume_production.py --dry-run

示例（真实 API 只允许显式预算）::

  python3 scripts/resume_production.py --real-api --max-api-calls 5

历史 `--refine` 入口默认禁用。当前路线为翻译 -> 一致性校对 -> 唯一最终译文导出。

旧的 --run-id / --chapter-offset / --target-new-chapters / hydrate 参数仍被接受，
但不再直接驱动 translate.py；恢复与续跑由 scheduler 根据当前状态自行决定。
        """,
    )
    parser.add_argument("--run-id", default=DEFAULT_RESUME_RUN, help="Resume existing run (omit with --new-run)")
    parser.add_argument(
        "--new-run",
        action="store_true",
        help="Start a fresh run_id at --chapter-offset (do not pass --run-id to translate)",
    )
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
        help="Legacy refinement route; disabled unless ALLOW_LEGACY_REFINEMENT=1",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only gate + hydrate plan, no translate/refine")
    parser.add_argument("--real-api", action="store_true", help="Delegate a real scheduler tick; requires --max-api-calls > 0")
    parser.add_argument("--max-api-calls", type=int, default=None)
    parser.add_argument("--max-segments", type=int, default=None)
    parser.add_argument("--max-wall-time-minutes", type=float, default=None)
    parser.add_argument("--batch-token-budget", type=int, default=None)
    parser.add_argument("--max-segments-per-call", type=int, default=None)
    args = parser.parse_args()

    py = _python()

    if args.refine:
        print(
            "resume_production --refine is deprecated and disabled; "
            "current production path is scheduler -> consistency -> singleton final export.",
            file=sys.stderr,
        )
        return 2
    if args.real_api and int(args.max_api_calls or 0) <= 0:
        print("--real-api requires --max-api-calls > 0", file=sys.stderr)
        return 2

    if args.skip_gate or args.no_hydrate or args.hydrate_apply or args.new_run:
        print(
            "resume_production: legacy gate/hydrate/run-id flags are ignored; "
            "local_scheduler_tick.py owns pause, lock, orphan and resume decisions.",
            file=sys.stderr,
        )
    apply_local_env(REPO_ROOT)
    return _run(_scheduler_tick_command(py, args), check=False).returncode


if __name__ == "__main__":
    raise SystemExit(main())
