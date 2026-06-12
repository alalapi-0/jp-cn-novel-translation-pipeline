"""Local fix plan builder and term-fix applier (FS-036, Phase B Level 3).

Aggregates FS-034 glossary conflict audit and FS-035 draft structure audit into:
- **term_fixes**: deterministic glossary target replacements (rule patches);
- **retranslate_tasks**: segment-level retranslation (non-deterministic / residual);
- **deferred**: glossary curation or informational items (no auto-fix this round).

Never embeds source or draft body text in the plan document.
"""

from __future__ import annotations

import difflib
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from consistency.conflict_audit import chapters_from_segment_ids
from consistency.manifest import find_segments_files

SCHEMA_VERSION = 1

TERM_FIX_KINDS: frozenset[str] = frozenset(
    {"locked_violation", "approved_violation", "divergent_translation"}
)
RETRANSLATE_KINDS: frozenset[str] = frozenset(
    {
        "source_residual",
        "missing_segment",
        "missing_draft",
        "misalignment",
        "shared_target",
    }
)
DEFER_KINDS: frozenset[str] = frozenset({"unlisted_high_freq", "format_anomaly"})


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _term_fixes_from_glossary(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fixes: list[dict[str, Any]] = []
    for row in findings:
        kind = str(row.get("kind") or "")
        if kind not in TERM_FIX_KINDS:
            continue
        canonical = str(row.get("target_term") or "").strip()
        if not canonical:
            continue
        alternates = row.get("alternate_targets") or {}
        if not alternates:
            continue
        source_term = str(row.get("source_term") or "")
        segment_ids = list(row.get("segment_ids") or [])
        chapters = list(row.get("chapters") or [])
        for alternate_target in sorted(alternates):
            fixes.append(
                {
                    "fix_method": "term_replace",
                    "kind": kind,
                    "blocking": bool(row.get("blocking")),
                    "source_term": source_term,
                    "canonical_target": canonical,
                    "alternate_target": alternate_target,
                    "segment_ids": segment_ids,
                    "chapters": chapters,
                }
            )
    fixes.sort(
        key=lambda row: (
            row["kind"],
            row["source_term"],
            row["alternate_target"],
        )
    )
    return fixes


def _retranslate_from_glossary(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    for row in findings:
        kind = str(row.get("kind") or "")
        if kind not in RETRANSLATE_KINDS:
            continue
        segment_ids = list(row.get("segment_ids") or [])
        if not segment_ids and kind == "shared_target":
            continue
        tasks.append(
            {
                "task_method": "segment_retranslate",
                "kind": kind,
                "blocking": bool(row.get("blocking")),
                "segment_ids": segment_ids,
                "chapters": list(row.get("chapters") or chapters_from_segment_ids(segment_ids)),
                "reason": "ambiguous_shared_target" if kind == "shared_target" else kind,
                **{
                    k: row[k]
                    for k in ("target_term", "source_terms")
                    if k in row and row[k] is not None
                },
            }
        )
    return tasks


def _retranslate_from_structure(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for row in findings:
        kind = str(row.get("kind") or "")
        if kind not in RETRANSLATE_KINDS:
            continue
        hint = str(row.get("hint") or row.get("severity") or kind)
        key = (kind, hint)
        bucket = grouped.setdefault(
            key,
            {
                "task_method": "segment_retranslate",
                "kind": kind,
                "blocking": bool(row.get("blocking")),
                "severity": row.get("severity"),
                "hint": row.get("hint"),
                "reason": hint,
                "segment_ids": [],
                "chapters": set(),
                "source_run_ids": set(),
            },
        )
        bucket["blocking"] = bucket["blocking"] or bool(row.get("blocking"))
        for sid in row.get("segment_ids") or []:
            if sid not in bucket["segment_ids"]:
                bucket["segment_ids"].append(sid)
        for ch in row.get("chapters") or []:
            bucket["chapters"].add(ch)
        run_id = row.get("source_run_id")
        if run_id:
            bucket["source_run_ids"].add(str(run_id))

    tasks: list[dict[str, Any]] = []
    for (kind, _), bucket in sorted(grouped.items()):
        tasks.append(
            {
                "task_method": bucket["task_method"],
                "kind": kind,
                "blocking": bucket["blocking"],
                "severity": bucket.get("severity"),
                "hint": bucket.get("hint"),
                "reason": bucket["reason"],
                "segment_ids": bucket["segment_ids"],
                "chapters": sorted(bucket["chapters"]),
                "source_run_ids": sorted(bucket["source_run_ids"]),
            }
        )
    return tasks


def _deferred_from_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deferred: list[dict[str, Any]] = []
    for row in findings:
        kind = str(row.get("kind") or "")
        if kind not in DEFER_KINDS:
            continue
        method = "glossary_curation" if kind == "unlisted_high_freq" else "manual_review"
        deferred.append(
            {
                "defer_method": method,
                "kind": kind,
                "blocking": bool(row.get("blocking")),
                "source_term": row.get("source_term"),
                "chapters": list(row.get("chapters") or []),
                "segment_ids": list(row.get("segment_ids") or [])[:20],
                "source_hits": row.get("source_hits"),
            }
        )
    deferred.sort(key=lambda row: (-(row.get("source_hits") or 0), str(row.get("source_term") or "")))
    return deferred


def build_local_fix_plan(
    glossary_audit: dict[str, Any],
    structure_audit: dict[str, Any],
    *,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Merge FS-034 / FS-035 audit reports into an actionable fix plan."""
    glossary_findings = list(glossary_audit.get("findings") or [])
    structure_findings = list(structure_audit.get("findings") or [])

    term_fixes = _term_fixes_from_glossary(glossary_findings)
    retranslate = _retranslate_from_glossary(glossary_findings)
    retranslate.extend(_retranslate_from_structure(structure_findings))
    deferred = _deferred_from_findings(glossary_findings)
    deferred.extend(_deferred_from_findings(structure_findings))

    term_fix_segments = {sid for fix in term_fixes for sid in fix.get("segment_ids") or []}
    retranslate_segments = {sid for task in retranslate for sid in task.get("segment_ids") or []}

    by_method: dict[str, dict[str, int]] = {
        "term_replace": defaultdict(int),
        "segment_retranslate": defaultdict(int),
        "deferred": defaultdict(int),
    }
    for fix in term_fixes:
        by_method["term_replace"][fix["kind"]] += 1
    for task in retranslate:
        by_method["segment_retranslate"][task["kind"]] += 1
    for item in deferred:
        by_method["deferred"][item["kind"]] += 1

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or utc_now_iso(),
        "inputs": {
            "glossary_conflict_audit_generated_at": glossary_audit.get("generated_at"),
            "draft_structure_audit_generated_at": structure_audit.get("generated_at"),
            "glossary_findings_total": len(glossary_findings),
            "structure_findings_total": len(structure_findings),
        },
        "stats": {
            "term_fix_count": len(term_fixes),
            "retranslate_task_count": len(retranslate),
            "deferred_count": len(deferred),
            "term_fix_segment_count": len(term_fix_segments),
            "retranslate_segment_count": len(retranslate_segments),
        },
        "categorization": {
            "term_replace": dict(sorted(by_method["term_replace"].items())),
            "segment_retranslate": dict(sorted(by_method["segment_retranslate"].items())),
            "deferred": dict(sorted(by_method["deferred"].items())),
        },
        "term_fixes": term_fixes,
        "retranslate_tasks": retranslate,
        "deferred": deferred,
    }


def plan_summary(plan: dict[str, Any]) -> dict[str, Any]:
    stats = plan.get("stats") or {}
    return {
        "status": "PASS",
        "term_fix_count": stats.get("term_fix_count"),
        "retranslate_task_count": stats.get("retranslate_task_count"),
        "deferred_count": stats.get("deferred_count"),
        "term_fix_segment_count": stats.get("term_fix_segment_count"),
        "retranslate_segment_count": stats.get("retranslate_segment_count"),
        "categorization": plan.get("categorization"),
    }


def build_segment_locations(repo_root: Path) -> dict[str, tuple[Path, int, int]]:
    """Map segment_id -> (segments.json path, chapter_index, segment_index)."""
    locations: dict[str, tuple[Path, int, int]] = {}
    for seg_path in find_segments_files(repo_root):
        doc = json.loads(seg_path.read_text(encoding="utf-8"))
        for ci, chapter in enumerate(doc.get("chapters") or []):
            for si, segment in enumerate(chapter.get("segments") or []):
                sid = str(segment.get("segment_id") or "")
                if sid:
                    locations[sid] = (seg_path, ci, si)
    return locations


def _segment_draft_at(locations: dict[str, tuple[Path, int, int]], segment_id: str) -> str | None:
    loc = locations.get(segment_id)
    if not loc:
        return None
    path, ci, si = loc
    doc = json.loads(path.read_text(encoding="utf-8"))
    return str(doc["chapters"][ci]["segments"][si].get("draft_text") or "")


def _apply_replace_to_draft(draft: str, alternate: str, canonical: str) -> tuple[str, bool]:
    if not alternate or alternate not in draft:
        return draft, False
    return draft.replace(alternate, canonical), True


def preview_term_fixes(
    plan: dict[str, Any],
    repo_root: Path,
) -> list[dict[str, Any]]:
    """Compute per-segment before/after for term fixes (for dry-run display)."""
    locations = build_segment_locations(repo_root)
    previews: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()

    for fix in plan.get("term_fixes") or []:
        alternate = str(fix.get("alternate_target") or "")
        canonical = str(fix.get("canonical_target") or "")
        for segment_id in fix.get("segment_ids") or []:
            key = (segment_id, alternate, canonical)
            if key in seen:
                continue
            seen.add(key)
            before = _segment_draft_at(locations, segment_id)
            if before is None:
                previews.append(
                    {
                        "segment_id": segment_id,
                        "alternate_target": alternate,
                        "canonical_target": canonical,
                        "changed": False,
                        "missing": True,
                    }
                )
                continue
            after, changed = _apply_replace_to_draft(before, alternate, canonical)
            diff_lines = list(
                difflib.unified_diff(
                    before.splitlines(keepends=True),
                    after.splitlines(keepends=True),
                    fromfile=f"{segment_id}:before",
                    tofile=f"{segment_id}:after",
                    lineterm="",
                )
            )
            previews.append(
                {
                    "segment_id": segment_id,
                    "alternate_target": alternate,
                    "canonical_target": canonical,
                    "changed": changed,
                    "missing": False,
                    "diff": "".join(diff_lines) if changed else "",
                }
            )
    previews.sort(key=lambda row: row["segment_id"])
    return previews


def apply_term_fixes(
    plan: dict[str, Any],
    repo_root: Path,
    *,
    dry_run: bool = True,
) -> dict[str, Any]:
    """Apply term_replace patches to draft_text only (never source or checkpoints)."""
    locations = build_segment_locations(repo_root)
    modified_files: dict[Path, dict[str, Any]] = {}
    applied: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for fix in plan.get("term_fixes") or []:
        alternate = str(fix.get("alternate_target") or "")
        canonical = str(fix.get("canonical_target") or "")
        for segment_id in fix.get("segment_ids") or []:
            loc = locations.get(segment_id)
            if not loc:
                skipped.append({"segment_id": segment_id, "reason": "segment_not_found"})
                continue
            path, ci, si = loc
            if path not in modified_files:
                modified_files[path] = json.loads(path.read_text(encoding="utf-8"))
            doc = modified_files[path]
            segment = doc["chapters"][ci]["segments"][si]
            before = str(segment.get("draft_text") or "")
            source_before = str(segment.get("source_text") or "")
            after, changed = _apply_replace_to_draft(before, alternate, canonical)
            if not changed:
                skipped.append({"segment_id": segment_id, "reason": "alternate_not_present"})
                continue
            if not dry_run:
                segment["draft_text"] = after
            applied.append(
                {
                    "segment_id": segment_id,
                    "alternate_target": alternate,
                    "canonical_target": canonical,
                    "segments_file": str(path),
                    "source_text_unchanged": segment.get("source_text") == source_before,
                }
            )

    if not dry_run:
        for path, doc in modified_files.items():
            tmp = path.with_suffix(path.suffix + ".tmp")
            tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            tmp.replace(path)

    return {
        "dry_run": dry_run,
        "applied_count": len(applied),
        "skipped_count": len(skipped),
        "modified_files": sorted({str(p) for p in modified_files}),
        "applied": applied,
        "skipped": skipped,
        "previews": preview_term_fixes(plan, repo_root) if dry_run else [],
    }
