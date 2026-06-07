#!/usr/bin/env python3
"""Supervised translation autopilot — worker lifecycle bound to controller process."""

from __future__ import annotations

import argparse
import atexit
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from local_env import apply_local_env  # noqa: E402
from translation.stop_control import clear_stop_request, request_stop  # noqa: E402

import importlib.util

_registry_spec = importlib.util.spec_from_file_location(
    "pipeline_worker_registry", REPO_ROOT / "scripts" / "pipeline_worker_registry.py"
)
assert _registry_spec and _registry_spec.loader
_registry = importlib.util.module_from_spec(_registry_spec)
_registry_spec.loader.exec_module(_registry)

DEFAULT_DRAFT_MODEL = "deepseek/deepseek-v4-pro"

ROUND_PLAN: dict[str, dict[str, object]] = {
    "T-002": {
        "offset": 190,
        "limit": 20,
        "resume_run_id": "run_20260607_095821_draft_stage_b_50ch",
    },
    "T-003": {"offset": 210, "limit": 20, "resume_run_id": ""},
}

_child_proc: subprocess.Popen[str] | None = None
_controller_run_id = ""


def _python() -> str:
    venv = REPO_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _production_env(controller_run_id: str, round_id: str, draft_model: str) -> dict[str, str]:
    env = os.environ.copy()
    env["REAL_API_TESTS_ENABLED"] = "1"
    env["CONTROLLED_RUN_ENABLED"] = "1"
    env["TRANSLATION_CONTROLLER_PID"] = str(os.getpid())
    env["TRANSLATION_CONTROLLER_RUN_ID"] = controller_run_id
    env["TRANSLATION_ROUND_ID"] = round_id
    if draft_model:
        env["DRAFT_MODEL"] = draft_model
    return env


def _graceful_stop_child(*, reason: str = "controller_exit") -> None:
    global _child_proc
    if _child_proc is None or _child_proc.poll() is not None:
        return
    request_stop(
        reason=reason,
        requested_by="translation_autopilot_loop",
        target_run_id=os.environ.get("TRANSLATION_ACTIVE_RUN_ID", ""),
        repo_root=REPO_ROOT,
    )
    try:
        _child_proc.send_signal(signal.SIGTERM)
    except OSError:
        pass
    try:
        _child_proc.wait(timeout=120)
    except subprocess.TimeoutExpired:
        _child_proc.kill()
        _child_proc.wait(timeout=10)
    _child_proc = None


def _on_exit() -> None:
    _graceful_stop_child(reason="controller_atexit")


