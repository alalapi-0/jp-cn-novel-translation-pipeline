"""Dedicated review state persisted under workspace/review_state.json."""

from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REVIEW_STATE_FILE = "review_state.json"
APPROVAL_IDENTITY_SCHEMA = "segment_approval_identity"
APPROVAL_IDENTITY_DOMAIN = "light-novel.workbench.segment-approval"
APPROVAL_IDENTITY_VERSION = 1
_review_state_lock = threading.Lock()


class ReviewStateConflictError(RuntimeError):
    """The project review preimage changed before its atomic update."""

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
