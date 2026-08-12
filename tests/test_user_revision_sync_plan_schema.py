from __future__ import annotations

import json
import copy
import sys
from pathlib import Path

import jsonschema
import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from revision_sync.plan import _content_digest_for_plan, build_sync_plan, sha256_bytes, validate_sync_plan

POLICY = json.loads((ROOT / "tests" / "fixtures" / "user_revision_sync" / "policy.json").read_text(encoding="utf-8"))


def _frozen_kwargs():
    return {
        "owner_decisions": POLICY["owner_decisions"],
        "content_policies": POLICY["content_policies"],
    }


def _passed_quality_evidence():
    return {
        name: {"status": "passed", "evidence": f"test-evidence:{name}"}
        for name in (
            "source_hashes_unchanged", "consistency_check", "singleton_revalidated",
            "workspace_baseline_precheck", "schema_validation",
        )
    }


def _schema_validator():
    schema = json.loads((ROOT / "schemas" / "user_revision_sync_plan.schema.json").read_text(encoding="utf-8"))
    return jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())


def _default_plan():
    return build_sync_plan(
        [], [],
        input_hashes={"canonical_sha256": "a" * 64, "revision_sha256": "b" * 64},
        chapter_87_disposition="awaiting_user_no_phase_a_change",
        **_frozen_kwargs(),
    )


def _redigest(plan):
    plan["content_digest"] = _content_digest_for_plan(plan)
    plan["plan_id"] = f"user-revision-sync-{plan['content_digest'][:20]}"
    expected = sha256_bytes(f"{plan['plan_id']}:{plan['content_digest']}:accept".encode("utf-8"))
    plan["apply_authorization"]["exact_plan_acceptance"]["expected_acceptance_token"] = expected
    return plan


