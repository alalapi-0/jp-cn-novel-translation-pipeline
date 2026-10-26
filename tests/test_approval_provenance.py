"""Approval labels are not evidence of a human or a trusted candidate decision."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from assets.translation_memory import build_translation_memory_assets
from workbench.export_service import run_export
from workbench.project_registry import (
    ApprovalIdentityConflictError, create_project_manifest, patch_project_review_state_cas,
)
from workbench.review_state import (
    approval_identity, get_project_review_state, is_formally_approved, patch_project_review_state,
)


SEGMENT = {"id": "seg-1", "source": "風が吹く。", "draft": "风吹来了。"}


def setup_project(root: Path):
    create_project_manifest(root, project_id="provenance-test", name="Synthetic",
                            language_direction="JP_TO_CN", segments=[dict(SEGMENT)])
    return approval_identity(project_id="provenance-test", language_direction="JP_TO_CN", segment=SEGMENT)


def test_legacy_content_bound_status_stays_unknown_and_readable(tmp_path):
    identity = setup_project(tmp_path)
    entry = {"status": "approved", "approval_identity": identity, "note": "legacy"}
    patch_project_review_state(tmp_path, "provenance-test", segments={"seg-1": entry})
    path = tmp_path / "workspace" / "review_state.json"; before = path.read_bytes()
    loaded = get_project_review_state(tmp_path, "provenance-test")["segments"]["seg-1"]
    assert loaded["status"] == "approved" and loaded["note"] == "legacy"
    assert not is_formally_approved(loaded, identity, segment=SEGMENT)
    for consumer, error in [(lambda: run_export(tmp_path, source="manifest", project_id="provenance-test"), "no approved segments"),
                            (lambda: build_translation_memory_assets(repo_root=tmp_path, project_id="provenance-test"), "no approved translation pairs")]:
        with pytest.raises(ValueError, match=error): consumer()
    assert path.read_bytes() == before


@pytest.mark.parametrize("actor", ["human", "agent", "machine"])
def test_actor_strings_and_final_flags_do_not_supply_provenance(actor):
    identity = approval_identity(project_id="p", language_direction="JP_TO_CN", segment=SEGMENT)
    entry = {"status": "approved", "approval_identity": identity, "actor_type": actor,
             "review_actor_type": actor, "human_reviewed": True, "human_approved_final": True}
    assert not is_formally_approved(entry, identity, segment=SEGMENT)


def test_untrusted_patch_cannot_supply_actor_or_provenance(tmp_path):
    identity = setup_project(tmp_path)
    state = patch_project_review_state_cas(tmp_path, "provenance-test", segments={"seg-1": {
        "status": "approved", "expected_identity": identity, "actor_type": "human",
        "human_approved_final": True, "decision_provenance": {"actor_type": "agent", "identity": identity},
    }})
    entry = state["segments"]["seg-1"]
    assert entry["decision_provenance"]["actor_type"] == "unknown"
    assert "actor_type" not in entry and "human_approved_final" not in entry
    assert not is_formally_approved(entry, identity, segment=SEGMENT)


def test_final_status_is_not_a_supported_untrusted_mutation(tmp_path):
    identity = setup_project(tmp_path)
    with pytest.raises(ApprovalIdentityConflictError):
        patch_project_review_state_cas(tmp_path, "provenance-test", segments={"seg-1": {
            "status": "human_approved_final", "expected_identity": identity}})
    assert get_project_review_state(tmp_path, "provenance-test")["segments"] == {}


def test_legacy_run_approved_label_cannot_bypass_manifest_provenance(tmp_path):
    root = tmp_path / "workspace" / "runs" / "synthetic-run"; root.mkdir(parents=True)
    (root / "segments.json").write_text(json.dumps({"language_direction": "JP_TO_CN", "chapters": [
        {"chapter_id": "1", "segments": [{"segment_id": "seg-1", "source_text": "原文", "draft_text": "译文", "status": "approved"}]}]}))
    with pytest.raises(ValueError, match="no approved translation pairs"):
        build_translation_memory_assets(repo_root=tmp_path, source_run="synthetic-run")


@pytest.mark.parametrize("actor_type", ["agent", "psh_proxy", "machine", "unknown"])
def test_explicit_nonhuman_service_context_and_consumers(tmp_path, actor_type):
    from workbench.review_state import DecisionActor, review_decision_summary
    identity = setup_project(tmp_path)
    state = patch_project_review_state_cas(tmp_path, "provenance-test",
        decision_actor=DecisionActor(actor_type, "synthetic-service-context"),
        segments={"seg-1": {"status": "approved", "expected_identity": identity,
                            "actor_type": "human", "human_approved_final": True}})
    entry = state["segments"]["seg-1"]
    decision = review_decision_summary(entry, identity, segment=SEGMENT)
    assert decision["actor_type"] == actor_type
    assert decision["human_reviewed"] is False and decision["human_approved_final"] is False
    accepted = actor_type in {"agent", "psh_proxy"}
    assert is_formally_approved(entry, identity, segment=SEGMENT) is accepted
    if accepted:
        exported = run_export(tmp_path, source="manifest", project_id="provenance-test")
        assets = build_translation_memory_assets(repo_root=tmp_path, project_id="provenance-test")
        assert exported["acceptance_actor_counts"] == {actor_type: 1}
        for doc in [exported, assets]:
            assert doc["approval_scope"] == "nonhuman_candidate"
            assert doc["human_approved_final"] is False and doc["is_canonical"] is False
        assert assets["approved_pairs"][0]["acceptance_provenance"]["actor_type"] == actor_type
        changed = {**SEGMENT, "draft": "等长异稿。"}
        changed_id = approval_identity(project_id="provenance-test", language_direction="JP_TO_CN", segment=changed)
        assert not is_formally_approved(entry, changed_id, segment=changed)
        assert not is_formally_approved(entry, identity, segment={**SEGMENT, "draft": " "})
        from workbench.project_registry import update_project_segments
        update_project_segments(tmp_path, "provenance-test", [changed])
        with pytest.raises(ValueError, match="no approved segments"):
            run_export(tmp_path, source="manifest", project_id="provenance-test")
        with pytest.raises(ValueError, match="no approved translation pairs"):
            build_translation_memory_assets(repo_root=tmp_path, project_id="provenance-test")
    else:
        with pytest.raises(ValueError, match="no approved segments"):
            run_export(tmp_path, source="manifest", project_id="provenance-test")
        with pytest.raises(ValueError, match="no approved translation pairs"):
            build_translation_memory_assets(repo_root=tmp_path, project_id="provenance-test")


@pytest.mark.parametrize("actor", ["human", "user", "human_approved_final", []])
def test_no_human_or_final_actor_issuer(actor):
    from workbench.review_state import DecisionActor
    with pytest.raises(ValueError): DecisionActor(actor, "untrusted")


@pytest.mark.parametrize("field,value", [("actor_type", "human"), ("actor_type", []),
    ("decision", []), ("human_approved_final", True), ("scope", "final"), ("origin", "client")])
def test_forged_or_malformed_provenance_fails_closed(tmp_path, field, value):
    from workbench.review_state import DecisionActor
    identity = setup_project(tmp_path)
    entry = patch_project_review_state_cas(tmp_path, "provenance-test",
        decision_actor=DecisionActor("agent", "synthetic"),
        segments={"seg-1": {"status": "approved", "expected_identity": identity}})["segments"]["seg-1"]
    entry["decision_provenance"][field] = value
    assert not is_formally_approved(entry, identity, segment=SEGMENT)


def test_metadata_preserves_but_status_mutation_replaces_actor(tmp_path):
    from workbench.review_state import DecisionActor
    identity = setup_project(tmp_path)
    approved = {"status": "approved", "expected_identity": identity}
    patch_project_review_state_cas(tmp_path, "provenance-test", decision_actor=DecisionActor("agent", "synthetic"), segments={"seg-1": approved})
    state = patch_project_review_state_cas(tmp_path, "provenance-test", segments={"seg-1": {"note": "keep", "decision_provenance": {"actor_type": "human"}}})
    assert is_formally_approved(state["segments"]["seg-1"], identity, segment=SEGMENT)
    state = patch_project_review_state_cas(tmp_path, "provenance-test", segments={"seg-1": approved})
    assert state["segments"]["seg-1"]["decision_provenance"]["actor_type"] == "unknown"
    assert not is_formally_approved(state["segments"]["seg-1"], identity, segment=SEGMENT)
