#!/usr/bin/env python3
"""Single-worker registry for translate/refine pipeline processes."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STATE_PATH = REPO_ROOT / "workspace" / "pipeline_state.json"
DEFAULT_HEARTBEAT_TIMEOUT_SEC = 300


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def load_state(state_path: Path | None = None) -> dict[str, Any]:
    path = state_path or DEFAULT_STATE_PATH
    if not path.is_file():
        return {"schema_version": 1, "workers": [], "updated_at": utc_now()}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {"schema_version": 1, "workers": [], "updated_at": utc_now()}
        data.setdefault("workers", [])
        return data
    except Exception:
        return {"schema_version": 1, "workers": [], "updated_at": utc_now()}


def save_state(state: dict[str, Any], state_path: Path | None = None) -> None:
    path = state_path or DEFAULT_STATE_PATH
    state["updated_at"] = utc_now()
    atomic_write_json(path, state)


def is_worker_active(
    worker: dict[str, Any],
    *,
    heartbeat_timeout_sec: int = DEFAULT_HEARTBEAT_TIMEOUT_SEC,
) -> bool:
    status = str(worker.get("status") or "")
    if status not in {"pending", "in_progress"}:
        return False
    pid = int(worker.get("pid") or 0)
    if not pid_alive(pid):
        return False
    heartbeat = parse_dt(str(worker.get("heartbeat_at") or worker.get("started_at") or ""))
    if heartbeat is None:
        return True
    age = (datetime.now(timezone.utc) - heartbeat).total_seconds()
    return age <= heartbeat_timeout_sec


def is_worker_stale(
    worker: dict[str, Any],
    *,
    heartbeat_timeout_sec: int = DEFAULT_HEARTBEAT_TIMEOUT_SEC,
) -> bool:
    status = str(worker.get("status") or "")
    if status not in {"pending", "in_progress"}:
        return False
    pid = int(worker.get("pid") or 0)
    heartbeat = parse_dt(str(worker.get("heartbeat_at") or worker.get("started_at") or ""))
    if heartbeat is None:
        return not pid_alive(pid)
    age = (datetime.now(timezone.utc) - heartbeat).total_seconds()
    if age > heartbeat_timeout_sec:
        return True
    return not pid_alive(pid)


def find_active_workers(
    *,
    task_type: str | None = None,
    stage: str | None = None,
    run_id: str | None = None,
    chapter_offset: int | None = None,
    state_path: Path | None = None,
) -> list[dict[str, Any]]:
    state = load_state(state_path)
    out: list[dict[str, Any]] = []
    for worker in state.get("workers", []):
        if not isinstance(worker, dict):
            continue
        if not is_worker_active(worker):
            continue
        if task_type and worker.get("task_type") != task_type:
            continue
        if stage and worker.get("stage") != stage:
            continue
        if run_id and worker.get("run_id") != run_id:
            continue
        if chapter_offset is not None and worker.get("chapter_offset") != chapter_offset:
            continue
        out.append(worker)
    return out


def register_worker(
    *,
    task_type: str,
    stage: str,
    run_id: str,
    chapter_offset: int = 0,
    pid: int | None = None,
    controller_pid: int | None = None,
    controller_run_id: str = "",
    round_id: str = "",
    chapter_range: str = "",
    provider: str = "",
    model: str = "",
    stop_policy: str = "stop_when_controller_exits",
    state_path: Path | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """Register worker or return (None, reason) if duplicate active worker exists."""
    active = find_active_workers(
        task_type=task_type,
        stage=stage,
        run_id=run_id,
        chapter_offset=chapter_offset,
        state_path=state_path,
    )
    if active:
        w = active[0]
        return None, (
            f"already_running:worker_id={w.get('worker_id')} pid={w.get('pid')} "
            f"task={task_type} stage={stage} run_id={run_id}"
        )

    now = utc_now()
    worker = {
        "worker_id": f"{task_type}-{run_id}-{uuid4().hex[:8]}",
        "pid": pid or os.getpid(),
        "controller_pid": int(controller_pid or 0),
        "controller_run_id": controller_run_id,
        "task_type": task_type,
        "stage": stage,
        "run_id": run_id,
        "round_id": round_id,
        "chapter_range": chapter_range,
        "chapter_offset": chapter_offset,
        "provider": provider,
        "model": model,
        "stop_policy": stop_policy,
        "started_at": now,
        "heartbeat_at": now,
        "status": "in_progress",
    }
    state = load_state(state_path)
    workers = [w for w in state.get("workers", []) if isinstance(w, dict)]
    workers.append(worker)
    state["workers"] = workers
    save_state(state, state_path)
    return worker, "registered"


def heartbeat_worker(
    worker_id: str,
    *,
    status: str = "in_progress",
    state_path: Path | None = None,
) -> bool:
    state = load_state(state_path)
    updated = False
    for worker in state.get("workers", []):
        if worker.get("worker_id") == worker_id:
            worker["heartbeat_at"] = utc_now()
            worker["status"] = status
            updated = True
            break
    if updated:
        save_state(state, state_path)
    return updated


def unregister_worker(worker_id: str, *, status: str = "completed", state_path: Path | None = None) -> bool:
    state = load_state(state_path)
    updated = False
    for worker in state.get("workers", []):
        if worker.get("worker_id") == worker_id:
            worker["status"] = status
            worker["heartbeat_at"] = utc_now()
            updated = True
            break
    if updated:
        save_state(state, state_path)
    return updated


def _read_lock_pid(lock_path: Path) -> int | None:
    if not lock_path.is_file():
        return None
    try:
        return int(lock_path.read_text(encoding="utf-8").strip().splitlines()[0])
    except (ValueError, IndexError, OSError):
        return None


def _kill_pid(pid: int) -> bool:
    if pid <= 0 or not pid_alive(pid):
        return False
    import signal

    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    for _ in range(20):
        if not pid_alive(pid):
            return True
        import time

        time.sleep(0.5)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return False
    return not pid_alive(pid)


def _run_progress_heartbeat_age_sec(repo_root: Path, run_id: str) -> float | None:
    """Return seconds since run_progress heartbeat for a run, or None if unavailable."""
    rp_path = repo_root / "workspace" / "runs" / run_id / "run_progress.json"
    if not rp_path.is_file():
        return None
    try:
        data = json.loads(rp_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    heartbeat = parse_dt(str(data.get("heartbeat_at") or data.get("updated_at") or ""))
    if heartbeat is None:
        return None
    return (datetime.now(timezone.utc) - heartbeat).total_seconds()


def heal_stale_workers(
    *,
    heartbeat_timeout_sec: int = DEFAULT_HEARTBEAT_TIMEOUT_SEC,
    state_path: Path | None = None,
    lock_dir: Path | None = None,
    repo_root: Path | None = None,
) -> dict[str, Any]:
    """Kill frozen workers (alive PID, stale heartbeat), clear locks, mark registry failed."""
    path = state_path or DEFAULT_STATE_PATH
    locks = lock_dir or (REPO_ROOT / "workspace" / ".locks")
    root = repo_root or REPO_ROOT
    state = load_state(path)
    healed: list[dict[str, Any]] = []

    for worker in state.get("workers", []):
        if not isinstance(worker, dict) or not is_worker_stale(worker, heartbeat_timeout_sec=heartbeat_timeout_sec):
            continue
        pid = int(worker.get("pid") or 0)
        run_id = str(worker.get("run_id") or "")
        progress_age = _run_progress_heartbeat_age_sec(root, run_id) if run_id else None
        if progress_age is not None and progress_age <= heartbeat_timeout_sec:
            continue
        killed = _kill_pid(pid) if pid > 0 else False
        worker["status"] = "failed"
        worker["heartbeat_at"] = utc_now()
        worker["healed_at"] = utc_now()
        worker["heal_reason"] = "stale_heartbeat" if pid_alive(pid) else "dead_pid"
        if killed:
            worker["heal_action"] = "sigterm_killed"
        elif pid > 0 and pid_alive(pid):
            worker["heal_action"] = "kill_failed"
        else:
            worker["heal_action"] = "marked_failed"
        healed.append(
            {
                "worker_id": worker.get("worker_id"),
                "pid": pid,
                "task_type": worker.get("task_type"),
                "run_id": worker.get("run_id"),
                "heal_action": worker.get("heal_action"),
            }
        )

    if healed:
        save_state(state, path)

    cleared_locks: list[str] = []
    healed_pids = {int(h.get("pid") or 0) for h in healed if int(h.get("pid") or 0) > 0}
    if locks.is_dir():
        for lock in locks.glob("*.lock"):
            pid = _read_lock_pid(lock)
            if pid is None:
                continue
            if not pid_alive(pid):
                lock.unlink(missing_ok=True)
                cleared_locks.append(lock.name)
                continue
            if pid in healed_pids:
                lock.unlink(missing_ok=True)
                cleared_locks.append(lock.name)
                continue
            run_id = ""
            for worker in state.get("workers", []):
                if isinstance(worker, dict) and int(worker.get("pid") or 0) == pid:
                    run_id = str(worker.get("run_id") or "")
                    break
            progress_age = _run_progress_heartbeat_age_sec(root, run_id) if run_id else None
            if progress_age is not None and progress_age <= heartbeat_timeout_sec:
                continue
            if _kill_pid(pid):
                lock.unlink(missing_ok=True)
                cleared_locks.append(lock.name)

    return {
        "healed_workers": healed,
        "healed_count": len(healed),
        "cleared_locks": cleared_locks,
        "heartbeat_timeout_sec": heartbeat_timeout_sec,
    }


def find_orphan_api_workers(state_path: Path | None = None) -> list[dict[str, Any]]:
    """Active real-API workers without a living controller (supervised mode violation)."""
    state = load_state(state_path)
    orphans: list[dict[str, Any]] = []
    for worker in state.get("workers", []):
        if not isinstance(worker, dict) or not is_worker_active(worker):
            continue
        task = str(worker.get("task_type") or "")
        if task not in {"translate", "refine"}:
            continue
        ctrl_pid = int(worker.get("controller_pid") or 0)
        if ctrl_pid <= 0:
            orphans.append({**worker, "orphan_reason": "missing_controller_pid"})
            continue
        if not pid_alive(ctrl_pid):
            orphans.append({**worker, "orphan_reason": "dead_controller_pid"})
    return orphans


def request_worker_stop(
    *,
    run_id: str = "",
    worker_id: str = "",
    reason: str = "controller_exit",
    requested_by: str = "pipeline_worker_registry",
    repo_root: Path | None = None,
) -> dict[str, Any]:
    sys.path.insert(0, str((repo_root or REPO_ROOT) / "src"))
    from translation.stop_control import request_stop  # noqa: WPS433

    payload = request_stop(
        reason=reason,
        requested_by=requested_by,
        target_worker_id=worker_id,
        target_run_id=run_id,
        repo_root=repo_root or REPO_ROOT,
    )
    import signal

    state = load_state()
    stopped: list[dict[str, Any]] = []
    for worker in state.get("workers", []):
        if not isinstance(worker, dict) or not is_worker_active(worker):
            continue
        if worker_id and worker.get("worker_id") != worker_id:
            continue
        if run_id and worker.get("run_id") != run_id:
            continue
        pid = int(worker.get("pid") or 0)
        if pid > 0 and pid_alive(pid):
            try:
                os.kill(pid, signal.SIGTERM)
            except OSError:
                pass
        stopped.append(
            {
                "worker_id": worker.get("worker_id"),
                "pid": pid,
                "run_id": worker.get("run_id"),
            }
        )
    return {"stop_request": payload, "signaled_workers": stopped}


def summarize_registry(state_path: Path | None = None) -> dict[str, Any]:
    state = load_state(state_path)
    workers = [w for w in state.get("workers", []) if isinstance(w, dict)]
    active = [w for w in workers if is_worker_active(w)]
    stale = [w for w in workers if is_worker_stale(w)]
    orphans = find_orphan_api_workers(state_path)
    return {
        "total_workers": len(workers),
        "active_workers": active,
        "active_count": len(active),
        "stale_workers": stale,
        "stale_count": len(stale),
        "orphan_workers": orphans,
        "orphan_count": len(orphans),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Pipeline worker registry")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--heal",
        action="store_true",
        help="Kill stale workers and remove dead-pid lock files",
    )
    parser.add_argument(
        "--heartbeat-timeout-sec",
        type=int,
        default=DEFAULT_HEARTBEAT_TIMEOUT_SEC,
    )
    parser.add_argument("--request-stop", action="store_true", help="Write stop file and SIGTERM workers")
    parser.add_argument("--run-id", default="", help="Target run_id for --request-stop")
    parser.add_argument("--worker-id", default="", help="Target worker_id for --request-stop")
    args = parser.parse_args()
    if args.request_stop:
        result = request_worker_stop(
            run_id=args.run_id.strip(),
            worker_id=args.worker_id.strip(),
            reason="manual_request_stop",
        )
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(f"stop requested; signaled={len(result.get('signaled_workers', []))}")
        return 0
    if args.heal:
        result = heal_stale_workers(heartbeat_timeout_sec=args.heartbeat_timeout_sec)
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2))
        else:
            print(
                f"healed={result['healed_count']} cleared_locks={len(result['cleared_locks'])}"
            )
        return 0
    summary = summarize_registry()
    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"active={summary['active_count']} stale={summary['stale_count']} "
            f"total={summary['total_workers']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
