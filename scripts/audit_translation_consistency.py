#!/usr/bin/env python3
"""Minimal full-draft consistency audit (no real text in git-bound outputs)."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from local_env import apply_local_env  # noqa: E402
from translation.run_progress import safe_load_json  # noqa: E402

_gate_spec = importlib.util.spec_from_file_location(
    "throughput_gate", REPO_ROOT / "scripts" / "throughput_gate.py"
)
assert _gate_spec and _gate_spec.loader
_gate = importlib.util.module_from_spec(_gate_spec)
_gate_spec.loader.exec_module(_gate)

OUT_DIR = REPO_ROOT / "workspace" / "consistency_audit"
JP_RE = re.compile(r"[\u3040-\u30ff]")
CHAPTER_NUM_RE = re.compile(r"ch-(\d+)-")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_all_segments() -> list[dict[str, Any]]:
    chapters: list[dict[str, Any]] = []
    for run_root in _gate._iter_stage_b_runs():
        doc = safe_load_json(run_root / "segments.json")
        if not doc:
            continue
        for ch in doc.get("chapters", []):
            chapters.append(ch)
    return chapters


def _chapter_number(chapter_id: str) -> int | None:
    m = re.search(r"(\d+)", chapter_id or "")
    return int(m.group(1)) if m else None


def audit() -> dict[str, Any]:
    chapters = _load_all_segments()
    draft_done, refined_done = _gate._count_chapter_metrics()

    source_residual: list[dict[str, Any]] = []
    missing_segments: list[str] = []
    chapter_nums: list[int] = []
    term_hits: dict[str, set[str]] = defaultdict(set)

    for ch in chapters:
        cid = str(ch.get("chapter_id") or "")
        num = _chapter_number(cid)
        if num is not None:
            chapter_nums.append(num)
        for seg in ch.get("segments", []):
            sid = str(seg.get("segment_id") or "")
            draft = (seg.get("draft_text") or "").strip()
            if not draft:
                missing_segments.append(sid)
                continue
            if JP_RE.search(draft):
                source_residual.append({"segment_id": sid, "hint": "japanese_kana_present"})

    chapter_nums_sorted = sorted(set(chapter_nums))
    gaps: list[int] = []
    if chapter_nums_sorted:
        for i in range(chapter_nums_sorted[0], chapter_nums_sorted[-1] + 1):
            if i not in chapter_nums_sorted:
                gaps.append(i)

    # Load translation memory terms if present
    tm_path = REPO_ROOT / "workspace" / "assets" / "translation_memory" / "pw-user-assets-flow.json"
    tm_doc = safe_load_json(tm_path) if tm_path.is_file() else {}
    terms = tm_doc.get("terms") or tm_doc.get("glossary") or []
    if isinstance(terms, list):
        for entry in terms[:200]:
            if not isinstance(entry, dict):
                continue
            src = str(entry.get("source") or entry.get("jp") or "").strip()
            tgt = str(entry.get("target") or entry.get("zh") or "").strip()
            if src and tgt:
                term_hits[src].add(tgt)

    multi_target = {k: sorted(v) for k, v in term_hits.items() if len(v) > 1}
    multi_source: dict[str, list[str]] = defaultdict(list)
    for src, tgts in term_hits.items():
        for t in tgts:
            multi_source[t].append(src)
    multi_source = {k: sorted(set(v)) for k, v in multi_source.items() if len(v) > 1}

    entity_conflicts = {
        "same_source_multiple_targets": multi_target,
        "same_target_multiple_sources": multi_source,
    }

    report = {
        "generated_at": _utc_now(),
        "draft_completed_chapters": draft_done,
        "refined_exportable_chapters": refined_done,
        "chapters_observed": len(chapter_nums_sorted),
        "chapter_range": {
            "min": chapter_nums_sorted[0] if chapter_nums_sorted else None,
            "max": chapter_nums_sorted[-1] if chapter_nums_sorted else None,
        },
        "chapter_gaps": gaps[:50],
        "chapter_gap_count": len(gaps),
        "missing_draft_segment_count": len(missing_segments),
        "source_residual_segment_count": len(source_residual),
        "source_residual_samples": source_residual[:20],
        "entity_conflicts_summary": {
            "same_source_multiple_targets": len(multi_target),
            "same_target_multiple_sources": len(multi_source),
        },
        "glossary_entries_scanned": len(term_hits),
        "checks": {
            "names": "deferred_to_tm_expansion",
            "skills": "deferred_to_tm_expansion",
            "places": "deferred_to_tm_expansion",
            "organizations": "deferred_to_tm_expansion",
            "character_profiles": "deferred_manual_review",
            "world_bible": "deferred_manual_review",
        },
        "recommendation": "fix_glossary_and_validator_before_bulk_retranslate",
    }
    return report, entity_conflicts


def render_md(report: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Full Draft Consistency Report",
            "",
            f"- generated_at: {report['generated_at']}",
            f"- draft_completed_chapters: {report['draft_completed_chapters']}",
            f"- refined_exportable_chapters: {report['refined_exportable_chapters']}",
            f"- chapters_observed: {report['chapters_observed']}",
            f"- chapter_gaps: {report['chapter_gap_count']}",
            f"- missing_draft_segments: {report['missing_draft_segment_count']}",
            f"- source_residual_segments: {report['source_residual_segment_count']}",
            f"- glossary conflicts (source→targets): {report['entity_conflicts_summary']['same_source_multiple_targets']}",
            f"- glossary conflicts (target→sources): {report['entity_conflicts_summary']['same_target_multiple_sources']}",
            "",
            "## Recommendation",
            "",
            report["recommendation"],
            "",
            "> 详细冲突见 `entity_conflicts.json`；术语修复计划见 `terminology_fix_plan.md`。",
        ]
    ) + "\n"


def render_fix_plan(report: dict[str, Any], conflicts: dict[str, Any]) -> str:
    lines = [
        "# Terminology Fix Plan",
        "",
        f"Generated: {report['generated_at']}",
        "",
        "## Priority",
        "",
        "1. Resolve `same_source_multiple_targets` in translation memory / glossary.",
        "2. Resolve `same_target_multiple_sources` ambiguities.",
        "3. Update validator rules for locked terms.",
        "4. Re-run localized retranslate for affected segments only.",
        "",
        "## Conflict counts",
        "",
        f"- same_source_multiple_targets: {len(conflicts.get('same_source_multiple_targets', {}))}",
        f"- same_target_multiple_sources: {len(conflicts.get('same_target_multiple_sources', {}))}",
        "",
        "## Not in scope",
        "",
        "- Manual full-volume text edits",
        "- Automatic final marking",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit draft translation consistency")
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()
    apply_local_env(REPO_ROOT)

    report, conflicts = audit()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    (OUT_DIR / "full_draft_consistency_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (OUT_DIR / "entity_conflicts.json").write_text(
        json.dumps(conflicts, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    if not args.json_only:
        (OUT_DIR / "full_draft_consistency_report.md").write_text(render_md(report), encoding="utf-8")
        (OUT_DIR / "terminology_fix_plan.md").write_text(render_fix_plan(report, conflicts), encoding="utf-8")

    print(f"wrote {OUT_DIR}/full_draft_consistency_report.json")
    print(f"draft_completed={report['draft_completed_chapters']} gaps={report['chapter_gap_count']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
