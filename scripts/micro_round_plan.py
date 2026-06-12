#!/usr/bin/env python3
"""Resolve 3-chapter draft/refinement micro-round plans (D-MR-XXX / R-MR-XXX)."""

from __future__ import annotations

import re
from typing import Any

FIRST_DRAFT_MR_CHAPTER = 203
TOTAL_CHAPTERS = 612
# NOTE (FS-008 incident, 2026-06-11): the old LEGACY_PARTIAL_RUN_ID auto-resume
# pointed D-MR-001/002 at run_20260607_095821 and the hydrate step rewrote that
# run's segments window (209-211 -> 206-208), orphaning the ch209-211 records.
# Legacy-run auto-resume is permanently removed; resume decisions belong to the
# scheduler task planner, which only ever resumes same-offset in_progress runs.

# Legacy 20-chapter rounds (deprecated, kept for report compatibility).
LEGACY_ROUND_PLAN: dict[str, dict[str, Any]] = {
    "T-001": {
        "phase": "draft",
        "chapter_start": 171,
        "chapter_end": 190,
        "offset": 170,
        "limit": 20,
        "resume_run_id": "",
    },
    "T-002": {
        "phase": "draft",
        "chapter_start": 191,
        "chapter_end": 210,
        "offset": 190,
        "limit": 20,
        "resume_run_id": "",
    },
    "T-003": {
        "phase": "draft",
        "chapter_start": 211,
        "chapter_end": 230,
        "offset": 210,
        "limit": 20,
        "resume_run_id": "",
    },
}


def _parse_mr_number(round_id: str, prefix: str) -> int | None:
    m = re.match(rf"^{re.escape(prefix)}-(\d+)$", round_id)
    return int(m.group(1)) if m else None


def draft_mr_plan(round_id: str, *, round_size: int = 3) -> dict[str, Any] | None:
    n = _parse_mr_number(round_id, "D-MR")
    if n is None or n < 1:
        return None
    start = FIRST_DRAFT_MR_CHAPTER + (n - 1) * round_size
    if start > TOTAL_CHAPTERS:
        return None
    end = min(start + round_size - 1, TOTAL_CHAPTERS)
    offset = start - 1
    limit = end - start + 1
    return {
        "round_id": round_id,
        "phase": "draft",
        "chapter_start": start,
        "chapter_end": end,
        "offset": offset,
        "limit": limit,
        "round_size": round_size,
        "resume_run_id": "",
        "model_profile": "draft_translation_primary",
    }


def next_draft_mr_id(round_id: str) -> str | None:
    n = _parse_mr_number(round_id, "D-MR")
    if n is None:
        return None
    nxt = n + 1
    if FIRST_DRAFT_MR_CHAPTER + (nxt - 1) * 3 > TOTAL_CHAPTERS:
        return None
    return f"D-MR-{nxt:03d}"


def gap_backfill_plan(round_id: str) -> dict[str, Any] | None:
    """Resolve GAP-<start>-<end> backfill rounds (FS-007).

    Gap rounds cover chapters below the D-MR anchor that lost their run
    records (e.g. ch191-208, found in FS-002). They never resume a legacy
    run directory: reusing run dirs is the data-loss root cause documented
    in the FS-002 report.
    """
    m = re.match(r"^GAP-(\d+)-(\d+)$", round_id)
    if not m:
        return None
    start, end = int(m.group(1)), int(m.group(2))
    if start < 1 or end < start or end > TOTAL_CHAPTERS:
        return None
    return {
        "round_id": round_id,
        "phase": "draft",
        "chapter_start": start,
        "chapter_end": end,
        "offset": start - 1,
        "limit": end - start + 1,
        "round_size": end - start + 1,
        "resume_run_id": "",
        "model_profile": "draft_translation_primary",
    }


def resolve_round_plan(
    round_id: str,
    *,
    round_size: int = 3,
    run_id: str = "",
    chapter_range: str = "",
) -> dict[str, Any] | None:
    if round_id in LEGACY_ROUND_PLAN:
        plan = dict(LEGACY_ROUND_PLAN[round_id])
        plan["round_id"] = round_id
        if run_id:
            plan["resume_run_id"] = run_id
        return plan

    plan = gap_backfill_plan(round_id) or draft_mr_plan(round_id, round_size=round_size)
    if plan is None:
        return None

    if run_id:
        plan["resume_run_id"] = run_id
    if chapter_range:
        m = re.match(r"^(\d+)-(\d+)$", chapter_range.strip())
        if m:
            plan["chapter_start"] = int(m.group(1))
            plan["chapter_end"] = int(m.group(2))
            plan["offset"] = plan["chapter_start"] - 1
            plan["limit"] = plan["chapter_end"] - plan["chapter_start"] + 1
    return plan
