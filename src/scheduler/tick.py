"""Single-tick skeleton for the local scheduler (FS-003, spec §9.1).

One tick is one supervised pass:

    pause check -> pre-flight status -> lock acquire -> pause re-check
    -> next-task snapshot -> placeholder dry-run execution
    -> tick state + tick report persisted -> lock release -> clean exit

FS-003 deliberately dispatches no real work: the placeholder executor only
records what *would* run. The task decision table arrives with FS-004 and
the first real-API smoke with FS-007. The tick never spawns detached
background workers and never calls a provider.

Exit codes:
    0  completed, or politely skipped (paused / lock busy / active workers)
       — periodic launchd invocations must not register these as failures;
    1  unexpected executor error;
    2  blocked state needing human / FS-006 attention (stale lock, orphans).
"""

from __future__ import annotations

import json
import os
import tempfile
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from scheduler.control import (
    SchedulerLockError,
    acquire_lock,
    is_paused,
    lock_status,
    release_lock,
)
from scheduler.status import collect_status

TICK_STATE_REL = "workspace/control/scheduler_tick_state.json"
TICK_REPORTS_REL = "workspace/control/tick_reports"

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_BLOCKED = 2

_STATUS_EXIT_CODE = {
    "completed": EXIT_OK,
    "skipped_paused": EXIT_OK,
    "skipped_lock_held": EXIT_OK,
    "skipped_active_workers": EXIT_OK,
    "blocked_stale_lock": EXIT_BLOCKED,
    "blocked_orphan_workers": EXIT_BLOCKED,
    "error": EXIT_ERROR,
}

TaskExecutor = Callable[[dict[str, Any]], dict[str, Any]]


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def _new_tick_id() -> str:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"tick_{stamp}_{os.getpid()}_{uuid.uuid4().hex[:6]}"


def execute_task_dry_run(task: dict[str, Any]) -> dict[str, Any]:
    """FS-003 placeholder executor: record what would run, perform nothing."""
    return {
        "executed": False,
        "mode": "dry_run",
        "planned_task": task,
        "note": "FS-003 skeleton placeholder; task dispatch arrives with FS-004",
    }


def _write_tick_report(root: Path, result: dict[str, Any]) -> Path:
    path = root / TICK_REPORTS_REL / f"{result['tick_id']}.json"
    _write_json(path, result)
    return path


def _update_tick_state(root: Path, result: dict[str, Any]) -> None:
    """Maintain workspace/control/scheduler_tick_state.json.

    FS-002 status reads last_successful_tick / last_blocked_reason from here,
    so those field names are contract. A completed tick clears the blocked
    reason; a skip/block records it while preserving the last success stamp.
    """
    path = root / TICK_STATE_REL
    state: dict[str, Any] = {}
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(doc, dict):
                state = doc
        except (OSError, json.JSONDecodeError):
            state = {}
    if result["status"] == "completed":
        state["last_successful_tick"] = result["finished_at"]
        state["last_blocked_reason"] = None
    else:
        state["last_blocked_reason"] = result["blocked_reason"]
    state["last_tick_id"] = result["tick_id"]
    state["last_tick_status"] = result["status"]
    state["updated_at"] = result["finished_at"]
    _write_json(path, state)


def _finish(
    root: Path,
    result: dict[str, Any],
    status: str,
    *,
    reason: str | None,
) -> dict[str, Any]:
    result["status"] = status
    result["blocked_reason"] = reason
    result["exit_code"] = _STATUS_EXIT_CODE[status]
    result["finished_at"] = _utc_now()
    report_path = _write_tick_report(root, result)
    result["report_path"] = str(report_path)
    _update_tick_state(root, result)
    return result


def run_tick(
    repo_root: Path | None = None,
    *,
    dry_run: bool = True,
    owner: str = "local_scheduler_tick",
    executor: TaskExecutor | None = None,
) -> dict[str, Any]:
    """Run exactly one scheduler tick. Returns the tick result dict.

    The result always carries ``status``, ``exit_code`` and ``report_path``;
    the lock is always released on exit when this tick acquired it.
    """
    if not dry_run:
        raise ValueError(
            "FS-003 tick skeleton only supports dry_run=True; "
            "real execution lands in FS-004 / FS-007"
        )
    root = repo_root or _repo_root()
    result: dict[str, Any] = {
        "tick_id": _new_tick_id(),
        "mode": "dry_run",
        "owner": owner,
        "started_at": _utc_now(),
        "status": "error",
        "blocked_reason": None,
        "next_task": None,
        "execution": None,
    }

    # 1. Pause gate (spec §9.3): never take the lock while paused.
    if is_paused(root):
        return _finish(root, result, "skipped_paused", reason="paused")

    # 2. Pre-flight snapshot: lock / worker health and next-task decision.
    status = collect_status(root)
    if status["scheduler_lock_status"] == "held":
        return _finish(root, result, "skipped_lock_held", reason="lock_held")
    if status["scheduler_lock_status"] == "stale":
        # Stale locks are never reclaimed by a tick; FS-006 owns that cleanup.
        return _finish(root, result, "blocked_stale_lock", reason="stale_lock")
    if status["orphan_worker_count"]:
        return _finish(root, result, "blocked_orphan_workers", reason="orphan_workers")
    if status["active_worker_count"]:
        # Supervised work already in flight: yield politely, not an error.
        return _finish(root, result, "skipped_active_workers", reason="active_workers")

    result["next_task"] = {
        "task": status["next_task"],
        "round_id": status["next_round_id"],
        "chapter_range": status["next_chapter_range"],
        "phase": status["current_phase"],
    }

    # 3. Mutual exclusion (spec §9.4); racing ticks lose gracefully.
    try:
        lock = acquire_lock(owner=owner, repo_root=root, reclaim_stale=False)
    except SchedulerLockError as exc:
        if exc.reason == "lock_held":
            return _finish(root, result, "skipped_lock_held", reason="lock_held")
        # "stale" seen exactly at acquire time is usually a race against a
        # tick that was mid-write or mid-release; re-probe once before
        # declaring a genuinely stale lock (which FS-006 owns).
        time.sleep(0.1)
        probe = lock_status(root)
        if not probe["exists"] or probe["alive"]:
            return _finish(root, result, "skipped_lock_held", reason="lock_race")
        return _finish(root, result, "blocked_stale_lock", reason="stale_lock")

    try:
        # 4. Pause may have been requested between the gate and the lock.
        if is_paused(root):
            return _finish(root, result, "skipped_paused", reason="paused")

        run_executor = executor or execute_task_dry_run
        try:
            result["execution"] = run_executor(result["next_task"])
        except Exception as exc:  # noqa: BLE001 — tick must still release the lock
            result["execution"] = {
                "executed": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(limit=5),
            }
            return _finish(root, result, "error", reason="executor_error")
        return _finish(root, result, "completed", reason=None)
    finally:
        release_lock(repo_root=root, pid=lock["pid"])
