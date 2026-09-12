"""Dedicated review state persisted under workspace/review_state.json."""

from __future__ import annotations

import hashlib
import json
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REVIEW_STATE_FILE = "review_state.json"
APPROVAL_IDENTITY_SCHEMA = "segment_approval_identity"
APPROVAL_IDENTITY_DOMAIN = "light-novel.workbench.segment-approval"
APPROVAL_IDENTITY_VERSION = 1
_review_state_lock = threading.Lock()


def review_state_path(repo_root: Path) -> Path:
    return repo_root / "workspace" / REVIEW_STATE_FILE


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def segment_text(seg: dict[str, Any], *keys: str) -> str:
    """Return the first non-empty manifest text using the canonical field order."""
    for key in keys:
        value = seg.get(key)
        if isinstance(value, str) and value.strip():
            return value
    return ""


def segment_id(seg: dict[str, Any]) -> str:
    primary = str(seg.get("id") or "").strip()
    alias = str(seg.get("segment_id") or "").strip()
    if primary and alias and primary != alias:
        raise ValueError(f"segment id fields disagree: {primary!r} != {alias!r}")
    return primary or alias


def approval_identity(
    *,
    project_id: str,
    language_direction: str,
    segment: dict[str, Any],
) -> str:
    """Hash the exact canonical project, segment, direction, source and target identity."""
    identity = {
        "schema": APPROVAL_IDENTITY_SCHEMA,
        "domain": APPROVAL_IDENTITY_DOMAIN,
        "version": APPROVAL_IDENTITY_VERSION,
        "project_id": str(project_id),
        "segment_id": segment_id(segment),
        "language_direction": str(language_direction),
        "source_text": segment_text(segment, "source", "source_text"),
        "target_text": segment_text(
            segment,
            "draft",
            "draft_text",
            "target_text",
            "translation",
        ),
    }
    canonical = json.dumps(
        identity,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return f"sha256:{hashlib.sha256(canonical).hexdigest()}"


def has_approvable_content(segment: dict[str, Any]) -> bool:
    source = segment_text(segment, "source", "source_text")
    target = segment_text(
        segment,
        "draft",
        "draft_text",
        "target_text",
        "translation",
    )
    return bool(source.strip()) and bool(target.strip())


def is_formally_approved(
    entry: Any,
    current_identity: str,
    *,
    segment: dict[str, Any],
) -> bool:
    return (
        has_approvable_content(segment)
        and isinstance(entry, dict)
        and str(entry.get("status") or "").strip().lower() == "approved"
        and entry.get("approval_identity") == current_identity
    )


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
    with _review_state_lock:
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
    with _review_state_lock:
        state = load_review_state(repo_root)
        projects = state.setdefault("projects", {})
        project = projects.setdefault(project_id, {"segments": {}, "issues": {}})
        seg_map = project.setdefault("segments", {})
        issue_map = project.setdefault("issues", {})
        if segments:
            for seg_id, entry in segments.items():
                if not isinstance(entry, dict):
                    continue
                existing = seg_map.get(str(seg_id))
                prior = existing if isinstance(existing, dict) else {}
                seg_map[str(seg_id)] = {
                    **prior,
                    **entry,
                    "at": entry.get("at") or utc_now(),
                }
        if issues:
            for issue_id, entry in issues.items():
                if not isinstance(entry, dict):
                    continue
                existing = issue_map.get(str(issue_id))
                prior = existing if isinstance(existing, dict) else {}
                issue_map[str(issue_id)] = {
                    **prior,
                    **entry,
                    "at": entry.get("at") or utc_now(),
                }
        save_review_state(repo_root, state)
        return project


def delete_project_review_state(repo_root: Path, project_id: str) -> bool:
    with _review_state_lock:
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
