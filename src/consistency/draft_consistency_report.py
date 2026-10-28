"""Full draft consistency report aggregator (FS-037, Phase B).

Combines Level 0–5 artifacts into one statistics-only report under
``workspace/consistency_audit/``. Never embeds source or draft body text.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from translation.chapter_parser import count_source_chapters
from translation.run_progress import safe_load_json
from consistency.index_workspace_storage import index_workspace_path
from consistency.segment_index import SCHEMA_VERSION as SEGMENT_INDEX_SCHEMA_VERSION, index_shape_consistent, segment_index_digest

AUDIT_DIR_REL = "workspace/consistency_audit"
MANIFEST_DIR_REL = "workspace/manifests"
INDEX_DIR_REL = "workspace/indexes"

ARTIFACTS = {
    "chapter_manifest": ("chapter_manifest.json", MANIFEST_DIR_REL),
    "segment_index": ("segment_index.json", INDEX_DIR_REL),
    "entity_index": ("entity_index.json", INDEX_DIR_REL),
    "glossary_conflict_audit": ("glossary_conflict_audit.json", AUDIT_DIR_REL),
    "draft_structure_audit": ("draft_structure_audit.json", AUDIT_DIR_REL),
    "local_fix_plan": ("local_fix_plan.json", AUDIT_DIR_REL),
    "arbitration_report": ("arbitration_report.json", AUDIT_DIR_REL),
    "retranslate_progress": ("retranslate_progress.json", AUDIT_DIR_REL),
    "fix_plan_status": ("fix_plan_status.json", AUDIT_DIR_REL),
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _load_optional(repo_root: Path, rel_dir: str, name: str) -> dict[str, Any] | None:
    path = (
        index_workspace_path(name, repo_root=repo_root)
        if rel_dir == INDEX_DIR_REL
        else repo_root / rel_dir / name
    )
    if not path.is_file():
        return None
    return safe_load_json(path)


def _level_stats(repo_root: Path) -> dict[str, Any]:
    manifest = _load_optional(repo_root, MANIFEST_DIR_REL, "chapter_manifest.json") or {}
    segment_index = _load_optional(repo_root, INDEX_DIR_REL, "segment_index.json") or {}
    entity_index = _load_optional(repo_root, INDEX_DIR_REL, "entity_index.json") or {}
    glossary = _load_optional(repo_root, AUDIT_DIR_REL, "glossary_conflict_audit.json") or {}
    structure = _load_optional(repo_root, AUDIT_DIR_REL, "draft_structure_audit.json") or {}
    fix_plan = _load_optional(repo_root, AUDIT_DIR_REL, "local_fix_plan.json") or {}
    arbitration = _load_optional(repo_root, AUDIT_DIR_REL, "arbitration_report.json") or {}
    retranslate = _load_optional(repo_root, AUDIT_DIR_REL, "retranslate_progress.json") or {}
    fix_status = _load_optional(repo_root, AUDIT_DIR_REL, "fix_plan_status.json") or {}

    glossary_blocking = sum(1 for f in glossary.get("findings") or [] if f.get("blocking"))
    structure_blocking = sum(1 for f in structure.get("findings") or [] if f.get("blocking"))

    manifest_chapters = int((manifest.get("stats") or {}).get("chapters_indexed") or 0)
    index_schema_supported=(type(segment_index.get('schema_version')) is int
                            and segment_index['schema_version']==SEGMENT_INDEX_SCHEMA_VERSION)
    index_shape_valid=index_shape_consistent(segment_index)
    index_stats=segment_index.get('stats') if isinstance(segment_index.get('stats'),dict) else {}
    segment_total=index_stats.get('segments_indexed') if index_schema_supported else None
    segment_missing=index_stats.get('missing_segments_count') if index_schema_supported else None
    counts_valid=(type(segment_total) is int and segment_total>=0
                  and type(segment_missing) is int and segment_missing>=0)
    if not counts_valid:segment_total=segment_missing=None
    structure_inputs=structure.get('inputs') if isinstance(structure.get('inputs'),dict) else {}
    structure_schema_supported=(type(structure_inputs.get('segment_index_schema_version')) is int
                                and structure_inputs['segment_index_schema_version']==SEGMENT_INDEX_SCHEMA_VERSION)
    try:
        structure_index_matches=(index_shape_valid and structure_schema_supported
                                 and structure_inputs.get('segment_index_sha256')==segment_index_digest(segment_index))
    except (TypeError,ValueError,OverflowError):
        structure_index_matches=False

    return {
        "level_0_manifest": {
            "present": bool(manifest),
            "chapter_count": manifest_chapters,
            "covers_source": None,
            "snapshot_claims_full_coverage": (manifest.get("stats") or {}).get("full_coverage") is True,
            "source_freshness_status": "UNVERIFIED",
        },
        "level_1_entity_index": {
            "present": bool(entity_index),
            "entities_indexed": int((entity_index.get("stats") or {}).get("entities_indexed") or 0),
        },
        "level_2_glossary_conflicts": {
            "present": bool(glossary),
            "findings_total": len(glossary.get("findings") or []),
            "blocking_count": glossary_blocking,
        },
        "level_2_structure": {
            "present": bool(structure),
            "findings_total": len(structure.get("findings") or []),
            "blocking_count": structure_blocking,
            "index_schema_supported": structure_schema_supported,
            "index_content_matches": structure_index_matches,
        },
        "level_3_fix_plan": {
            "present": bool(fix_plan),
            "term_fix_count": (fix_plan.get("stats") or {}).get("term_fix_count"),
            "retranslate_segment_count": (fix_plan.get("stats") or {}).get("retranslate_segment_count"),
            "deferred_count": (fix_plan.get("stats") or {}).get("deferred_count"),
        },
        "level_4_arbitration": {
            "present": bool(arbitration),
            "candidate_count": arbitration.get("candidate_count"),
            "api_calls": arbitration.get("api_calls"),
            "max_api_calls": arbitration.get("max_api_calls"),
            "within_budget": not arbitration.get("budget_exhausted"),
            "execution_status": arbitration.get("status"),
            "dry_run": bool(arbitration.get("dry_run")),
        },
        "level_5_retranslate": {
            "present": bool(retranslate),
            "execution_status": retranslate.get("status"),
            "dry_run": bool(retranslate.get("dry_run") or (retranslate.get("last_batch") or {}).get("dry_run")),
            "total_segments": retranslate.get("total_segments"),
            "completed_segments": len(retranslate.get("completed_segment_ids") or []),
            "remaining_segments": max(
                0,
                int(retranslate.get("total_segments") or 0)
                - len(set(retranslate.get("completed_segment_ids") or [])),
            ),
        },
        "fix_plan_status": fix_status,
        "segment_index": {
            "segment_count": segment_total,
            "missing_segment_count": segment_missing,
            "schema_supported": index_schema_supported,
            "shape_consistent": index_shape_valid,
            "known_clean": index_shape_valid and counts_valid and index_stats.get('clean') is True,
            "source_freshness_status": "UNVERIFIED",
        },
        "blocking_conflicts_total": glossary_blocking + structure_blocking,
    }


def build_draft_consistency_report(repo_root: Path) -> dict[str, Any]:
    levels = _level_stats(repo_root)
    total_chapters = count_source_chapters(repo_root)
    blocking = int(levels.get("blocking_conflicts_total") or 0)

    artifacts_present = {
        key: (_load_optional(repo_root, rel_dir, name) is not None)
        for key, (name, rel_dir) in ARTIFACTS.items()
        if key not in ("retranslate_progress", "fix_plan_status", "arbitration_report")
    }
    arbitration = levels["level_4_arbitration"]
    retranslate = levels["level_5_retranslate"]
    fixes = levels["fix_plan_status"]
    simulated = arbitration["dry_run"] or retranslate["dry_run"] or fixes.get("dry_run")
    incomplete = (not all(artifacts_present.values())
                  or not levels['segment_index']['known_clean']
                  or not levels['level_2_structure']['index_content_matches']
                  or levels['level_0_manifest']['source_freshness_status']!='VERIFIED'
                  or levels['segment_index']['source_freshness_status']!='VERIFIED'
                  or bool(arbitration.get("candidate_count") and arbitration.get("execution_status") != "PASS")
                  or bool(levels["level_3_fix_plan"].get("retranslate_segment_count") and not fixes.get("all_closed")))
    failed = arbitration.get("execution_status") == "FAIL" or retranslate.get("execution_status") == "failed"
    status = "SIMULATED" if simulated else "FAIL" if blocking or failed else "INCOMPLETE" if incomplete else "PASS"

    return {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "phase": "B",
        "round": "FS-037",
        "total_source_chapters": total_chapters,
        "blocking_conflicts": blocking,
        "status": status,
        "artifacts_present": artifacts_present,
        "progressive_disclosure": levels,
        "recommendation": ("resolve_blocking_before_final_export" if blocking or failed
                           else "verify_current_sources_before_final_export"),
    }


def report_summary(report: dict[str, Any]) -> dict[str, Any]:
    pd = report.get("progressive_disclosure") or {}
    return {
        "status": report.get("status"),
        "blocking_conflicts": report.get("blocking_conflicts"),
        "total_source_chapters": report.get("total_source_chapters"),
        "retranslate_remaining": (pd.get("level_5_retranslate") or {}).get("remaining_segments"),
        "arbitration_api_calls": (pd.get("level_4_arbitration") or {}).get("api_calls"),
        "recommendation": report.get("recommendation"),
    }
