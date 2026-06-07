"""Atomic run progress and stage-state helpers for draft/refine pipelines."""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

PROGRESS_SCHEMA_VERSION = 1
VALID_STATUSES = frozenset(
    {"pending", "in_progress", "completed", "failed", "aborted", "blocked"}
)
RECOVERY_LABELS = frozenset(
    {
        "recoverable_in_progress",
        "recoverable_missing_artifacts",
        "completed_consistent",
        "state_conflict",
    }
)

DEFAULT_STAGE_STATE_REL = "workspace/stage_state.json"
PRODUCTION_STAGE_STATE_REL = "workspace/stage_state_production.json"

DIAGNOSTIC_RUN_EXACT = frozenset(
    {
        "round_50_e2e",
        "asset-context-user-verify",
        "asset-context-user-verify-2",
        "fixture_asset_extract_test",
    }
)


def is_diagnostic_run_id(run_id: str) -> bool:
    """Return True for test/diagnostic runs that must not block production resume."""
    rid = (run_id or "").strip()
    if not rid:
        return False
    if rid in DIAGNOSTIC_RUN_EXACT:
        return True
    if rid.startswith("asset-context-"):
        return True
    if rid.startswith("fixture_"):
        return True
    if rid.startswith("draft-a-"):
        return True
    if "realapi_diagnostic" in rid or "diagnostic_translate" in rid:
        return True
    if rid.startswith("micro_validate"):
        return True
    return False


def production_stage_state_path(repo_root: Path) -> Path:
    return repo_root / PRODUCTION_STAGE_STATE_REL


def default_stage_state_path(repo_root: Path) -> Path:
    return repo_root / DEFAULT_STAGE_STATE_REL


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


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


def init_run_metadata(
    run_root: Path,
    *,
    run_id: str,
    phase: str,
    stage: str,
    scope: str,
    chapter_offset: int = 0,
    provider_mode: str = "pending",
    model_name: str = "",
    extra: dict[str, Any] | None = None,
) -> None:
    started = utc_now()
    meta = {
        "run_id": run_id,
        "phase": phase,
        "stage": stage,
        "scope": scope,
        "started_at": started,
        "provider_mode": provider_mode,
        "model_name": model_name,
        "chapter_offset": chapter_offset,
        "summary": {},
    }
    if extra:
        meta.update(extra)
    atomic_write_json(run_root / "run_metadata.json", meta)
    write_run_progress(
        run_root,
        run_id=run_id,
        phase=phase,
        stage=stage,
        chapter_offset=chapter_offset,
        status="pending",
        total_segments=0,
        completed_segments=0,
        pending_segments=0,
        started_at=started,
    )


def write_run_progress(
    run_root: Path,
    *,
    run_id: str,
    phase: str,
    stage: str,
    chapter_offset: int,
    status: str,
    total_segments: int,
    completed_segments: int,
    pending_segments: int | None = None,
    last_completed_segment_id: str = "",
    last_error_type: str = "",
    started_at: str | None = None,
    heartbeat_at: str | None = None,
) -> None:
    if status not in VALID_STATUSES:
        raise ValueError(f"invalid progress status: {status}")
    progress_path = run_root / "run_progress.json"
    existing = safe_load_json(progress_path) or {}
    now = utc_now()
    payload = {
        "schema_version": PROGRESS_SCHEMA_VERSION,
        "run_id": run_id,
        "phase": phase,
        "stage": stage,
        "chapter_offset": chapter_offset,
        "status": status,
        "total_segments": total_segments,
        "completed_segments": completed_segments,
        "pending_segments": (
            pending_segments
            if pending_segments is not None
            else max(0, total_segments - completed_segments)
        ),
        "last_completed_segment_id": last_completed_segment_id,
        "last_error_type": last_error_type,
        "started_at": started_at or existing.get("started_at") or now,
        "heartbeat_at": heartbeat_at or now,
        "updated_at": now,
    }
    atomic_write_json(progress_path, payload)


def safe_load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        if value.endswith("Z"):
            value = value[:-1] + "+00:00"
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def update_stage_state_if_newer(
    repo_root: Path,
    payload: dict[str, Any],
    *,
    run_id: str,
    started_at: str | None = None,
    state_path: Path | None = None,
) -> bool:
    """Write stage_state only if this run is newer than or equal to the active run."""
    path = state_path or (repo_root / "workspace" / "stage_state.json")
    existing = safe_load_json(path) or {}
    existing_run = str(existing.get("run_id") or "")
    existing_started = parse_dt(str(existing.get("updated_at") or existing.get("started_at") or ""))
    new_started = parse_dt(started_at or payload.get("updated_at") or payload.get("started_at") or utc_now())

    if existing_run and existing_run != run_id:
        if existing.get("status") == "in_progress":
            if new_started and existing_started and new_started < existing_started:
                return False

    payload = dict(payload)
    payload.setdefault("updated_at", utc_now())
    payload["run_id"] = run_id
    atomic_write_json(path, payload)
    return True


def classify_run_recovery(
    *,
    run_id: str,
    checkpoint_status: str | None,
    has_run_metadata: bool,
    has_segments: bool,
    has_progress: bool,
    progress_status: str | None,
    segments_consistent: bool | None = None,
) -> str:
    cp = (checkpoint_status or "").split(":", 1)[0]
    if cp == "completed" and has_run_metadata and has_segments and segments_consistent is not False:
        return "completed_consistent"
    if cp == "in_progress" or progress_status == "in_progress":
        if has_run_metadata and has_segments:
            return "recoverable_in_progress"
        return "recoverable_missing_artifacts"
    if cp == "completed" and (not has_segments or not has_run_metadata):
        return "state_conflict"
    if progress_status in {"failed", "aborted", "blocked"}:
        return "state_conflict"
    if has_progress or has_run_metadata:
        return "recoverable_in_progress"
    return "state_conflict"