def _run_gate(py: str) -> dict:
    proc = subprocess.run(
        [py, "scripts/throughput_gate.py", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if not proc.stdout.strip():
        return {"decision": "BLOCK", "blocks": ["gate_empty_output"]}
    return json.loads(proc.stdout)


def run_supervised_round(
    *,
    round_id: str,
    phase: str = "draft",
    round_size: int = 20,
    draft_model: str = "",
    skip_gate: bool = False,
    poll_sec: float = 15.0,
) -> int:
    global _child_proc, _controller_run_id
    apply_local_env(REPO_ROOT)
    py = _python()
    plan = ROUND_PLAN.get(round_id)
    if not plan:
        print(f"unknown round_id={round_id}", file=sys.stderr)
        return 2

    _registry.heal_stale_workers()
    orphans = _registry.find_orphan_api_workers()
    if orphans:
        print(f"stopping {len(orphans)} orphan worker(s) before supervised start", flush=True)
        for o in orphans:
            _registry.request_worker_stop(
                run_id=str(o.get("run_id") or ""),
                worker_id=str(o.get("worker_id") or ""),
                reason="orphan_reclaim",
            )
        time.sleep(5)
        _registry.heal_stale_workers()

    if not skip_gate:
        gate = _run_gate(py)
        print(f"throughput_gate: {gate.get('decision')}")
        if gate.get("decision") == "BLOCK":
            return 2
        if gate.get("orphan_workers") or _registry.find_orphan_api_workers():
            print("BLOCK: orphan API workers remain", file=sys.stderr)
            return 2

    offset = int(plan["offset"])
    limit = int(plan.get("limit") or round_size)
    run_id = str(plan.get("resume_run_id") or "").strip()
    _controller_run_id = f"autopilot_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    clear_stop_request(REPO_ROOT)

    signal.signal(signal.SIGINT, lambda *_: (_graceful_stop_child(reason="sigint"), sys.exit(130)))
    signal.signal(signal.SIGTERM, lambda *_: (_graceful_stop_child(reason="sigterm"), sys.exit(143)))
    atexit.register(_on_exit)

    if run_id:
        hydrate = subprocess.run(
            [
                py,
                "scripts/hydrate_checkpoint.py",
                "--run-id",
                run_id,
                "--chapter-offset",
                str(offset),
                "--limit-chapters",
                str(limit),
                "--json",
                "--apply",
            ],
            cwd=REPO_ROOT,
            env=_production_env(_controller_run_id, round_id, draft_model),
        )
        if hydrate.returncode != 0:
            return hydrate.returncode

    cmd = [
        py,
        "scripts/translate.py",
        "--phase",
        phase,
        "--stage",
        "stage_b",
        "--chapter-offset",
        str(offset),
        "--limit-chapters",
        str(limit),
        "--asset-context",
        str(REPO_ROOT / "workspace/assets/translation_memory/pw-user-assets-flow.json"),
        "--stage-state-path",
        "workspace/stage_state_production.json",
        "--controller-pid",
        str(os.getpid()),
        "--controller-run-id",
        _controller_run_id,
        "--round-id",
        round_id,
    ]
    if run_id:
        cmd.extend(["--run-id", run_id])

    os.environ["TRANSLATION_ACTIVE_RUN_ID"] = run_id or f"stage_b_offset_{offset}"
    print("+", " ".join(cmd), flush=True)
    _child_proc = subprocess.Popen(
        cmd,
        cwd=REPO_ROOT,
        env=_production_env(_controller_run_id, round_id, draft_model),
    )

    while _child_proc.poll() is None:
        time.sleep(poll_sec)
        progress_path = REPO_ROOT / "workspace" / "runs" / (run_id or "") / "run_progress.json"
        if run_id and progress_path.is_file():
            try:
                prog = json.loads(progress_path.read_text(encoding="utf-8"))
                print(
                    f"[supervised] {run_id} {prog.get('completed_segments')}/{prog.get('total_segments')} "
                    f"status={prog.get('status')}",
                    flush=True,
                )
            except (OSError, json.JSONDecodeError):
                pass

    rc = int(_child_proc.returncode or 0)
    _child_proc = None
    clear_stop_request(REPO_ROOT)

    report_cmd = [
        py,
        "scripts/generate_translation_round_report.py",
        "--round-id",
        round_id,
    ]
    if run_id:
        report_cmd.extend(["--run-id", run_id])
    subprocess.run(report_cmd, cwd=REPO_ROOT)

    remaining = _registry.find_orphan_api_workers()
    if remaining:
        print(f"WARN: orphan workers after round: {len(remaining)}", file=sys.stderr)
        return 2 if rc == 0 else rc
    return rc


def main() -> int:
    parser = argparse.ArgumentParser(description="Supervised translation autopilot")
    parser.add_argument("--phase", choices=["draft"], default="draft")
    parser.add_argument("--round-id", default="T-002")
    parser.add_argument("--round-size", type=int, default=20)
    parser.add_argument("--real-api", action="store_true", default=True)
    parser.add_argument("--supervised", action="store_true", default=True)
    parser.add_argument("--auto-start-next", action="store_true")
    parser.add_argument("--continue-until", default="round-complete")
    parser.add_argument("--draft-model", default=DEFAULT_DRAFT_MODEL, help="DRAFT_MODEL (default DeepSeek)")
    parser.add_argument("--progress-interval-seconds", type=float, default=30.0)
    parser.add_argument("--foreground", action="store_true", default=True, help="Run in foreground (required)")
    parser.add_argument("--no-detach", action="store_true", default=True, help="Do not detach child process")
    parser.add_argument("--skip-gate", action="store_true")
    args = parser.parse_args()
    if not args.supervised:
        print("ERROR: --supervised is required for real API production", file=sys.stderr)
        return 2
    draft_model = (args.draft_model or DEFAULT_DRAFT_MODEL).strip()
    print(f"[autopilot] model={draft_model} round={args.round_id} poll={args.progress_interval_seconds}s", flush=True)
    return run_supervised_round(
        round_id=args.round_id,
        phase=args.phase,
        round_size=args.round_size,
        draft_model=draft_model,
        skip_gate=args.skip_gate,
        poll_sec=args.progress_interval_seconds,
    )


if __name__ == "__main__":
    raise SystemExit(main())
