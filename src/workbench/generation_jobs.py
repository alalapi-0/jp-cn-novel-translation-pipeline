"""Persistent generation job state for Workbench quickstart requests."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

GENERATION_JOBS_FILE = "generation_jobs.json"
ACTIVE_JOB_STATUSES = {"queued", "running"}
TERMINAL_JOB_STATUSES = {"succeeded", "failed"}
MAX_HISTORY_PER_PROJECT = 20

_state_guard = threading.Lock()
_project_lock_guard = threading.Lock()
_project_locks: dict[str, threading.Lock] = {}


@dataclass(frozen=True)
class GenerationInProgressError(RuntimeError):
    """Raised when another generation job is already running for the project."""

    project_id: str
    job: dict[str, Any] | None = None

    def __str__(self) -> str:
        req = str((self.job or {}).get("request_id") or "").strip()
        if req:
            return f"generation already in progress for {self.project_id} (request_id={req})"
        return f"generation already in progress for {self.project_id}"


def generation_jobs_path(repo_root: Path) -> Path:
    return repo_root / "workspace" / GENERATION_JOBS_FILE


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_state() -> dict[str, Any]:
    return {"version": 1, "projects": {}, "updated_at": utc_now()}


def _normalize_state(data: dict[str, Any]) -> dict[str, Any]:
    state = data if isinstance(data, dict) else {}
    state.setdefault("version", 1)
    state.setdefault("projects", {})
    state.setdefault("updated_at", utc_now())
    if not isinstance(state["projects"], dict):
        state["projects"] = {}
    return state


def _load_state_unlocked(repo_root: Path) -> dict[str, Any]:
    path = generation_jobs_path(repo_root)
    if not path.is_file():
        return _empty_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_state()
    return _normalize_state(data)


def _save_state_unlocked(repo_root: Path, state: dict[str, Any]) -> None:
    path = generation_jobs_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utc_now()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def _project_entry(state: dict[str, Any], project_id: str) -> dict[str, Any]:
    projects = state.setdefault("projects", {})
    project = projects.setdefault(project_id, {"current": None, "history": []})
    if not isinstance(project, dict):
        project = {"current": None, "history": []}
        projects[project_id] = project
    history = project.get("history")
    if not isinstance(history, list):
        project["history"] = []
    return project


def project_generation_lock(project_id: str) -> threading.Lock:
    with _project_lock_guard:
        lock = _project_locks.get(project_id)
        if lock is None:
            lock = threading.Lock()
            _project_locks[project_id] = lock
        return lock


def _append_history(project: dict[str, Any], job: dict[str, Any]) -> None:
    history = project.setdefault("history", [])
    if not isinstance(history, list):
        history = []
        project["history"] = history
    history.insert(0, deepcopy(job))
    del history[MAX_HISTORY_PER_PROJECT:]


def get_project_generation_job(repo_root: Path, project_id: str) -> dict[str, Any] | None:
    with _state_guard:
        state = _load_state_unlocked(repo_root)
        project = state.get("projects", {}).get(project_id)
        if not isinstance(project, dict):
            return None
        current = project.get("current")
        return deepcopy(current) if isinstance(current, dict) else None


def find_generation_job(repo_root: Path, project_id: str, request_id: str) -> dict[str, Any] | None:
    req = str(request_id or "").strip()
    if not req:
        return None
    with _state_guard:
        state = _load_state_unlocked(repo_root)
        project = state.get("projects", {}).get(project_id)
        if not isinstance(project, dict):
            return None
        current = project.get("current")
        if isinstance(current, dict) and str(current.get("request_id") or "") == req:
            return deepcopy(current)
        history = project.get("history")
        if isinstance(history, list):
            for item in history:
                if isinstance(item, dict) and str(item.get("request_id") or "") == req:
                    return deepcopy(item)
        return None


def prepare_generation_job(
    repo_root: Path,
    project_id: str,
    *,
    request_id: str,
    mode: str,
    sample_text: str,
) -> dict[str, Any]:
    req = str(request_id or "").strip()
    if not req:
        raise ValueError("request_id is required")
    with _state_guard:
        state = _load_state_unlocked(repo_root)
        project = _project_entry(state, project_id)
        current = project.get("current")
        if isinstance(current, dict):
            current_req = str(current.get("request_id") or "").strip()
            current_status = str(current.get("status") or "").strip().lower()
            if current_req == req:
                return deepcopy(current)
            if current_status in ACTIVE_JOB_STATUSES:
                raise GenerationInProgressError(project_id=project_id, job=deepcopy(current))
            _append_history(project, current)

        now = utc_now()
        job = {
            "request_id": req,
            "project_id": project_id,
            "mode": mode,
            "status": "queued",
            "created_at": now,
            "updated_at": now,
            "started_at": None,
            "finished_at": None,
            "sample_chars": len(sample_text or ""),
            "sample_preview": str(sample_text or "").strip().replace("\n", " ")[:120],
            "segments_created": 0,
            "error_code": None,
            "error_message": None,
            "response_payload": None,
        }
        project["current"] = job
        _save_state_unlocked(repo_root, state)
        return deepcopy(job)


def mark_generation_running(repo_root: Path, project_id: str, request_id: str) -> dict[str, Any] | None:
    req = str(request_id or "").strip()
    if not req:
        return None
    with _state_guard:
        state = _load_state_unlocked(repo_root)
        project = _project_entry(state, project_id)
        current = project.get("current")
        if not isinstance(current, dict) or str(current.get("request_id") or "").strip() != req:
            return None
        if str(current.get("status") or "").strip().lower() == "running":
            return deepcopy(current)
        now = utc_now()
        current["status"] = "running"
        current["started_at"] = current.get("started_at") or now
        current["updated_at"] = now
        _save_state_unlocked(repo_root, state)
        return deepcopy(current)


def mark_generation_succeeded(
    repo_root: Path,
    project_id: str,
    request_id: str,
    *,
    response_payload: dict[str, Any],
) -> dict[str, Any] | None:
    req = str(request_id or "").strip()
    if not req:
        return None
    with _state_guard:
        state = _load_state_unlocked(repo_root)
        project = _project_entry(state, project_id)
        current = project.get("current")
        if not isinstance(current, dict) or str(current.get("request_id") or "").strip() != req:
            return None
        now = utc_now()
        current["status"] = "succeeded"
        current["updated_at"] = now
        current["finished_at"] = now
        current["error_code"] = None
        current["error_message"] = None
        current["segments_created"] = int(response_payload.get("segments_created") or 0)
        current["response_payload"] = deepcopy(response_payload)
        _save_state_unlocked(repo_root, state)
        return deepcopy(current)


def mark_generation_failed(
    repo_root: Path,
    project_id: str,
    request_id: str,
    *,
    error_code: str,
    error_message: str,
) -> dict[str, Any] | None:
    req = str(request_id or "").strip()
    if not req:
        return None
    with _state_guard:
        state = _load_state_unlocked(repo_root)
        project = _project_entry(state, project_id)
        current = project.get("current")
        if not isinstance(current, dict) or str(current.get("request_id") or "").strip() != req:
            return None
        now = utc_now()
        current["status"] = "failed"
        current["updated_at"] = now
        current["finished_at"] = now
        current["error_code"] = str(error_code or "generation_failed")
        current["error_message"] = str(error_message or "generation failed")
        current["response_payload"] = None
        _save_state_unlocked(repo_root, state)
        return deepcopy(current)


def clear_project_generation_job(repo_root: Path, project_id: str) -> dict[str, Any] | None:
    """Clear current job and keep the latest job in history."""
    with _state_guard:
        state = _load_state_unlocked(repo_root)
        project = state.get("projects", {}).get(project_id)
        if not isinstance(project, dict):
            return None
        current = project.get("current")
        if isinstance(current, dict):
            _append_history(project, current)
            project["current"] = None
            _save_state_unlocked(repo_root, state)
            return deepcopy(current)
        return None


def delete_project_generation_state(repo_root: Path, project_id: str) -> bool:
    with _state_guard:
        state = _load_state_unlocked(repo_root)
        projects = state.get("projects", {})
        if not isinstance(projects, dict):
            return False
        existed = str(project_id) in projects
        if existed:
            projects.pop(str(project_id), None)
            _save_state_unlocked(repo_root, state)
            return True
        return False
