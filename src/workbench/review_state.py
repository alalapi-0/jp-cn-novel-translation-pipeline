"""Dedicated review state persisted under workspace/review_state.json."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REVIEW_STATE_FILE = "review_state.json"


def review_state_path(repo_root: Path) -> Path:
    return repo_root / "workspace" / REVIEW_STATE_FILE


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _empty_state() -> dict[str, Any]:
    return {"version": 1, "projects": {}, "updated_at": utc_now()}


def load_review_state(repo_root: Path) -> dict[str, Any]:
    path = review_state_path(repo_root)
    if not path.is_file():
        return _empty_state()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _empty_state()
    if not isinstance(data, dict):
        return _empty_state()
    data.setdefault("version", 1)
    data.setdefault("projects", {})
    return data


def save_review_state(repo_root: Path, state: dict[str, Any]) -> None:
    path = review_state_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utc_now()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def get_project_review_state(repo_root: Path, project_id: str) -> dict[str, Any]:
    state = load_review_state(repo_root)
    projects = state.setdefault("projects", {})
    project = projects.setdefault(project_id, {"segments": {}, "issues": {}})
    project.setdefault("segments", {})
    project.setdefault("issues", {})
    return project


def patch_project_review_state(
    repo_root: Path,
    project_id: str,
    *,
    segments: dict[str, Any] | None = None,
    issues: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state = load_review_state(repo_root)
    projects = state.setdefault("projects", {})
    project = projects.setdefault(project_id, {"segments": {}, "issues": {}})
    seg_map = project.setdefault("segments", {})
    issue_map = project.setdefault("issues", {})
    if segments:
        for seg_id, entry in segments.items():
            if not isinstance(entry, dict):
                continue
            seg_map[str(seg_id)] = {**entry, "at": entry.get("at") or utc_now()}
    if issues:
        for issue_id, entry in issues.items():
            if not isinstance(entry, dict):
                continue
            issue_map[str(issue_id)] = {**entry, "at": entry.get("at") or utc_now()}
    save_review_state(repo_root, state)
    return get_project_review_state(repo_root, project_id)


def delete_project_review_state(repo_root: Path, project_id: str) -> bool:
    state = load_review_state(repo_root)
    projects = state.setdefault("projects", {})
    if not isinstance(projects, dict):
        state["projects"] = {}
        save_review_state(repo_root, state)
        return False
    existed = str(project_id) in projects
    if existed:
        projects.pop(str(project_id), None)
        save_review_state(repo_root, state)
    return existed
