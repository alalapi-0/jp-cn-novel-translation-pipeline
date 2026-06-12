"""Glossary conflict audit (FS-034, Level 2).

Compares the entity index (FS-033) and optional term usage index (FS-015)
against glossary entries. Outputs deterministic statistics and per-conflict
chapter / segment locations — never source or draft body text.

Blocking rules (Phase B ``phase_acceptance_criteria.md`` B5)
------------------------------------------------------------
+---------------------------+-----------+------------------------------------------+
| Kind                      | Blocking  | Condition                                |
+===========================+===========+==========================================+
| ``locked_violation``      | yes       | ``locked=True`` term has divergent hits  |
| ``approved_violation``    | yes       | ``approved_by_user=True`` + divergent    |
| ``divergent_translation`` | no        | same-source multi-target (unprotected)   |
| ``shared_target``         | no        | same-target multi-source                 |
| ``unlisted_high_freq``    | no        | high-freq source absent from glossary    |
+---------------------------+-----------+------------------------------------------+

Protected-term divergent hits are emitted as ``locked_violation`` or
``approved_violation`` (blocking) rather than generic ``divergent_translation``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from glossary.models import GlossaryEntry

SCHEMA_VERSION = 1

BLOCKING_RULES: dict[str, str] = {
    "locked_violation": "blocking",
    "approved_violation": "blocking",
    "divergent_translation": "non-blocking",
    "shared_target": "non-blocking",
    "unlisted_high_freq": "non-blocking",
}

BLOCKING_KINDS: frozenset[str] = frozenset(
    kind for kind, level in BLOCKING_RULES.items() if level == "blocking"
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def chapters_from_segment_ids(segment_ids: list[str]) -> list[str]:
    """Derive chapter ids from segment ids like ``ch-001-seg-001``."""
    chapters: set[str] = set()
    for segment_id in segment_ids:
        parts = str(segment_id).split("-")
        if len(parts) >= 2:
            chapters.add(f"{parts[0]}-{parts[1]}")
    return sorted(chapters)


def _alternate_targets(stats: dict[str, Any], canonical_target: str) -> dict[str, int]:
    alts: dict[str, int] = {}
    for target, info in (stats.get("mappings") or {}).items():
        if not target or target == canonical_target:
            continue
        count = int((info or {}).get("count") or 0)
        if count > 0:
            alts[str(target)] = count
    return dict(sorted(alts.items(), key=lambda kv: (-kv[1], kv[0])))


def _term_stats(
    source_term: str,
    entity_index: dict[str, Any],
    term_usage_index: dict[str, Any] | None,
) -> dict[str, Any] | None:
    entities = entity_index.get("entities") or {}
    if source_term in entities:
        return entities[source_term]
    if term_usage_index:
        return (term_usage_index.get("terms") or {}).get(source_term)
    return None


def _protected_violation_kind(entry: GlossaryEntry) -> str | None:
    if entry.locked:
        return "locked_violation"
    if entry.approved_by_user:
        return "approved_violation"
    return None


def _finding_base(
    *,
    kind: str,
    blocking: bool,
    chapters: list[str],
    segment_ids: list[str],
    **extra: Any,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "kind": kind,
        "blocking": blocking,
        "chapters": chapters,
        "segment_ids": segment_ids,
    }
    row.update(extra)
    return row


def _collect_protected_violations(
    terms: list[GlossaryEntry],
    entity_index: dict[str, Any],
    term_usage_index: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for entry in sorted(terms, key=lambda t: t.source_term):
        if entry.deleted or not entry.target_term:
            continue
        kind = _protected_violation_kind(entry)
        if not kind:
            continue
        stats = _term_stats(entry.source_term, entity_index, term_usage_index)
        if not stats:
            continue
        divergent = int(stats.get("divergent") or 0)
        if divergent <= 0:
            continue
        segment_ids = list(stats.get("divergent_segment_ids") or [])
        findings.append(
            _finding_base(
                kind=kind,
                blocking=True,
                chapters=chapters_from_segment_ids(segment_ids),
                segment_ids=segment_ids,
                source_term=entry.source_term,
                target_term=entry.target_term,
                category=entry.category,
                source_hits=int(stats.get("source_hits") or 0),
                divergent=divergent,
                alternate_targets=_alternate_targets(stats, entry.target_term),
            )
        )
    return findings


def _collect_divergent_translation(
    entity_index: dict[str, Any],
    glossary_by_source: dict[str, GlossaryEntry],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for conflict in entity_index.get("conflicts") or []:
        if conflict.get("kind") != "divergent_translation":
            continue
        source_term = str(conflict.get("source_term") or "")
        entry = glossary_by_source.get(source_term)
        if entry and _protected_violation_kind(entry):
            continue
        segment_ids = list(conflict.get("sample_segment_ids") or [])
        entities = entity_index.get("entities") or {}
        stats = entities.get(source_term) or {}
        findings.append(
            _finding_base(
                kind="divergent_translation",
                blocking=False,
                chapters=chapters_from_segment_ids(segment_ids),
                segment_ids=segment_ids,
                source_term=source_term,
                target_term=str(conflict.get("target_term") or ""),
                source_hits=int(conflict.get("source_hits") or 0),
                divergent=int(conflict.get("divergent") or 0),
                ratio=float(conflict.get("ratio") or 0),
                alternate_targets=_alternate_targets(
                    stats,
                    str(conflict.get("target_term") or ""),
                ),
            )
        )
    findings.sort(key=lambda row: (row["source_term"], -row["divergent"]))
    return findings


def _collect_shared_target(entity_index: dict[str, Any]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    entities = entity_index.get("entities") or {}
    for conflict in entity_index.get("conflicts") or []:
        if conflict.get("kind") != "shared_target":
            continue
        target_term = str(conflict.get("target_term") or "")
        source_terms = sorted(conflict.get("source_terms") or [])
        segment_ids: list[str] = []
        for source_term in source_terms:
            stats = entities.get(source_term) or {}
            for seg_id in stats.get("divergent_segment_ids") or []:
                if seg_id not in segment_ids:
                    segment_ids.append(seg_id)
        findings.append(
            _finding_base(
                kind="shared_target",
                blocking=False,
                chapters=chapters_from_segment_ids(segment_ids),
                segment_ids=segment_ids[:20],
                target_term=target_term,
                source_terms=source_terms,
            )
        )
    findings.sort(key=lambda row: row["target_term"])
    return findings


def _collect_unlisted_high_freq(
    entity_index: dict[str, Any],
    glossary_sources: set[str],
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    for row in entity_index.get("unlisted_high_freq") or []:
        source_term = str(row.get("source_term") or "")
        if not source_term or source_term in glossary_sources:
            continue
        segment_ids = list(row.get("sample_segment_ids") or [])
        chapters = list(row.get("chapters") or [])
        if not chapters:
            chapters = chapters_from_segment_ids(segment_ids)
        findings.append(
            _finding_base(
                kind="unlisted_high_freq",
                blocking=False,
                chapters=sorted(chapters),
                segment_ids=segment_ids,
                source_term=source_term,
                source_hits=int(row.get("source_hits") or 0),
                inferred_targets=dict(row.get("inferred_targets") or {}),
            )
        )
    findings.sort(key=lambda row: (-row["source_hits"], row["source_term"]))
    return findings


def audit_glossary_conflicts(
    terms: list[GlossaryEntry],
    entity_index: dict[str, Any],
    *,
    term_usage_index: dict[str, Any] | None = None,
    generated_at: str | None = None,
) -> dict[str, Any]:
    """Build the glossary conflict audit report (deterministic for fixed inputs)."""
    active_terms = [t for t in terms if not t.deleted]
    glossary_by_source = {t.source_term: t for t in active_terms}
    glossary_sources: set[str] = set()
    for entry in active_terms:
        glossary_sources.add(entry.source_term)
        for alias in entry.aliases or []:
            if alias:
                glossary_sources.add(str(alias))

    findings: list[dict[str, Any]] = []
    findings.extend(
        _collect_protected_violations(active_terms, entity_index, term_usage_index)
    )
    findings.extend(_collect_divergent_translation(entity_index, glossary_by_source))
    findings.extend(_collect_shared_target(entity_index))
    findings.extend(_collect_unlisted_high_freq(entity_index, glossary_sources))

    findings.sort(
        key=lambda row: (
            0 if row["blocking"] else 1,
            row["kind"],
            row.get("source_term") or row.get("target_term") or "",
        )
    )

    by_kind: dict[str, int] = {}
    blocking_count = 0
    for row in findings:
        by_kind[row["kind"]] = by_kind.get(row["kind"], 0) + 1
        if row["blocking"]:
            blocking_count += 1

    entity_stats = entity_index.get("stats") or {}
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or utc_now_iso(),
        "inputs": {
            "entity_index_generated_at": entity_index.get("generated_at"),
            "entity_index_schema_version": entity_index.get("schema_version"),
            "glossary_entry_count": len(active_terms),
            "term_usage_index_used": term_usage_index is not None,
            "term_usage_index_generated_at": (
                (term_usage_index or {}).get("generated_at") if term_usage_index else None
            ),
            "unlisted_candidate_count": entity_stats.get("unlisted_candidate_count"),
            "entities_indexed": entity_stats.get("entities_indexed"),
        },
        "blocking_rules": dict(BLOCKING_RULES),
        "stats": {
            "findings_total": len(findings),
            "blocking_count": blocking_count,
            "non_blocking_count": len(findings) - blocking_count,
            "by_kind": dict(sorted(by_kind.items())),
        },
        "findings": findings,
    }


def audit_summary(report: dict[str, Any]) -> dict[str, Any]:
    stats = report.get("stats") or {}
    blocking = int(stats.get("blocking_count") or 0)
    return {
        "status": "PASS" if blocking == 0 else "WARN",
        "findings_total": stats.get("findings_total"),
        "blocking_count": blocking,
        "non_blocking_count": stats.get("non_blocking_count"),
        "by_kind": stats.get("by_kind"),
    }
