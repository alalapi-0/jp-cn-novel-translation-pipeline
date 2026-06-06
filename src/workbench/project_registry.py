"""Multi-project manifest registry under workspace/manifests/."""

from __future__ import annotations

import json
import shutil
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from workbench.project_id import (
    InvalidProjectIdError,
    is_history_project_id,
    is_test_project_id,
    project_list_category,
    validate_project_id,
)

MANIFESTS_DIR_NAME = "manifests"
WORKBENCH_STATE_FILE = "workbench_state.json"
LEGACY_MANIFEST_NAME = "project_manifest.json"
EXAMPLE_GLOB = "workbench_project.*.example.json"
_REFRESH_LOCK = threading.Lock()
_project_locks_guard = threading.Lock()
_project_locks: dict[str, threading.Lock] = {}


class ManifestWriteInProgressError(RuntimeError):
    """Raised when another request is already writing the same manifest."""


def _project_write_lock(project_id: str) -> threading.Lock:
    with _project_locks_guard:
        lock = _project_locks.get(project_id)
        if lock is None:
            lock = threading.Lock()
            _project_locks[project_id] = lock
        return lock


@dataclass(frozen=True)
class ProjectManifest:
    project_id: str
    name: str
    language_direction: str
    status: str
    chapters: int
    segments: tuple[dict[str, Any], ...]
    path: Path | None = None

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.project_id,
            "project_id": self.project_id,
            "name": self.name,
            "direction": self.language_direction,
            "language_direction": self.language_direction,
            "status": self.status,
            "chapters": self.chapters,
            "is_test": is_test_project_id(self.project_id),
            "category": project_list_category(self.project_id),
        }

    def to_workbench_payload(self) -> dict[str, Any]:
        return {
            "project": self.to_summary(),
            "segments": list(self.segments),
        }


def manifests_dir(repo_root: Path) -> Path:
    return repo_root / "workspace" / MANIFESTS_DIR_NAME


def workbench_state_path(repo_root: Path) -> Path:
    return repo_root / "workspace" / WORKBENCH_STATE_FILE


def examples_dir(repo_root: Path) -> Path:
    return repo_root / "data" / "examples"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"manifest must be a JSON object: {path}")
    return data


def parse_project_manifest(data: dict[str, Any], *, path: Path | None = None) -> ProjectManifest:
    project_id = str(data.get("project_id") or "").strip()
    if not project_id:
        raise ValueError("manifest missing project_id")
    name = str(data.get("name") or project_id)
    direction = str(data.get("language_direction") or data.get("direction") or "JP_TO_CN")
    status = str(data.get("status") or "unknown")
    chapters_raw = data.get("chapters", 0)
    try:
        chapters = int(chapters_raw)
    except (TypeError, ValueError):
        chapters = 0
    segments_raw = data.get("segments") or []
    if not isinstance(segments_raw, list):
        raise ValueError(f"segments must be a list for {project_id}")
    segments: list[dict[str, Any]] = []
    for item in segments_raw:
        if isinstance(item, dict):
            segments.append(item)
    return ProjectManifest(
        project_id=project_id,
        name=name,
        language_direction=direction,
        status=status,
        chapters=chapters,
        segments=tuple(segments),
        path=path,
    )


def load_project_manifest(path: Path) -> ProjectManifest:
    return parse_project_manifest(_load_json(path), path=path)


def _manifest_project_id(path: Path) -> str | None:
    try:
        return parse_project_manifest(_load_json(path)).project_id
    except (OSError, json.JSONDecodeError, ValueError):
        return None


def list_project_manifest_paths(repo_root: Path) -> list[Path]:
    root = manifests_dir(repo_root)
    if not root.is_dir():
        return []
    paths = sorted(
        p for p in root.glob("*.json") if p.is_file() and p.name != LEGACY_MANIFEST_NAME
    )
    legacy = root / LEGACY_MANIFEST_NAME
    if legacy.is_file():
        legacy_id = _manifest_project_id(legacy)
        named_ids = {_manifest_project_id(p) for p in paths}
        named_ids.discard(None)
        if legacy_id is None or legacy_id not in named_ids:
            paths.append(legacy)
    return paths


def list_project_manifests(
    repo_root: Path,
    *,
    include_test: bool = True,
    include_history: bool = True,
) -> list[ProjectManifest]:
    manifests: list[ProjectManifest] = []
    seen: set[str] = set()
    for path in list_project_manifest_paths(repo_root):
        try:
            manifest = load_project_manifest(path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if manifest.project_id in seen:
            continue
        seen.add(manifest.project_id)
        if not include_test and is_test_project_id(manifest.project_id):
            continue
        if not include_history and is_history_project_id(manifest.project_id):
            continue
        manifests.append(manifest)
    manifests.sort(key=lambda m: m.project_id)
    return manifests


def _read_workbench_state(repo_root: Path) -> dict[str, Any]:
    path = workbench_state_path(repo_root)
    if not path.is_file():
        return {}
    try:
        data = _load_json(path)
    except (OSError, json.JSONDecodeError, ValueError):
        return {}
    return data


def get_active_project_id(repo_root: Path) -> str | None:
    state = _read_workbench_state(repo_root)
    active = str(state.get("active_project_id") or "").strip()
    if active:
        known = {m.project_id for m in list_project_manifests(repo_root)}
        if active in known:
            return active
    manifests = list_project_manifests(repo_root)
    if manifests:
        return manifests[0].project_id
    return None


def set_active_project_id(repo_root: Path, project_id: str) -> ProjectManifest:
    project_id = validate_project_id(project_id)
    match = next((m for m in list_project_manifests(repo_root) if m.project_id == project_id), None)
    if match is None:
        raise KeyError(f"unknown project_id: {project_id}")
    state_path = workbench_state_path(repo_root)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "active_project_id": project_id,
        "updated_at": utc_now(),
    }
    state_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return match