def test_generated_plan_is_schema_valid_and_confirmation_gated():
    canonical = [{"chapter_id": "ch-1", "segment_id": "ch-1-seg-001", "source_text": "原文", "target_text": "旧译"}]
    revised = [{"segment_id": "ch-1-seg-001", "source_text": "原文", "target_text": "新译"}]
    plan = build_sync_plan(
        canonical, revised,
        input_hashes={"canonical_sha256": "a" * 64, "revision_sha256": "b" * 64},
        chapter_87_disposition="awaiting_user_no_phase_a_change",
        term_proposals=[{"source_term": "原語", "proposed_target": "术语"}],
        character_proposals=[{"character_id": "sample", "proposed_name": "示例"}],
        classified_decisions=[{"segment_id": "ch-1-seg-001", "classification": "source_supported_polish"}],
        generated_at="2026-08-08T00:00:00+00:00",
        **_frozen_kwargs(),
    )
    schema = json.loads((ROOT / "schemas" / "user_revision_sync_plan.schema.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker()).validate(plan)
    assert plan["status"] == "awaiting_confirmation"
    assert plan["confirmation_required"] is True
    assert plan["side_effects_applied"] is False
    assert "human_approved_final" in plan["forbidden_targets"]
    assert plan["needs_glossary_update"] is True
    assert plan["needs_character_profile_update"] is True
    assert plan["needs_world_bible_update"] is False
    assert plan["needs_style_profile_update"] is True
    assert plan["needs_translation_memory_update"] is True
    assert plan["needs_local_retranslation"] is False
    assert plan["needs_consistency_check"] is True
    assert plan["affects_current_final_export"] is True
    assert set(plan["taxonomy"]["classes"]) == {
        "unchanged_human_polish", "source_supported_polish", "source_inconsistent_change",
        "terminology_only_correction", "formatting_metadata_cleanup", "unresolved_semantic_conflict",
    }
    assert plan["taxonomy"]["counts"]["source_supported_polish"] == 1
    assert plan["taxonomy"]["counts"]["unresolved_semantic_conflict"] == 0
    assert set(plan["forbidden_targets"]) >= {
        "input_jp", "input_zh", "source_text", "human_approved_final",
        "legacy_baseline_body", "draft_full_baseline", "canonical_final_until_confirmed",
        "output_cn/translated/full_volume_cn.md",
    }
    assert "changed_segments" not in plan["material_preview"]
    assert plan["material_preview"]["changed_segment_refs"] == ["ch-1-seg-001"]
    aligned = plan["alignment"]["aligned_segments"][0]
    assert "before_text" not in aligned
    assert "after_text" not in aligned
    assert "source_text" not in aligned
    assert {"before_sha256", "after_sha256", "source_sha256"} <= set(aligned)
    assert all(len(aligned[key]) == 64 for key in ("before_sha256", "after_sha256", "source_sha256"))
    assert aligned["before_normalized_sha256"] != aligned["after_normalized_sha256"]
    assert "before_preview" not in plan["segment_changes"][0]
    assert "after_preview" not in plan["segment_changes"][0]
    assert len(plan["owner_decisions"]) == 9
    assert plan["apply_authorization"]["gates_satisfied"] is False
    assert plan["apply_authorization"]["application_state"] == "forbidden_pending_gates"
    policy = plan["forum_formatting_policy"]
    assert policy["chapter_id"] == "ch-088"
    assert policy["floor_count"] == 57
    assert policy["reply_count"] == 21
    assert policy["first_floor_op_annotation_only"] is True
    assert policy["reply_targets_must_precede_post"] is True
    assert policy["forum_note_once"] is True
    assert policy["afterword_separator_is_system"] is False
    assert policy["preserve_source_order"] is True
    assert "{body}" in policy["render_floor_template"]
    assert "{body}" in policy["render_reply_template"]


def test_default_plan_construction_is_byte_equal_and_uses_unspecified_time_sentinel():
    first = _default_plan()
    second = _default_plan()
    assert first == second
    assert json.dumps(first, ensure_ascii=False, sort_keys=True) == json.dumps(second, ensure_ascii=False, sort_keys=True)
    assert first["generated_at"] == "1970-01-01T00:00:00+00:00"
    _schema_validator().validate(first)


def test_explicit_generated_at_is_preserved_exactly():
    explicit = "2026-08-08T00:00:00+00:00"
    plan = build_sync_plan(
        [], [],
        input_hashes={"canonical_sha256": "a" * 64, "revision_sha256": "b" * 64},
        chapter_87_disposition="awaiting_user_no_phase_a_change",
        generated_at=explicit,
        **_frozen_kwargs(),
    )
    assert plan["generated_at"] == explicit
    _schema_validator().validate(plan)


def test_schema_rejects_judge_readiness_and_gate_forgeries():
    validator = _schema_validator()
    base = _default_plan()
    assert list(validator.iter_errors(base)) == []

    future_without_prerequisites = copy.deepcopy(base)
    future_without_prerequisites["apply_authorization"]["future_apply_candidate_eligible"] = True
    future_without_prerequisites["readiness_gates"]["future_apply_candidate_eligible"] = True

    all_passed_while_not_run = copy.deepcopy(base)
    all_passed_while_not_run["quality_gates"]["all_passed"] = True
    all_passed_while_not_run["readiness_gates"]["validation_complete"] = True

    satisfied_with_null_acceptance = copy.deepcopy(base)
    satisfied_with_null_acceptance["apply_authorization"]["exact_plan_acceptance"]["satisfied"] = True
    satisfied_with_null_acceptance["readiness_gates"]["exact_plan_accepted"] = True

    satisfied_with_malformed_acceptance = copy.deepcopy(satisfied_with_null_acceptance)
    exact = satisfied_with_malformed_acceptance["apply_authorization"]["exact_plan_acceptance"]
    exact["accepted_plan_id"] = "not-a-plan-id"
    exact["accepted_content_digest"] = "not-a-digest"
    exact["acceptance_token"] = "not-a-token"

    duplicated_readiness_mismatch = copy.deepcopy(base)
    duplicated_readiness_mismatch["readiness_gates"]["exact_plan_accepted"] = True

    for forged in (
        future_without_prerequisites,
        all_passed_while_not_run,
        satisfied_with_null_acceptance,
        satisfied_with_malformed_acceptance,
        duplicated_readiness_mismatch,
    ):
        assert list(validator.iter_errors(forged)), forged


def test_schema_rejects_readiness_forged_over_alignment_and_taxonomy_evidence():
    plan = build_sync_plan(
        [
            {"chapter_id": "ch-1", "segment_id": "ch-1-seg-001", "source_text": "s1", "target_text": "one"},
            {"chapter_id": "ch-1", "segment_id": "ch-1-seg-002", "source_text": "s2", "target_text": "two"},
        ],
        [{"chapter_id": "ch-1", "segment_id": "ch-1-seg-001", "source_text": "s1", "target_text": "changed"}],
        input_hashes={"canonical_sha256": "a" * 64, "revision_sha256": "b" * 64},
        chapter_87_disposition="awaiting_user_no_phase_a_change",
        **_frozen_kwargs(),
    )
    forged = copy.deepcopy(plan)
    forged["readiness_gates"]["alignment_complete"] = True
    forged["readiness_gates"]["manual_queue_empty"] = True
    forged["readiness_gates"]["semantic_classification_complete"] = True
    assert forged["alignment"]["summary"]["complete_alignment"] is False
    assert forged["alignment"]["summary"]["manual_item_count"] == 1
    assert forged["taxonomy"]["unclassified_segment_count"] == 1
    assert list(_schema_validator().iter_errors(forged))
    with pytest.raises(ValueError, match="schema validation failed"):
        validate_sync_plan(forged)


def test_semantic_validation_rejects_well_formed_wrong_acceptance_identity():
    confirmed = [{**item, "status": "confirmed"} for item in POLICY["owner_decisions"]]
    common = dict(
        input_hashes={"canonical_sha256": "a" * 64, "revision_sha256": "b" * 64},
        chapter_87_disposition="awaiting_user_no_phase_a_change",
        owner_decisions=confirmed,
        content_policies=POLICY["content_policies"],
        validation_evidence=_passed_quality_evidence(),
    )
    candidate = build_sync_plan([], [], **common)
    exact = candidate["apply_authorization"]["exact_plan_acceptance"]
    authorized = build_sync_plan(
        [], [], **common,
        application_authorization={
            "accepted_plan_id": candidate["plan_id"],
            "accepted_content_digest": candidate["content_digest"],
            "acceptance_token": exact["expected_acceptance_token"],
            "workspace_rebaseline_authorized_current_turn": True,
            "workspace_rebaseline_authorization_evidence": "current-turn test authorization",
        },
    )
    forged = copy.deepcopy(authorized)
    forged_exact = forged["apply_authorization"]["exact_plan_acceptance"]
    forged_exact["accepted_plan_id"] = "user-revision-sync-" + "0" * 20
    forged_exact["accepted_content_digest"] = "1" * 64
    forged_exact["acceptance_token"] = "2" * 64
    # Draft 2020-12 can validate shapes and implications, but cannot compute
    # cryptographic equality between sibling values.
    assert list(_schema_validator().iter_errors(forged)) == []
    with pytest.raises(ValueError, match="cryptographic evidence"):
        validate_sync_plan(forged)

    altered_expected = copy.deepcopy(authorized)
    altered_expected["apply_authorization"]["exact_plan_acceptance"]["expected_acceptance_token"] = "3" * 64
    assert list(_schema_validator().iter_errors(altered_expected)) == []
    with pytest.raises(ValueError, match="expected acceptance token"):
        validate_sync_plan(altered_expected)


def test_builder_rejects_revised_output_override():
    with pytest.raises(ValueError, match="revised_output must remain"):
        build_sync_plan(
            [], [],
            input_hashes={"canonical_sha256": "a" * 64, "revision_sha256": "b" * 64},
            chapter_87_disposition="awaiting_user_no_phase_a_change",
            paths={"revised_output": "workspace/not-full-volume.md"},
            **_frozen_kwargs(),
        )


def test_semantic_validation_rejects_redigested_alignment_change_and_classification_forgeries():
    base = build_sync_plan(
        [{"chapter_id": "ch-1", "segment_id": "ch-1-seg-001", "source_text": "s", "target_text": "old"}],
        [{"chapter_id": "ch-1", "segment_id": "ch-1-seg-001", "source_text": "s", "target_text": "new"}],
        input_hashes={"canonical_sha256": "a" * 64, "revision_sha256": "b" * 64},
        chapter_87_disposition="awaiting_user_no_phase_a_change",
        classified_decisions=[{"segment_id": "ch-1-seg-001", "classification": "source_supported_polish"}],
        **_frozen_kwargs(),
    )
    missing_change = _redigest(copy.deepcopy(base))
    missing_change["segment_changes"] = []
    missing_change["chapter_coverage"]["changed_segment_count"] = 0
    missing_change["chapter_coverage"]["changed_chapters"] = []
    _redigest(missing_change)
    with pytest.raises(ValueError, match="one-to-one"):
        validate_sync_plan(missing_change)

    duplicate_aligned = copy.deepcopy(base)
    duplicate_aligned["alignment"]["aligned_segments"].append(copy.deepcopy(duplicate_aligned["alignment"]["aligned_segments"][0]))
    duplicate_aligned["alignment"]["summary"]["aligned_segment_count"] += 1
    duplicate_aligned["alignment"]["summary"]["modified_segment_count"] += 1
    _redigest(duplicate_aligned)
    with pytest.raises(ValueError, match="aligned segment IDs must be unique"):
        validate_sync_plan(duplicate_aligned)

    duplicate_change = copy.deepcopy(base)
    duplicate_change["segment_changes"].append(copy.deepcopy(duplicate_change["segment_changes"][0]))
    duplicate_change["chapter_coverage"]["changed_segment_count"] += 1
    _redigest(duplicate_change)
    with pytest.raises(ValueError, match="IDs must be unique"):
        validate_sync_plan(duplicate_change)

    duplicate_classification = copy.deepcopy(base)
    duplicate_classification["taxonomy"]["classified_decisions"].append(
        copy.deepcopy(duplicate_classification["taxonomy"]["classified_decisions"][0])
    )
    duplicate_classification["taxonomy"]["counts"]["source_supported_polish"] += 1
    _redigest(duplicate_classification)
    with pytest.raises(ValueError, match="IDs must be unique"):
        validate_sync_plan(duplicate_classification)


def test_semantic_validation_rejects_redigested_modified_segment_relabel_forgery():
    base = build_sync_plan(
        [{"chapter_id": "ch-1", "segment_id": "ch-1-seg-001", "source_text": "s", "target_text": "old"}],
        [{"chapter_id": "ch-1", "segment_id": "ch-1-seg-001", "source_text": "s", "target_text": "new"}],
        input_hashes={"canonical_sha256": "a" * 64, "revision_sha256": "b" * 64},
        chapter_87_disposition="awaiting_user_no_phase_a_change", **_frozen_kwargs(),
    )
    forged = copy.deepcopy(base)
    aligned = forged["alignment"]["aligned_segments"][0]
    assert aligned["before_normalized_sha256"] != aligned["after_normalized_sha256"]
    aligned["change_type"] = "unchanged"
    forged["alignment"]["summary"]["modified_segment_count"] = 0
    forged["alignment"]["summary"]["unchanged_segment_count"] = 1
    forged["segment_changes"] = []
    forged["taxonomy"]["classified_decisions"] = []
    forged["taxonomy"]["unclassified_segment_count"] = 0
    forged["chapter_coverage"]["changed_segment_count"] = 0
    forged["chapter_coverage"]["changed_chapters"] = []
    forged["readiness_gates"]["semantic_classification_complete"] = True
    _redigest(forged)
    with pytest.raises(ValueError, match="change type contradicts normalized fingerprints"):
        validate_sync_plan(forged)


def test_semantic_validation_rejects_redigested_index_and_chapter_coverage_forgeries():
    base = build_sync_plan(
        [
            {"chapter_id": "ch-1", "segment_id": "ch-1-seg-001", "source_text": "s1", "target_text": "one"},
            {"chapter_id": "ch-2", "segment_id": "ch-2-seg-001", "source_text": "s2", "target_text": "two"},
        ],
        [{"chapter_id": "ch-1", "segment_id": "ch-1-seg-001", "source_text": "s1", "target_text": "changed"}],
        input_hashes={"canonical_sha256": "a" * 64, "revision_sha256": "b" * 64},
        chapter_87_disposition="awaiting_user_no_phase_a_change",
        **_frozen_kwargs(),
    )
    wrong_manual_index = copy.deepcopy(base)
    wrong_manual_index["alignment"]["manual_queue"][0]["canonical_index"] = 0
    _redigest(wrong_manual_index)
    with pytest.raises(ValueError, match="canonical indices do not account"):
        validate_sync_plan(wrong_manual_index)

    duplicate_index = copy.deepcopy(base)
    duplicate_index["alignment"]["manual_queue"].append(copy.deepcopy(duplicate_index["alignment"]["manual_queue"][0]))
    duplicate_index["alignment"]["summary"]["manual_item_count"] += 1
    duplicate_index["chapter_coverage"]["manual_item_count"] += 1
    _redigest(duplicate_index)
    with pytest.raises(ValueError, match="manual alignment indices must be unique"):
        validate_sync_plan(duplicate_index)

    wrong_changed_count = copy.deepcopy(base)
    wrong_changed_count["chapter_coverage"]["changed_segment_count"] += 1
    _redigest(wrong_changed_count)
    with pytest.raises(ValueError, match="changed count contradicts"):
        validate_sync_plan(wrong_changed_count)

    wrong_chapters = copy.deepcopy(base)
    wrong_chapters["chapter_coverage"]["changed_chapters"] = ["ch-999"]
    _redigest(wrong_chapters)
    with pytest.raises(ValueError, match="chapters contradict"):
        validate_sync_plan(wrong_chapters)


def test_schema_rejects_claim_that_side_effects_were_applied():
    schema = json.loads((ROOT / "schemas" / "user_revision_sync_plan.schema.json").read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema)
    assert list(validator.iter_errors({"side_effects_applied": True}))


def test_forum_policy_rejects_structural_override():
    with pytest.raises(ValueError, match="overrides are forbidden"):
        build_sync_plan(
            [], [],
            input_hashes={"canonical_sha256": "a" * 64, "revision_sha256": "b" * 64},
            chapter_87_disposition="awaiting_user_no_phase_a_change",
            forum_formatting_policy={"floor_count": 58},
            **_frozen_kwargs(),
        )


def test_forum_templates_and_policy_meanings_are_frozen():
    with pytest.raises(ValueError, match="overrides are forbidden"):
        build_sync_plan(
            [], [], input_hashes={"canonical_sha256": "a" * 64, "revision_sha256": "b" * 64},
            chapter_87_disposition="awaiting_user_no_phase_a_change",
            forum_formatting_policy={"render_floor_template": "DROP_BODY", "render_reply_template": ">> {target_floor}\n{body}"},
            **_frozen_kwargs(),
        )
    altered_decisions = copy.deepcopy(POLICY["owner_decisions"])
    altered_decisions[0]["recommended_default"] = "silently replace protected source"
    with pytest.raises(ValueError, match="meaning must remain frozen"):
        build_sync_plan(
            [], [], input_hashes={"canonical_sha256": "a" * 64, "revision_sha256": "b" * 64},
            chapter_87_disposition="awaiting_user_no_phase_a_change",
            owner_decisions=altered_decisions, content_policies=POLICY["content_policies"],
        )
    altered_policies = {**POLICY["content_policies"], "metadata": "delete_all_content"}
    with pytest.raises(ValueError, match="policy meanings must remain frozen"):
        build_sync_plan(
            [], [], input_hashes={"canonical_sha256": "a" * 64, "revision_sha256": "b" * 64},
            chapter_87_disposition="awaiting_user_no_phase_a_change",
            owner_decisions=POLICY["owner_decisions"], content_policies=altered_policies,
        )


def test_semantic_validation_rejects_redigested_frozen_constant_forgeries():
    for field, value, message in (
        ("format", "DROP_BODY", "schema validation failed|formatting policy must remain frozen"),
        ("decision", "silently replace protected source", "schema validation failed|meaning must remain frozen"),
        ("policy", "delete_all_content", "schema validation failed|policy meanings must remain frozen"),
    ):
        forged = copy.deepcopy(_default_plan())
        if field == "format":
            forged["forum_formatting_policy"]["render_floor_template"] = value
        elif field == "decision":
            forged["owner_decisions"][0]["question"] = value
        else:
            forged["content_policies"]["metadata"] = value
        _redigest(forged)
        with pytest.raises(ValueError, match=message):
            validate_sync_plan(forged)


def test_exact_plan_and_current_turn_rebaseline_gates_are_stable_and_conditional():
    confirmed = [{**item, "status": "confirmed"} for item in POLICY["owner_decisions"]]
    common = dict(
        input_hashes={"canonical_sha256": "a" * 64, "revision_sha256": "b" * 64, "policy_sha256": "c" * 64},
        chapter_87_disposition="awaiting_user_no_phase_a_change",
        owner_decisions=confirmed,
        content_policies=POLICY["content_policies"],
        validation_evidence=_passed_quality_evidence(),
        generated_at="2026-08-08T00:00:00+00:00",
    )
    candidate = build_sync_plan([], [], **common)
    exact = candidate["apply_authorization"]["exact_plan_acceptance"]
    authorized = build_sync_plan(
        [], [], **common,
        application_authorization={
            "accepted_plan_id": candidate["plan_id"],
            "accepted_content_digest": candidate["content_digest"],
            "acceptance_token": exact["expected_acceptance_token"],
            "workspace_rebaseline_authorized_current_turn": True,
            "workspace_rebaseline_authorization_evidence": "current-turn explicit test authorization",
        },
    )
    assert authorized["plan_id"] == candidate["plan_id"]
    assert authorized["content_digest"] == candidate["content_digest"]
    assert authorized["plan_only"] is True
    assert authorized["apply_implementation_available"] is False
    assert authorized["apply_authorization"]["future_apply_candidate_eligible"] is True
    assert authorized["readiness_gates"]["future_apply_candidate_eligible"] is True
    assert authorized["apply_authorization"]["gates_satisfied"] is False
    assert authorized["readiness_gates"]["overall_ready"] is False
    assert authorized["apply_authorization"]["application_state"] == "forbidden_pending_gates"
    assert authorized["side_effects_applied"] is False
    assert authorized["proposed_apply_target"] in authorized["forbidden_targets"]
    validator = _schema_validator()
    validator.validate(authorized)

    all_passed_false_while_every_gate_passed = copy.deepcopy(authorized)
    all_passed_false_while_every_gate_passed["quality_gates"]["all_passed"] = False
    all_passed_false_while_every_gate_passed["readiness_gates"]["validation_complete"] = False
    all_passed_false_while_every_gate_passed["readiness_gates"]["future_apply_candidate_eligible"] = False
    all_passed_false_while_every_gate_passed["apply_authorization"]["future_apply_candidate_eligible"] = False
    assert list(validator.iter_errors(all_passed_false_while_every_gate_passed))


def test_full_user_authorization_cannot_unlock_unresolved_alignment():
    confirmed = [{**item, "status": "confirmed"} for item in POLICY["owner_decisions"]]
    canonical = [
        {"chapter_id": "ch-1", "segment_id": "ch-1-seg-001", "source_text": "s1", "target_text": "old one"},
        {"chapter_id": "ch-1", "segment_id": "ch-1-seg-002", "source_text": "s2", "target_text": "old two"},
    ]
    revised = [{"chapter_id": "ch-1", "segment_id": "ch-1-seg-001", "source_text": "s1", "target_text": "new one"}]
    common = dict(
        input_hashes={"canonical_sha256": "a" * 64, "revision_sha256": "b" * 64},
        chapter_87_disposition="awaiting_user_no_phase_a_change",
        owner_decisions=confirmed, content_policies=POLICY["content_policies"],
        validation_evidence=_passed_quality_evidence(), generated_at="2026-08-08T00:00:00+00:00",
    )
    candidate = build_sync_plan(canonical, revised, **common)
    exact = candidate["apply_authorization"]["exact_plan_acceptance"]
    unresolved = build_sync_plan(
        canonical, revised, **common,
        application_authorization={
            "accepted_plan_id": candidate["plan_id"], "accepted_content_digest": candidate["content_digest"],
            "acceptance_token": exact["expected_acceptance_token"],
            "workspace_rebaseline_authorized_current_turn": True,
            "workspace_rebaseline_authorization_evidence": "current-turn explicit test authorization",
        },
    )
    assert unresolved["apply_authorization"]["exact_plan_acceptance"]["satisfied"] is True
    assert unresolved["apply_authorization"]["workspace_rebaseline"]["satisfied"] is True
    assert unresolved["readiness_gates"]["manual_queue_empty"] is False
    assert unresolved["readiness_gates"]["semantic_classification_complete"] is False
    assert unresolved["apply_authorization"]["gates_satisfied"] is False
    assert unresolved["proposed_apply_target"] in unresolved["forbidden_targets"]

    fabricated = copy.deepcopy(unresolved)
    fabricated["apply_authorization"]["gates_satisfied"] = True
    fabricated["apply_authorization"]["application_state"] = "authorized_not_applied"
    fabricated["apply_authorization"]["owner_decisions_confirmed"] = True
    fabricated["readiness_gates"] = {key: True for key in fabricated["readiness_gates"]}
    fabricated["forbidden_targets"] = [
        item for item in fabricated["forbidden_targets"]
        if item not in {"canonical_final_until_confirmed", fabricated["proposed_apply_target"]}
    ]
    schema = json.loads((ROOT / "schemas" / "user_revision_sync_plan.schema.json").read_text(encoding="utf-8"))
    errors = list(jsonschema.Draft202012Validator(schema).iter_errors(fabricated))
    assert errors
    error_paths = {tuple(error.absolute_path) for error in errors}
    assert any(path[:1] in {("apply_authorization",), ("readiness_gates",)} for path in error_paths)


@pytest.mark.parametrize("forged_token", [None, "0" * 64])
def test_null_or_wrong_acceptance_never_unlocks_plan_only_artifact(forged_token):
    confirmed = [{**item, "status": "confirmed"} for item in POLICY["owner_decisions"]]
    common = dict(
        input_hashes={"canonical_sha256": "a" * 64, "revision_sha256": "b" * 64},
        chapter_87_disposition="awaiting_user_no_phase_a_change",
        owner_decisions=confirmed, content_policies=POLICY["content_policies"],
        validation_evidence=_passed_quality_evidence(), generated_at="2026-08-08T00:00:00+00:00",
    )
    candidate = build_sync_plan([], [], **common)
    forged = build_sync_plan(
        [], [], **common,
        application_authorization={
            "accepted_plan_id": candidate["plan_id"],
            "accepted_content_digest": candidate["content_digest"],
            "acceptance_token": forged_token,
            "workspace_rebaseline_authorized_current_turn": True,
            "workspace_rebaseline_authorization_evidence": "current-turn explicit test authorization",
        },
    )
    assert forged["apply_authorization"]["exact_plan_acceptance"]["satisfied"] is False
    assert forged["apply_authorization"]["future_apply_candidate_eligible"] is False
    assert forged["apply_authorization"]["gates_satisfied"] is False
    assert forged["apply_authorization"]["application_state"] == "forbidden_pending_gates"
    assert forged["proposed_apply_target"] in forged["forbidden_targets"]

    fabricated = copy.deepcopy(forged)
    fabricated["apply_authorization"]["gates_satisfied"] = True
    schema = json.loads((ROOT / "schemas" / "user_revision_sync_plan.schema.json").read_text(encoding="utf-8"))
    assert list(jsonschema.Draft202012Validator(schema).iter_errors(fabricated))


def test_duplicate_classified_segment_ids_are_rejected_before_counting():
    decision = {"segment_id": "ch-1-seg-001", "classification": "source_supported_polish"}
    with pytest.raises(ValueError, match="must be unique"):
        build_sync_plan(
            [{"chapter_id": "ch-1", "segment_id": "ch-1-seg-001", "source_text": "s", "target_text": "old"}],
            [{"chapter_id": "ch-1", "segment_id": "ch-1-seg-001", "source_text": "s", "target_text": "new"}],
            input_hashes={"canonical_sha256": "a" * 64, "revision_sha256": "b" * 64},
            chapter_87_disposition="awaiting_user_no_phase_a_change",
            classified_decisions=[decision, decision], **_frozen_kwargs(),
        )


def test_unclassified_changes_do_not_claim_source_adjudication():
    plan = build_sync_plan(
        [{"chapter_id": "ch-1", "segment_id": "ch-1-seg-001", "source_text": "source", "target_text": "old"}],
        [{"chapter_id": "ch-1", "segment_id": "ch-1-seg-001", "source_text": "source", "target_text": "new"}],
        input_hashes={"canonical_sha256": "a" * 64, "revision_sha256": "b" * 64},
        chapter_87_disposition="awaiting_user_no_phase_a_change", **_frozen_kwargs(),
    )
    assert plan["taxonomy"]["classified_decisions"] == []
    assert all(count == 0 for count in plan["taxonomy"]["counts"].values())
    assert plan["taxonomy"]["unclassified_segment_count"] == 1
    assert plan["segment_changes"][0]["classification"] == "unclassified"
