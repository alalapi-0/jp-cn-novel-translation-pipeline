"""Dedicated review state persisted under workspace/review_state.json."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import sys
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REVIEW_STATE_FILE = "review_state.json"
REVIEW_STATE_MAX_BYTES = 64 * 1024 * 1024
APPROVAL_IDENTITY_SCHEMA = "segment_approval_identity"
APPROVAL_IDENTITY_DOMAIN = "light-novel.workbench.segment-approval"
APPROVAL_IDENTITY_VERSION = 1
_review_state_lock = threading.Lock()


class ReviewStateConflictError(RuntimeError):
    """The project review preimage changed before its atomic update."""


class ReviewStateUnavailableError(Exception):
    """Review state cannot be safely read; details must not be sent to clients."""

    def __init__(self) -> None:
        super().__init__("审核状态暂不可用；请检查后重试。")


@dataclass(frozen=True)
class ReviewStateSnapshot:
    state: dict[str, Any]
    identity: tuple[Any, ...]

DECISION_SCHEMA = "workbench-review-decision/1"
_ACTOR_TYPES = {"unknown", "machine", "agent", "psh_proxy"}
_DECISION_KEYS = {"schema", "origin", "actor_type", "actor_ref", "approval_identity",
                  "decision", "scope", "human_approved_final"}
UNTRUSTED_APPROVAL_FIELDS = {
    "expected_identity", "approval_identity", "decision_provenance", "decision_actor",
    "actor", "actor_type", "review_actor_type", "approved_by", "approved_by_user",
    "human_reviewed", "human_approved_final", "approval_state", "approval_scope",
    "final_approval", "decision_summary",
}


@dataclass(frozen=True)
class DecisionActor:
    """Trusted local caller context, never parsed from HTTP or a saved label.

    This records nonhuman service attribution, not an authenticated human proof.
    No human or final-approval issuer exists in this interface.
    """
    actor_type: str
    actor_ref: str

    def __post_init__(self) -> None:
        if not isinstance(self.actor_type, str) or self.actor_type not in _ACTOR_TYPES:
            raise ValueError("human/final actor issuance is unsupported")
        if not isinstance(self.actor_ref, str) or not self.actor_ref.strip():
            raise ValueError("actor_ref is required")


def decision_provenance(identity: str, status: str, actor: DecisionActor | None) -> dict[str, Any]:
    if actor is not None and not isinstance(actor, DecisionActor):
        raise ValueError("decision actor must be trusted local service context")
    actor = actor or DecisionActor("unknown", "unverified_workbench_request")
    decision = status
    if status == "approved":
        decision = ("accepted" if actor.actor_type in {"agent", "psh_proxy"}
                    else "machine_suggestion" if actor.actor_type == "machine" else "unverified_claim")
    return {"schema": DECISION_SCHEMA, "origin": "workbench_identity_cas",
            "actor_type": actor.actor_type, "actor_ref": actor.actor_ref,
            "approval_identity": identity,
            "decision": decision,
            "scope": "nonhuman_candidate", "human_approved_final": False}


def review_decision_summary(entry: Any, current_identity: str, *, segment: dict[str, Any]) -> dict[str, Any]:
    """Read-only compatibility projection; never upgrades or rewrites legacy data."""
    entry = entry if isinstance(entry, dict) else {}
    p = entry.get("decision_provenance")
    valid = (isinstance(p, dict) and set(p) == _DECISION_KEYS
             and p.get("schema") == DECISION_SCHEMA and p.get("origin") == "workbench_identity_cas"
             and isinstance(p.get("actor_type"), str) and p["actor_type"] in _ACTOR_TYPES
             and isinstance(p.get("actor_ref"), str)
             and bool(p["actor_ref"].strip()) and p.get("scope") == "nonhuman_candidate"
             and p.get("human_approved_final") is False
             and isinstance(p.get("decision"), str)
             and p["decision"] in {"accepted", "machine_suggestion", "unverified_claim", "rejected", "pending"})
    bound = entry.get("approval_identity") == current_identity
    provenance_bound = valid and p.get("approval_identity") == current_identity
    actor_type = p["actor_type"] if valid else "unknown"
    accepted = bool(has_approvable_content(segment) and bound and provenance_bound
                    and str(entry.get("status") or "").strip().lower() == "approved"
                    and p["decision"] == "accepted" and actor_type in {"agent", "psh_proxy"})
    return {"actor_type": actor_type, "candidate_accepted": accepted,
            "provenance_status": "current" if provenance_bound else "stale" if valid else "unknown",
            "approval_identity_matches": bound, "scope": "nonhuman_candidate",
            "human_reviewed": False, "human_approved_final": False}


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
    from translation.source_versions import review_dependencies
    dependencies = review_dependencies(segment, identity['source_text'])
    if dependencies:
        identity['version'] = 2
        identity['dependencies'] = dependencies
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
    # Compatibility name: this authorizes a Workbench candidate, never human final.
    return review_decision_summary(entry, current_identity, segment=segment)["candidate_accepted"]


def _empty_state() -> dict[str, Any]:
    return {"version": 1, "projects": {}, "updated_at": utc_now()}


def _read_review_bytes(repo_root: Path) -> tuple[bytes | None, tuple[Any, ...]]:
    """Read the inode selected by a no-link open; directory containment is at open time."""
    from assets.translation_memory import _open_at2

    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise ValueError("secure review reads are unavailable")
    if ".." in Path(repo_root).parts:
        raise ValueError("review root is not a stable path")
    fds: list[int] = []
    try:
        anchor = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        fds.append(anchor)
        absolute = os.path.abspath(os.fspath(repo_root))
        # Acquiring the configured repo root may cross a mount, but never a
        # symlink or magic link. All paths below the root prohibit mounts too.
        root = _open_at2(anchor, Path(absolute.lstrip("/")), resolve=0x0E)
        fds.append(root)
        root_stat = os.fstat(root)
        if not stat.S_ISDIR(root_stat.st_mode):
            raise ValueError("review root unavailable")
        workspace = _open_at2(root, Path("workspace"), resolve=0x0F)
        fds.append(workspace)
        workspace_stat = os.fstat(workspace)
        if not stat.S_ISDIR(workspace_stat.st_mode):
            raise ValueError("review workspace unavailable")
        directory_identity = (root_stat.st_dev, root_stat.st_ino,
                              workspace_stat.st_dev, workspace_stat.st_ino)
        try:
            leaf = _open_at2(workspace, Path(REVIEW_STATE_FILE), resolve=0x0F)
        except FileNotFoundError:
            return None, (*directory_identity, None)
        fds.append(leaf)
        before = os.fstat(leaf)
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or before.st_size > REVIEW_STATE_MAX_BYTES:
            raise ValueError("review state is not a bounded uniquely linked regular file")
        content = bytearray()
        while True:
            chunk = os.read(leaf, min(65536, REVIEW_STATE_MAX_BYTES + 1 - len(content)))
            if not chunk:
                break
            content.extend(chunk)
            if len(content) > REVIEW_STATE_MAX_BYTES:
                raise ValueError("review state exceeds limit")
        after = os.fstat(leaf)
        def identity(value: os.stat_result) -> tuple[int, ...]:
            return (value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
                    value.st_size, value.st_mtime_ns, value.st_ctime_ns)
        if identity(before) != identity(after) or len(content) != before.st_size:
            raise ValueError("review state changed during read")
        raw = bytes(content)
        return raw, (*directory_identity, identity(before), hashlib.sha256(raw).hexdigest())
    finally:
        pending = sys.exc_info()[1]
        failures = []
        for fd in reversed(fds):
            try:
                os.close(fd)
            except OSError as error:
                failures.append(error)
        if failures:
            if pending is not None:
                raise BaseExceptionGroup("review read and cleanup failed", [pending, *failures]) from None
            if len(failures) == 1:
                raise failures[0]
            raise ExceptionGroup("review cleanup failed", failures)


def read_review_state_snapshot(repo_root: Path) -> ReviewStateSnapshot:
    """Validate a bounded snapshot; only a missing leaf is an empty state."""
    try:
        raw, identity = _read_review_bytes(repo_root)
        if raw is None:
            return ReviewStateSnapshot(_empty_state(), identity)
        def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
            result = {}
            for key, value in pairs:
                if key in result:
                    raise ValueError("ambiguous review state")
                result[key] = value
            return result
        def invalid_constant(_value: str) -> None:
            raise ValueError("invalid review state number")
        data = json.loads(raw.decode("utf-8"), object_pairs_hook=unique_object, parse_constant=invalid_constant)
        if not isinstance(data, dict) or type(data.get("version", 1)) is not int or data.get("version", 1) != 1:
            raise ValueError("unsupported review state structure")
        projects = data.get("projects", {})
        if not isinstance(projects, dict):
            raise ValueError("unsupported review state structure")
        for project in projects.values():
            if not isinstance(project, dict):
                raise ValueError("unsupported review state structure")
            for key in ("segments", "issues"):
                entries = project.get(key, {})
                if not isinstance(entries, dict) or any(not isinstance(entry, dict) for entry in entries.values()):
                    raise ValueError("unsupported review state structure")
    except Exception as error:
        raise ReviewStateUnavailableError() from error
    data.setdefault("version", 1)
    data.setdefault("projects", {})
    return ReviewStateSnapshot(data, identity)


def load_review_state(repo_root: Path) -> dict[str, Any]:
    return read_review_state_snapshot(repo_root).state


def save_review_state(repo_root: Path, state: dict[str, Any]) -> None:
    path = review_state_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = utc_now()
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def get_project_review_snapshot(repo_root: Path, project_id: str) -> tuple[dict[str, Any], tuple[Any, ...]]:
    with _review_state_lock:
        snapshot = read_review_state_snapshot(repo_root)
        state = snapshot.state
        projects = state.setdefault("projects", {})
        project = projects.setdefault(project_id, {"segments": {}, "issues": {}})
        project.setdefault("segments", {})
        project.setdefault("issues", {})
        return project, snapshot.identity


def get_project_review_state(repo_root: Path, project_id: str) -> dict[str, Any]:
    return get_project_review_snapshot(repo_root, project_id)[0]


def patch_project_review_state(
    repo_root: Path,
    project_id: str,
    *,
    segments: dict[str, Any] | None = None,
    issues: dict[str, Any] | None = None,
    _expected_review_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    with _review_state_lock:
        state = load_review_state(repo_root)
        projects = state.setdefault("projects", {})
        project = projects.setdefault(project_id, {"segments": {}, "issues": {}})
        # Lock order: project manifest lock (if held by caller), then this review
        # lock. Compare and persist under ONE review critical section. Other
        # projects need not hold a manifest lock, but cannot enter this gap.
        if _expected_review_state is not None and project != _expected_review_state:
            raise ReviewStateConflictError('review changed before atomic update; preserved current feedback')
        seg_map = project.setdefault("segments", {})
        issue_map = project.setdefault("issues", {})
        if segments:
            for seg_id, entry in segments.items():
                if not isinstance(entry, dict):
                    continue
                existing = seg_map.get(str(seg_id))
                prior = existing if isinstance(existing, dict) else {}
                merged = {
                    **prior,
                    **entry,
                    "at": entry.get("at") or utc_now(),
                }
                if "status" in entry and "decision_provenance" not in entry:
                    merged.pop("decision_provenance", None)
                seg_map[str(seg_id)] = merged
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
