"""Construct confirmation-gated user revision synchronization plans."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any, Mapping, Sequence

import jsonschema

from .aligner import align_revisions, normalize_text

FORBIDDEN_TARGETS = [
    "input_jp", "input_zh", "source_text", "human_approved_final",
    "legacy_baseline_body", "draft_full_baseline",
]
TAXONOMY_CLASSES = [
    "unchanged_human_polish", "source_supported_polish", "source_inconsistent_change",
    "terminology_only_correction", "formatting_metadata_cleanup", "unresolved_semantic_conflict",
]
DEFAULT_PATHS = {
    "source_dir": "input_jp",
    "revision_dir": "artifacts/wechat_published_text/chapters",
    "canonical_full_volume": "output_cn/translated/full_volume_cn.md",
    "glossary": "configs/glossary.yaml",
    "character_profile": "configs/character_profile.yaml",
    "prompt": "prompts/user_revision_reconciliation.md",
    "report_target": "artifacts/user_revision_sync/ch001_086_sync_plan.json",
    "revised_output": "output_cn/translated/full_volume_cn.md",
    "local_fix_plan": "workspace/consistency_audit/local_fix_plan.json",
    "audit_report": "reports/user_revision_sync_audit.json",
}
FROZEN_OWNER_DECISIONS = [
    ("homunculus_exact_spelling", "Confirm exact Homunculus spelling?", "Preserve the owner-provided spelling.", ["Homunculus"], ["ch-001"]),
    ("homunculus_annotation_rule", "Confirm the first-use annotation rule?", "Annotate once after confirmation.", ["Homunculus"], ["ch-001"]),
    ("chapter_087_disposition", "Confirm the separate long-term treatment of chapter 87?", "Exclude and leave unchanged, pending explicit user confirmation.", [], ["ch-087"]),
    ("handle_hana_eleboo", "Confirm the Hana Eleboo handle mapping?", "Keep the mapping unresolved.", ["hana_eleboo"], ["ch-001"]),
    ("handle_omiotsukenai", "Confirm the Omiotsukenai handle mapping?", "Keep the mapping unresolved.", ["omiotsukenai"], ["ch-001"]),
    ("duplicate_arafubuki", "Confirm duplicate Arafubuki handling?", "Do not merge without confirmation.", ["arafubuki"], ["ch-001"]),
    ("handle_peikouken", "Confirm the Peikouken handle mapping?", "Keep the mapping unresolved.", ["peikouken"], ["ch-001"]),
    ("handle_maa_chan", "Confirm the Maa-chan handle mapping?", "Keep the mapping unresolved.", ["maa_chan"], ["ch-001"]),
    ("handle_kouki", "Confirm the Kouki handle mapping?", "Keep the mapping unresolved.", ["kouki"], ["ch-001"]),
]
FROZEN_CONTENT_POLICIES = {
    "player_and_forum_names": "owner_confirmation_required",
    "same_source_skill_name": "preserve_one_canonical_name",
    "great_work": "preserve_owner_polish",
    "philosophers_egg": "preserve_exact_spelling_after_confirmation",
    "metadata": "remove_transport_metadata_only",
    "human_polish": "retain_when_source_consistent",
    "punctuation": "normalize_without_semantic_change",
}
FROZEN_FORUM_FORMATTING_POLICY = {
    "preserve_paragraph_boundaries": True, "preserve_dialogue_markers": True,
    "normalize_for_alignment_only": True, "destructive_reflow": False,
    "chapter_id": "ch-088", "floor_count": 57, "reply_count": 21,
    "first_floor_op_annotation_only": True, "reply_targets_must_precede_post": True,
    "render_floor_template": "{floor_label}\n{body}",
    "render_reply_template": ">> {target_floor}\n{body}",
    "forum_note_once": True, "afterword_separator_is_system": False,
    "preserve_source_order": True,
}
QUALITY_GATE_NAMES = {
    "source_hashes_unchanged",
    "consistency_check",
    "singleton_revalidated",
    "workspace_baseline_precheck",
    "schema_validation",
}
# Plan construction is deterministic when the caller has no observation time.
# This epoch sentinel means "unspecified"; it is not campaign evidence.
DEFAULT_GENERATED_AT = "1970-01-01T00:00:00+00:00"
FIXED_REVISED_OUTPUT = "output_cn/translated/full_volume_cn.md"
SCHEMA_PATH = Path(__file__).resolve().parents[2] / "schemas" / "user_revision_sync_plan.schema.json"
_POST_DIGEST_FIELDS = {
    "plan_id", "content_digest", "proposed_apply_target", "readiness_gates",
    "apply_authorization", "forbidden_targets",
}


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _fingerprint(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def _chapter_id(record: Mapping[str, Any]) -> str:
    if record.get("chapter_id"):
        return str(record["chapter_id"])
    match = re.match(r"^(ch[-_]?\d+)", str(record.get("segment_id") or ""), flags=re.IGNORECASE)
    return match.group(1).replace("_", "-").lower() if match else "unknown"


def _content_digest_for_plan(plan: Mapping[str, Any]) -> str:
    digest_payload = {
        key: value
        for key, value in plan.items()
        if key not in {"generated_at", "input_hashes", *_POST_DIGEST_FIELDS}
    }
    digest_payload["input_hashes"] = {
        key: value for key, value in plan["input_hashes"].items() if key != "policy_sha256"
    }
    return sha256_bytes(
        json.dumps(digest_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    )


def validate_sync_plan(plan: Mapping[str, Any]) -> None:
    """Validate schema-expressible structure plus computed semantic relationships.

    JSON Schema checks local shapes and declarative boolean implications. This
    function additionally verifies counts, sibling equality, and cryptographic
    identities that Draft 2020-12 cannot compute.
    """
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = jsonschema.Draft202012Validator(schema, format_checker=jsonschema.FormatChecker())
    errors = sorted(validator.iter_errors(plan), key=lambda error: list(error.absolute_path))
    if errors:
        first = errors[0]
        location = ".".join(str(part) for part in first.absolute_path) or "<root>"
        raise ValueError(f"sync plan schema validation failed at {location}: {first.message}")

    expected_digest = _content_digest_for_plan(plan)
    expected_plan_id = f"user-revision-sync-{expected_digest[:20]}"
    expected_token = sha256_bytes(f"{expected_plan_id}:{expected_digest}:accept".encode("utf-8"))
    if plan["content_digest"] != expected_digest or plan["plan_id"] != expected_plan_id:
        raise ValueError("sync plan identity does not match its content")
    exact = plan["apply_authorization"]["exact_plan_acceptance"]
    if exact["expected_acceptance_token"] != expected_token:
        raise ValueError("expected acceptance token does not match plan identity")
    exact_evidence_matches = (
        exact["accepted_plan_id"] == expected_plan_id
        and exact["accepted_content_digest"] == expected_digest
        and exact["acceptance_token"] == expected_token
    )
    if exact["satisfied"] is not exact_evidence_matches:
        raise ValueError("exact plan acceptance does not match its cryptographic evidence")

    alignment = plan["alignment"]
    summary = alignment["summary"]
    taxonomy = plan["taxonomy"]
    quality = plan["quality_gates"]
    readiness = plan["readiness_gates"]
    authorization = plan["apply_authorization"]
    rebaseline = authorization["workspace_rebaseline"]
    aligned = alignment["aligned_segments"]
    manual = alignment["manual_queue"]
    canonical_count = summary["canonical_segment_count"]
    revision_count = summary["revision_segment_count"]
    aligned_ids = [item["segment_id"] for item in aligned]
    canonical_indices = [item["canonical_index"] for item in aligned]
    revision_indices = [item["revision_index"] for item in aligned]
    if len(aligned_ids) != len(set(aligned_ids)):
        raise ValueError("aligned segment IDs must be unique")
    if len(canonical_indices) != len(set(canonical_indices)) or len(revision_indices) != len(set(revision_indices)):
        raise ValueError("aligned canonical and revision indices must be unique")
    if any(index >= canonical_count for index in canonical_indices) or any(index >= revision_count for index in revision_indices):
        raise ValueError("aligned index exceeds declared summary count")
    for item in aligned:
        hashes_equal = item["before_normalized_sha256"] == item["after_normalized_sha256"]
        expected_change_type = "unchanged" if hashes_equal else "modified"
        if item["change_type"] != expected_change_type:
            raise ValueError("aligned change type contradicts normalized fingerprints")
    unmatched_canonical: list[int] = []
    unmatched_revision: list[int] = []
    manual_ids: list[str] = []
    for item in manual:
        if item["kind"] == "unmatched_canonical":
            if "canonical_index" not in item or "revision_index" in item or "canonical_segment_id" not in item:
                raise ValueError("unmatched canonical evidence has contradictory indices")
            unmatched_canonical.append(item["canonical_index"])
            manual_ids.append(item["canonical_segment_id"])
        elif item["kind"] == "unmatched_revision":
            if "revision_index" not in item or "canonical_index" in item or "canonical_segment_id" in item:
                raise ValueError("unmatched revision evidence has contradictory indices")
            unmatched_revision.append(item["revision_index"])
    if len(unmatched_canonical) != len(set(unmatched_canonical)) or len(unmatched_revision) != len(set(unmatched_revision)):
        raise ValueError("manual alignment indices must be unique")
    if len(manual_ids) != len(set(manual_ids)) or set(manual_ids) & set(aligned_ids):
        raise ValueError("manual and aligned canonical segment IDs must be unique")
    if set(canonical_indices) | set(unmatched_canonical) != set(range(canonical_count)):
        raise ValueError("canonical indices do not account for the declared segment count")
    if set(revision_indices) | set(unmatched_revision) != set(range(revision_count)):
        raise ValueError("revision indices do not account for the declared segment count")
    expected_summary_counts = {
        "aligned_segment_count": len(aligned),
        "unchanged_segment_count": sum(item["change_type"] == "unchanged" for item in aligned),
        "modified_segment_count": sum(item["change_type"] == "modified" for item in aligned),
        "manual_item_count": len(manual),
    }
    if any(summary[name] != value for name, value in expected_summary_counts.items()):
        raise ValueError("alignment summary counts contradict alignment evidence")
    complete_alignment = (
        len(aligned) == summary["canonical_segment_count"] == summary["revision_segment_count"]
        and not manual
    )
    if summary["complete_alignment"] is not complete_alignment:
        raise ValueError("alignment completion flag contradicts alignment evidence")
    if plan["chapter_coverage"]["manual_item_count"] != len(manual):
        raise ValueError("chapter coverage manual count contradicts alignment evidence")
    if plan["chapter_coverage"]["aligned_segment_count"] != len(aligned):
        raise ValueError("chapter coverage aligned count contradicts alignment evidence")

    classified = taxonomy["classified_decisions"]
    segment_changes = plan["segment_changes"]
    change_ids = [item["segment_id"] for item in segment_changes]
    classified_ids = [item["segment_id"] for item in classified]
    if len(change_ids) != len(set(change_ids)) or len(classified_ids) != len(set(classified_ids)):
        raise ValueError("segment change and classified decision IDs must be unique")
    modified_by_id = {item["segment_id"]: item for item in aligned if item["change_type"] == "modified"}
    if set(change_ids) != set(modified_by_id):
        raise ValueError("segment changes must correspond one-to-one with modified aligned segments")
    for change in segment_changes:
        aligned_item = modified_by_id[change["segment_id"]]
        for name in (
            "chapter_id", "change_type", "alignment_method", "confidence",
            "before_sha256", "after_sha256", "before_normalized_sha256", "after_normalized_sha256",
            "before_length", "after_length",
        ):
            if change[name] != aligned_item[name]:
                raise ValueError(f"segment change {name} contradicts aligned evidence")
    if not set(classified_ids) <= set(change_ids):
        raise ValueError("classified decisions must reference modified segment changes")
    classification_by_id = {item["segment_id"]: item["classification"] for item in classified}
    if any(
        change["classification"] != classification_by_id.get(change["segment_id"], "unclassified")
        for change in segment_changes
    ):
        raise ValueError("segment classifications contradict classified decision evidence")
    expected_taxonomy_counts = {name: 0 for name in TAXONOMY_CLASSES}
    for item in classified:
        expected_taxonomy_counts[item["classification"]] += 1
    if taxonomy["counts"] != expected_taxonomy_counts:
        raise ValueError("taxonomy counts contradict classified decision evidence")
    actual_unclassified = sum(item["classification"] == "unclassified" for item in segment_changes)
    if taxonomy["unclassified_segment_count"] != actual_unclassified:
        raise ValueError("unclassified count contradicts segment change evidence")
    actual_quality_all_passed = all(quality[name]["passed"] is True for name in QUALITY_GATE_NAMES)
    if quality["all_passed"] is not actual_quality_all_passed:
        raise ValueError("quality aggregate contradicts named gate evidence")
    expected = {
        "alignment_complete": complete_alignment,
        "manual_queue_empty": not manual,
        "semantic_classification_complete": (
            actual_unclassified == 0
            and set(classified_ids) == set(change_ids)
            and all(item["classification"] != "unclassified" for item in segment_changes)
        ),
        "owner_decisions_confirmed": all(item["status"] == "confirmed" for item in plan["owner_decisions"]),
        "exact_plan_accepted": exact_evidence_matches,
        "workspace_rebaseline_authorized_current_turn": (
            rebaseline["authorized_current_turn"] is True
            and rebaseline["satisfied"] is True
            and isinstance(rebaseline["authorization_evidence"], str)
            and bool(rebaseline["authorization_evidence"].strip())
        ),
        "validation_complete": actual_quality_all_passed,
    }
    for name, value in expected.items():
        if readiness[name] is not value:
            raise ValueError(f"readiness gate {name} contradicts plan evidence")
    if authorization["owner_decisions_confirmed"] is not expected["owner_decisions_confirmed"]:
        raise ValueError("apply authorization owner decision flag contradicts plan evidence")
    future_eligible = all(expected.values())
    if readiness["future_apply_candidate_eligible"] is not future_eligible:
        raise ValueError("readiness future eligibility contradicts prerequisite evidence")
    if authorization["future_apply_candidate_eligible"] is not future_eligible:
        raise ValueError("apply authorization future eligibility contradicts prerequisite evidence")
    if plan["paths"]["revised_output"] != FIXED_REVISED_OUTPUT or plan["proposed_apply_target"] != FIXED_REVISED_OUTPUT:
        raise ValueError("proposed apply target must remain the fixed full-volume output")
    if plan["forum_formatting_policy"] != FROZEN_FORUM_FORMATTING_POLICY:
        raise ValueError("forum formatting policy must remain frozen")
    _validate_frozen_policy(plan["owner_decisions"], plan["content_policies"])
    coverage = plan["chapter_coverage"]
    expected_chapters = sorted({item["chapter_id"] for item in segment_changes} | {item["chapter_id"] for item in manual})
    if coverage["changed_segment_count"] != len(segment_changes):
        raise ValueError("chapter coverage changed count contradicts segment changes")
    if coverage["changed_chapters"] != expected_chapters:
        raise ValueError("chapter coverage chapters contradict change and manual evidence")


def _validate_frozen_policy(
    owner_decisions: Sequence[Mapping[str, Any]],
    content_policies: Mapping[str, Any] | None,
) -> dict[str, Any]:
    required_fields = {
        "id", "question", "recommended_default", "status", "affected_terms", "affected_chapters",
    }
    if len(owner_decisions) != len(FROZEN_OWNER_DECISIONS):
        raise ValueError("owner decisions must contain the nine frozen decisions in canonical order")
    for decision, frozen in zip(owner_decisions, FROZEN_OWNER_DECISIONS):
        missing = sorted(required_fields - set(decision))
        if missing or decision.get("status") not in {"awaiting_user", "confirmed"}:
            raise ValueError(f"invalid owner decision {decision.get('id', '<unknown>')}: missing={missing}")
        expected = {
            "id": frozen[0], "question": frozen[1], "recommended_default": frozen[2],
            "affected_terms": frozen[3], "affected_chapters": frozen[4],
        }
        if any(decision.get(name) != value for name, value in expected.items()):
            raise ValueError(f"owner decision meaning must remain frozen: {frozen[0]}")
    policies = dict(content_policies or {})
    if policies != FROZEN_CONTENT_POLICIES:
        raise ValueError("content policy meanings must remain frozen")
    return policies


def _build_quality_gates(validation_evidence: Mapping[str, Any] | None) -> dict[str, Any]:
    supplied = dict(validation_evidence or {})
    unknown = sorted(set(supplied) - QUALITY_GATE_NAMES)
    if unknown:
        raise ValueError(f"unknown validation evidence gates: {unknown}")
    gates: dict[str, Any] = {}
    for name in sorted(QUALITY_GATE_NAMES):
        item = dict(supplied.get(name, {}))
        status = item.get("status", "not_run")
        evidence = item.get("evidence")
        if status not in {"not_run", "passed", "failed"}:
            raise ValueError(f"invalid validation status for {name}: {status}")
        if status != "not_run" and (not isinstance(evidence, str) or not evidence.strip()):
            raise ValueError(f"validation gate {name} requires non-empty evidence when {status}")
        if status == "not_run" and evidence is not None:
            raise ValueError(f"validation gate {name} must not carry evidence when not_run")
        gates[name] = {"status": status, "evidence": evidence, "passed": status == "passed"}
    gates["all_passed"] = all(item["passed"] for item in gates.values())
    return gates


def build_sync_plan(
    canonical_segments: Sequence[Mapping[str, Any]],
    revised_segments: Sequence[Mapping[str, Any]],
    *,
    input_hashes: Mapping[str, str],
    chapter_87_disposition: str,
    term_proposals: Sequence[Mapping[str, Any]] = (),
    character_proposals: Sequence[Mapping[str, Any]] = (),
    classified_decisions: Sequence[Mapping[str, Any]] = (),
    forum_formatting_policy: Mapping[str, Any] | None = None,
    paths: Mapping[str, Any] | None = None,
    owner_decisions: Sequence[Mapping[str, Any]] = (),
    content_policies: Mapping[str, Any] | None = None,
    application_authorization: Mapping[str, Any] | None = None,
    validation_evidence: Mapping[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build a declarative sync plan. No filesystem or external effect occurs."""
    if not chapter_87_disposition.startswith("awaiting_user_no_phase_a_change"):
        raise ValueError("chapter_87_disposition must remain awaiting_user_no_phase_a_change")
    supplied_paths = dict(paths or {})
    unknown_paths = sorted(set(supplied_paths) - set(DEFAULT_PATHS))
    if unknown_paths:
        raise ValueError(f"unknown sync-plan path keys: {unknown_paths}")
    if supplied_paths.get("revised_output", FIXED_REVISED_OUTPUT) != FIXED_REVISED_OUTPUT:
        raise ValueError("revised_output must remain output_cn/translated/full_volume_cn.md")
    resolved_paths = {**DEFAULT_PATHS, **supplied_paths}
    if any(not isinstance(resolved_paths[key], str) or not resolved_paths[key] for key in DEFAULT_PATHS):
        raise ValueError("all sync-plan paths must be non-empty strings")
    policies = _validate_frozen_policy(owner_decisions, content_policies)

    alignment = align_revisions(canonical_segments, revised_segments)
    changed = [item for item in alignment["aligned_segments"] if item["change_type"] == "modified"]
    decision_ids = [str(item.get("segment_id")) for item in classified_decisions]
    if len(decision_ids) != len(set(decision_ids)):
        raise ValueError("classified decision segment_id values must be unique")
    decisions = {segment_id: dict(item) for segment_id, item in zip(decision_ids, classified_decisions)}
    invalid = sorted({str(item.get("classification")) for item in classified_decisions} - set(TAXONOMY_CLASSES))
    if invalid:
        raise ValueError(f"invalid classified decision values: {invalid}")
    chapters = {item["chapter_id"] for item in changed}
    for item in alignment["manual_queue"]:
        if "revision_index" in item:
            chapter_id = revised_segments[item["revision_index"]].get("chapter_id")
        elif "canonical_index" in item:
            chapter_id = canonical_segments[item["canonical_index"]].get("chapter_id")
        else:
            chapter_id = None
        if chapter_id:
            chapters.add(str(chapter_id))
    segment_changes = [
        {
            "segment_id": item["segment_id"],
            "chapter_id": item["chapter_id"],
            "change_type": item["change_type"],
            "alignment_method": item["alignment_method"],
            "confidence": item["confidence"],
            "before_sha256": _fingerprint(item["before_text"]),
            "after_sha256": _fingerprint(item["after_text"]),
            "before_normalized_sha256": _fingerprint(normalize_text(item["before_text"])),
            "after_normalized_sha256": _fingerprint(normalize_text(item["after_text"])),
            "before_length": len(item["before_text"]),
            "after_length": len(item["after_text"]),
            "classification": decisions.get(item["segment_id"], {}).get("classification", "unclassified"),
        }
        for item in changed
    ]
    changed_ids = {item["segment_id"] for item in segment_changes}
    unknown_decisions = sorted(set(decisions) - changed_ids)
    if unknown_decisions:
        raise ValueError(f"classified decisions reference non-modified segments: {unknown_decisions}")
    needs_review = bool(changed or alignment["manual_queue"] or term_proposals or character_proposals)
    taxonomy_counts = {name: 0 for name in TAXONOMY_CLASSES}
    for item in classified_decisions:
        taxonomy_counts[str(item["classification"])] += 1
    unclassified_count = sum(item["classification"] == "unclassified" for item in segment_changes)
    semantic_classification_complete = unclassified_count == 0 and len(decisions) == len(segment_changes)
    alignment_complete = alignment["summary"]["complete_alignment"] is True
    manual_queue_empty = alignment["summary"]["manual_item_count"] == 0
    quality_gates = _build_quality_gates(validation_evidence)
    formatting = dict(FROZEN_FORUM_FORMATTING_POLICY)
    if forum_formatting_policy is not None and dict(forum_formatting_policy) != {
        "render_floor_template": FROZEN_FORUM_FORMATTING_POLICY["render_floor_template"],
        "render_reply_template": FROZEN_FORUM_FORMATTING_POLICY["render_reply_template"],
    }:
        raise ValueError("forum formatting policy overrides are forbidden")
    safe_alignment = {
        **alignment,
        "aligned_segments": [
            {
                "segment_id": item["segment_id"], "chapter_id": item["chapter_id"],
                "canonical_index": item["canonical_index"], "revision_index": item["revision_index"],
                "alignment_method": item["alignment_method"], "confidence": item["confidence"],
                "change_type": item["change_type"], "before_sha256": _fingerprint(item["before_text"]),
                "after_sha256": _fingerprint(item["after_text"]),
                "before_normalized_sha256": _fingerprint(normalize_text(item["before_text"])),
                "after_normalized_sha256": _fingerprint(normalize_text(item["after_text"])),
                "source_sha256": _fingerprint(item["source_text"]),
                "before_length": len(item["before_text"]), "after_length": len(item["after_text"]),
                "source_length": len(item["source_text"]),
            }
            for item in alignment["aligned_segments"]
        ],
        "manual_queue": [
            {
                **item,
                "chapter_id": _chapter_id(
                    revised_segments[item["revision_index"]]
                    if "revision_index" in item
                    else canonical_segments[item["canonical_index"]]
                ),
            }
            for item in alignment["manual_queue"]
        ],
    }
    plan: dict[str, Any] = {
        "schema_version": 1, "plan_type": "user_revision_sync_plan",
        "plan_only": True, "apply_implementation_available": False,
        "status": "awaiting_confirmation", "confirmation_required": True,
        "side_effects_applied": False,
        "generated_at": DEFAULT_GENERATED_AT if generated_at is None else generated_at,
        "input_hashes": dict(input_hashes), "paths": resolved_paths,
        "owner_decisions": [dict(item) for item in owner_decisions], "content_policies": policies,
        "chapter_coverage": {
            "changed_chapters": sorted(chapters), "changed_segment_count": len(changed),
            "aligned_segment_count": alignment["summary"]["aligned_segment_count"],
            "manual_item_count": alignment["summary"]["manual_item_count"],
            "chapter_87_disposition": chapter_87_disposition,
        },
        "alignment": safe_alignment,
        "quality_gates": quality_gates,
        "taxonomy": {
            "classes": TAXONOMY_CLASSES, "counts": taxonomy_counts,
            "unclassified_segment_count": unclassified_count,
            "classified_decisions": [dict(item) for item in classified_decisions],
        },
        "needs_glossary_update": bool(term_proposals),
        "needs_character_profile_update": bool(character_proposals),
        "needs_world_bible_update": False, "needs_style_profile_update": needs_review,
        "needs_translation_memory_update": bool(changed),
        "needs_local_retranslation": bool(alignment["manual_queue"]),
        "needs_consistency_check": needs_review,
        "affects_current_final_export": bool(changed or alignment["manual_queue"]),
        "proposed_writes": [
            "translation_memory", "glossary", "character_profile", "local_fix_plan", "revised_output", "audit_report",
        ] if needs_review else [],
        "segment_changes": segment_changes,
        "term_proposals": [dict(item) for item in term_proposals],
        "character_proposals": [dict(item) for item in character_proposals],
        "forum_formatting_policy": formatting,
        "checks": [
            "manual_alignment_queue_resolved", "owner_decisions_confirmed", "content_policies_confirmed",
            "exact_plan_acceptance_confirmed", "workspace_rebaseline_authorized_current_turn",
            "schema_validation_passed", "source_hashes_unchanged", "consistency_check_passed",
            "singleton_final_export_revalidated",
        ],
        "rollback": {
            "strategy": "discard_unconfirmed_plan_or_restore_pre_apply_hashes",
            "requires_pre_apply_snapshot": True, "automatic_rollback_performed": False,
        },
        "material_preview": {
            "changed_segment_refs": [item["segment_id"] for item in segment_changes[:20]],
            "truncated": len(segment_changes) > 20,
            "manual_refs": [
                item.get("canonical_segment_id") or f"revision-index:{item.get('revision_index')}"
                for item in alignment["manual_queue"][:20]
            ],
        },
    }
    content_digest = _content_digest_for_plan(plan)
    plan_id = f"user-revision-sync-{content_digest[:20]}"
    expected_token = sha256_bytes(f"{plan_id}:{content_digest}:accept".encode("utf-8"))
    supplied_auth = dict(application_authorization or {})
    exact_plan_accepted = (
        supplied_auth.get("accepted_plan_id") == plan_id
        and supplied_auth.get("accepted_content_digest") == content_digest
        and supplied_auth.get("acceptance_token") == expected_token
    )
    rebaseline_authorized = supplied_auth.get("workspace_rebaseline_authorized_current_turn") is True
    evidence = supplied_auth.get("workspace_rebaseline_authorization_evidence")
    if rebaseline_authorized and (not isinstance(evidence, str) or not evidence.strip()):
        raise ValueError("current-turn workspace rebaseline authorization requires non-empty evidence")
    decisions_confirmed = all(item["status"] == "confirmed" for item in owner_decisions)
    future_apply_candidate_eligible = (
        exact_plan_accepted
        and rebaseline_authorized
        and decisions_confirmed
        and alignment_complete
        and manual_queue_empty
        and semantic_classification_complete
        and quality_gates["all_passed"]
    )
    proposed_apply_target = resolved_paths["revised_output"]
    forbidden_targets = list(FORBIDDEN_TARGETS)
    forbidden_targets.extend(["canonical_final_until_confirmed", proposed_apply_target])
    plan.update(
        {
            "plan_id": plan_id, "content_digest": content_digest,
            "proposed_apply_target": proposed_apply_target,
            "readiness_gates": {
                "alignment_complete": alignment_complete,
                "manual_queue_empty": manual_queue_empty,
                "semantic_classification_complete": semantic_classification_complete,
                "owner_decisions_confirmed": decisions_confirmed,
                "exact_plan_accepted": exact_plan_accepted,
                "workspace_rebaseline_authorized_current_turn": rebaseline_authorized,
                "validation_complete": quality_gates["all_passed"],
                "future_apply_candidate_eligible": future_apply_candidate_eligible,
                "overall_ready": False,
            },
            "apply_authorization": {
                "exact_plan_acceptance": {
                    "required": True,
                    "accepted_plan_id": supplied_auth.get("accepted_plan_id"),
                    "accepted_content_digest": supplied_auth.get("accepted_content_digest"),
                    "acceptance_token": supplied_auth.get("acceptance_token"),
                    "expected_acceptance_token": expected_token,
                    "satisfied": exact_plan_accepted,
                },
                "workspace_rebaseline": {
                    "required": True, "authorized_current_turn": rebaseline_authorized,
                    "authorization_evidence": evidence, "satisfied": rebaseline_authorized,
                },
                "owner_decisions_confirmed": decisions_confirmed,
                "future_apply_candidate_eligible": future_apply_candidate_eligible,
                "gates_satisfied": False,
                "application_state": "forbidden_pending_gates",
            },
            "forbidden_targets": forbidden_targets,
        }
    )
    validate_sync_plan(plan)
    return plan
