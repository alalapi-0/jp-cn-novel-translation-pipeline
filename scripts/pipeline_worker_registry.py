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
    pid = int(worker.get("pid") or 0)
    if pid_alive(pid):
        return False
    heartbeat = parse_dt(str(worker.get("heartbeat_at") or worker.get("started_at") or ""))
    if heartbeat is None:
        return True
    age = (datetime.now(timezone.utc) - heartbeat).total_seconds()
    return age > heartbeat_timeout_sec


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
        "task_type": task_type,
        "stage": stage,
        "run_id": run_id,
        "chapter_offset": chapter_offset,
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


def summarize_registry(state_path: Path | None = None) -> dict[str, Any]:
    state = load_state(state_path)
    workers = [w for w in state.get("workers", []) if isinstance(w, dict)]
    active = [w for w in workers if is_worker_active(w)]
    stale = [w for w in workers if is_worker_stale(w)]
    return {
        "total_workers": len(workers),
        "active_workers": active,
        "active_count": len(active),
        "stale_workers": stale,
        "stale_count": len(stale),
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Pipeline worker registry")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
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
