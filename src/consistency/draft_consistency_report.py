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
    path = repo_root / rel_dir / name
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

    total_chapters = count_source_chapters(repo_root)
    manifest_chapters = int((manifest.get("stats") or {}).get("chapters_indexed") or 0)
    segment_total = int((segment_index.get("stats") or {}).get("segments_indexed") or 0)
    segment_missing = int((segment_index.get("stats") or {}).get("missing_segments_count") or 0)

    return {
        "level_0_manifest": {
            "present": bool(manifest),
            "chapter_count": manifest_chapters,
            "covers_source": bool((manifest.get("stats") or {}).get("full_coverage"))
            or manifest_chapters >= total_chapters,
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
        },
        "level_5_retranslate": {
            "present": bool(retranslate),
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

    return {
        "schema_version": 1,
        "generated_at": utc_now_iso(),
        "phase": "B",
        "round": "FS-037",
        "total_source_chapters": total_chapters,
        "blocking_conflicts": blocking,
        "status": "PASS" if blocking == 0 else "FAIL",
        "artifacts_present": artifacts_present,
        "progressive_disclosure": levels,
        "recommendation": (
            "ready_for_baseline_lock"
            if blocking == 0 and artifacts_present.get("chapter_manifest")
            else "resolve_blocking_before_baseline_lock"
        ),
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