def get_project_manifest(repo_root: Path, project_id: str) -> ProjectManifest | None:
    try:
        project_id = validate_project_id(project_id)
    except InvalidProjectIdError:
        return None
    for manifest in list_project_manifests(repo_root):
        if manifest.project_id == project_id:
            return manifest
    return None


def resolve_active_manifest_path(repo_root: Path) -> Path | None:
    active_id = get_active_project_id(repo_root)
    if not active_id:
        legacy = manifests_dir(repo_root) / LEGACY_MANIFEST_NAME
        return legacy if legacy.is_file() else None
    for path in list_project_manifest_paths(repo_root):
        try:
            manifest = load_project_manifest(path)
        except (OSError, json.JSONDecodeError, ValueError):
            continue
        if manifest.project_id == active_id:
            return path
    legacy = manifests_dir(repo_root) / LEGACY_MANIFEST_NAME
    return legacy if legacy.is_file() else None


def refresh_example_manifests(repo_root: Path) -> list[Path]:
    """Copy committed example manifests into workspace/manifests (overwrite named files)."""
    with _REFRESH_LOCK:
        target_dir = manifests_dir(repo_root)
        target_dir.mkdir(parents=True, exist_ok=True)
        written: list[Path] = []
        for example in sorted(examples_dir(repo_root).glob(EXAMPLE_GLOB)):
            data = _load_json(example)
            project_id = str(data.get("project_id") or example.stem)
            dest = target_dir / f"{project_id}.json"
            tmp = dest.with_suffix(".json.tmp")
            shutil.copyfile(example, tmp)
            tmp.replace(dest)
            written.append(dest)
        return written


def save_project_manifest(repo_root: Path, data: dict[str, Any]) -> ProjectManifest:
    manifest = parse_project_manifest(data)
    target_dir = manifests_dir(repo_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    dest = target_dir / f"{manifest.project_id}.json"
    tmp = dest.with_name(f"{dest.name}.{uuid.uuid4().hex}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(dest)
    return load_project_manifest(dest)


def create_project_manifest(
    repo_root: Path,
    *,
    project_id: str,
    name: str,
    language_direction: str,
    segments: list[dict[str, Any]] | None = None,
) -> ProjectManifest:
    project_id = validate_project_id(project_id)
    if get_project_manifest(repo_root, project_id) is not None:
        raise ValueError(f"project already exists: {project_id}")
    payload = {
        "project_id": project_id,
        "name": name.strip() or project_id,
        "language_direction": language_direction.strip() or "JP_TO_CN",
        "status": "draft_pending",
        "chapters": 1,
        "segments": segments or [],
    }
    return save_project_manifest(repo_root, payload)


def update_project_segments(
    repo_root: Path,
    project_id: str,
    segments: list[dict[str, Any]],
    *,
    status: str | None = None,
) -> ProjectManifest:
    project_id = validate_project_id(project_id)
    lock = _project_write_lock(project_id)
    if not lock.acquire(blocking=False):
        raise ManifestWriteInProgressError(f"manifest write in progress: {project_id}")
    try:
        manifest = get_project_manifest(repo_root, project_id)
        if manifest is None:
            raise KeyError(f"unknown project_id: {project_id}")
        path = manifest.path or (manifests_dir(repo_root) / f"{project_id}.json")
        data = _load_json(path)
        data["segments"] = segments
        if status:
            data["status"] = status
        data["chapters"] = max(int(data.get("chapters") or 1), 1)
        return save_project_manifest(repo_root, data)
    finally:
        lock.release()


def seed_example_manifests(repo_root: Path, *, force: bool = False) -> list[Path]:
    """Copy committed example manifests into workspace/manifests when empty."""
    target_dir = manifests_dir(repo_root)
    target_dir.mkdir(parents=True, exist_ok=True)
    existing = [p for p in target_dir.glob("*.json") if p.name != LEGACY_MANIFEST_NAME]
    if existing and not force:
        return existing
    example_paths = sorted(examples_dir(repo_root).glob(EXAMPLE_GLOB))
    written: list[Path] = []
    for example in example_paths:
        data = _load_json(example)
        project_id = str(data.get("project_id") or example.stem)
        dest = target_dir / f"{project_id}.json"
        if dest.is_file() and not force:
            written.append(dest)
            continue
        shutil.copyfile(example, dest)
        written.append(dest)
    active = get_active_project_id(repo_root)
    if not active and written:
        first = load_project_manifest(written[0])
        set_active_project_id(repo_root, first.project_id)
    return sorted(written)
