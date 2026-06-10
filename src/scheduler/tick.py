"""Single-tick runner for the local scheduler (FS-003 skeleton + FS-004 planner).

One tick is one supervised pass:

    pause check -> pre-flight status -> lock acquire -> pause re-check
    -> task plan (FS-004 decision table) -> dispatch exactly one task
    -> tick state + tick report persisted -> lock release -> clean exit

Dispatch is synchronous and attached: an implemented plan's command runs as
a supervised child process and the tick waits for it; nothing is ever
detached. In dry-run mode the draft branch invokes
``run_micro_round.py --dry-run --no-real-api`` (batch plan only, no worker,
no API). Real mode (FS-007) arms ``--real-api`` and demands a positive
``max_api_calls`` budget; cost guard and throughput gate still apply inside
``run_micro_round``. Not-implemented branches are reported explicitly
(``not_implemented``) instead of silently skipping.

Exit codes:
    0  completed, or politely skipped (paused / lock busy / active workers)
       — periodic launchd invocations must not register these as failures;
    1  executor / dispatched-command error;
    2  blocked state needing human / FS-006 attention (stale lock, orphans).
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
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
from scheduler.task_planner import plan_next_task

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

# A dispatched dry-run plan is a local batch computation; it must not hang.
DISPATCH_TIMEOUT_SECONDS = 900
# A real micro-round slice is bounded by --max-api-calls / wall-time budgets,
# but model latency varies; give the supervised child a generous ceiling.
REAL_DISPATCH_TIMEOUT_SECONDS = 3600


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _python(root: Path) -> str:
    venv = root / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


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


def _tail(text: str, lines: int) -> str:
    return "\n".join((text or "").strip().splitlines()[-lines:])


def make_dispatcher(root: Path, *, timeout_seconds: int = DISPATCH_TIMEOUT_SECONDS) -> TaskExecutor:
    """Default executor: run an implemented plan's command synchronously.

    The child is supervised (attached, awaited); not-implemented plans are
    reported explicitly so the tick never pretends to have done work.
    """

    def dispatch(plan: dict[str, Any]) -> dict[str, Any]:
        if not plan.get("implemented"):
            return {
                "executed": False,
                "not_implemented": True,
                "task_type": plan.get("task_type"),
                "reason": plan.get("reason"),
            }
        proc = subprocess.run(
            plan["command"],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
        return {
            "executed": True,
            "mode": plan.get("mode"),
            "task_type": plan.get("task_type"),
            "command": plan["command"],
            "returncode": proc.returncode,
            "stdout_tail": _tail(proc.stdout, 15),
            "stderr_tail": _tail(proc.stderr, 10),
        }

    return dispatch


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
    budgets: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run exactly one scheduler tick. Returns the tick result dict.

    The result always carries ``status``, ``exit_code`` and ``report_path``;
    the lock is always released on exit when this tick acquired it.
    ``budgets`` (max_api_calls etc.) are passed through to the planned
    command line.

    Real mode (``dry_run=False``, FS-007) additionally requires a positive
    ``max_api_calls`` budget — an unbounded real tick is never allowed.
    """
    budgets = dict(budgets or {})
    mode = "dry_run" if dry_run else "real"
    if not dry_run and int(budgets.get("max_api_calls") or 0) <= 0:
        raise ValueError(
            "real-mode tick requires a positive max_api_calls budget "
            "(unbounded real API ticks are forbidden)"
        )
    root = repo_root or _repo_root()
    result: dict[str, Any] = {
        "tick_id": _new_tick_id(),
        "mode": mode,
        "owner": owner,
        "started_at": _utc_now(),
        "status": "error",
        "blocked_reason": None,
        "next_task": None,
        "plan": None,
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
    plan = plan_next_task(
        status,
        mode=mode,
        budgets=budgets,
        repo_root=root,
        python_executable=_python(root),
    )
    result["plan"] = plan.to_dict()

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

        timeout = DISPATCH_TIMEOUT_SECONDS if dry_run else REAL_DISPATCH_TIMEOUT_SECONDS
        run_executor = executor or make_dispatcher(root, timeout_seconds=timeout)
        try:
            result["execution"] = run_executor(result["plan"])
        except Exception as exc:  # noqa: BLE001 — tick must still release the lock
            result["execution"] = {
                "executed": False,
                "error": f"{type(exc).__name__}: {exc}",
                "traceback": traceback.format_exc(limit=5),
            }
            return _finish(root, result, "error", reason="executor_error")
        returncode = result["execution"].get("returncode")
        if returncode not in (None, 0):
            return _finish(root, result, "error", reason="dispatched_command_failed")
        return _finish(root, result, "completed", reason=None)
    finally:
        release_lock(repo_root=root, pid=lock["pid"])
