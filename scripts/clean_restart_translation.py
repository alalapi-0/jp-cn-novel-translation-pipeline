#!/usr/bin/env python3
"""Clean stop all translation workers, heal stale state, verify CLEAN before restart."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from local_env import apply_local_env  # noqa: E402
from translation.stop_control import clear_stop_request, request_stop  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "pipeline_worker_registry", REPO_ROOT / "scripts" / "pipeline_worker_registry.py"
)
assert _spec and _spec.loader
_registry = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_registry)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _archive_stop_signal() -> None:
    src = REPO_ROOT / "workspace" / "control" / "stop_requested.json"
    if not src.is_file():
        return
    archive_dir = REPO_ROOT / "workspace" / "control" / "archive" / f"clean_restart_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    archive_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, archive_dir / "stop_requested.json")
    clear_stop_request(REPO_ROOT)


def request_clean_stop() -> dict:
    return request_stop(
        reason="clean_restart_requested_by_user",
        requested_by="clean_restart_agent",
        target_worker_id="*",
        target_run_id="*",
        repo_root=REPO_ROOT,
    )


def stop_known_workers(*, wait_sec: int = 60) -> dict:
    signaled: list[dict] = []
    for worker in _registry.find_active_workers():
        pid = int(worker.get("pid") or 0)
        if pid > 0 and _registry.pid_alive(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
            signaled.append({"worker_id": worker.get("worker_id"), "pid": pid, "run_id": worker.get("run_id")})
    # Also stop active controllers (autopilot) if registered
    for worker in _registry.find_active_workers(task_type="translate"):
        ctrl = int(worker.get("controller_pid") or 0)
        if ctrl > 0 and _registry.pid_alive(ctrl):
            try:
                os.kill(ctrl, signal.SIGTERM)
            except OSError:
                pass
    deadline = time.monotonic() + wait_sec
    while time.monotonic() < deadline:
        alive = [w for w in _registry.find_active_workers() if _registry.pid_alive(int(w.get("pid") or 0))]
        if not alive:
            break
        time.sleep(2)
    return {"signaled": signaled, "remaining_active": len(_registry.find_active_workers())}


def main() -> int:
    parser = argparse.ArgumentParser(description="Clean restart: stop workers and heal")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--wait-sec", type=int, default=60)
    parser.add_argument("--no-heal", action="store_true")
    args = parser.parse_args()
    apply_local_env(REPO_ROOT)

    stop_doc = request_clean_stop()
    stop_result = stop_known_workers(wait_sec=args.wait_sec)
    if not args.no_heal:
        heal = _registry.heal_stale_workers()
    else:
        heal = {"healed_count": 0}

    _archive_stop_signal()

    # Mark in_progress registry entries stopped if PID dead
    state = _registry.load_state()
    for w in state.get("workers", []):
        if w.get("status") in {"in_progress", "pending"} and not _registry.pid_alive(int(w.get("pid") or 0)):
            w["status"] = "stopped_by_controller"
            w["stop_reason"] = "clean_restart"
            w["stopped_at"] = _utc_now()
    _registry.save_state(state)

    from check_orphan_workers import evaluate  # noqa: WPS433

    check = evaluate()
    result = {
        "stop_request": stop_doc,
        "stop_result": stop_result,
        "heal": heal,
        "orphan_check": check,
        "ready_to_restart": check["decision"] in {"CLEAN", "WARN"} and check["orphan_worker_count"] == 0,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"ready_to_restart={result['ready_to_restart']} decision={check['decision']}")
    return 0 if result["ready_to_restart"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
