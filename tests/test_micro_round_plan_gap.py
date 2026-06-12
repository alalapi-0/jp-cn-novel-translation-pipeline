"""Tests for GAP backfill round resolution (FS-007)."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from micro_round_plan import gap_backfill_plan, resolve_round_plan  # noqa: E402


def test_gap_round_resolves_with_correct_offsets() -> None:
    plan = resolve_round_plan("GAP-191-193")
    assert plan is not None
    assert plan["phase"] == "draft"
    assert plan["chapter_start"] == 191
    assert plan["chapter_end"] == 193
    assert plan["offset"] == 190
    assert plan["limit"] == 3
    # Gap rounds must never resume a legacy run directory (FS-002 data-loss
    # root cause was run-dir reuse).
    assert plan["resume_run_id"] == ""


def test_gap_round_single_chapter() -> None:
    plan = gap_backfill_plan("GAP-5-5")
    assert plan is not None
    assert plan["offset"] == 4
    assert plan["limit"] == 1


def test_gap_round_invalid_ranges_rejected() -> None:
    assert gap_backfill_plan("GAP-0-3") is None
    assert gap_backfill_plan("GAP-10-9") is None
    assert gap_backfill_plan("GAP-1-99999") is None
    assert gap_backfill_plan("D-MR-001") is None


def test_dmr_rounds_still_resolve() -> None:
    plan = resolve_round_plan("D-MR-001")
    assert plan is not None
    assert plan["chapter_start"] == 203
    assert plan["chapter_end"] == 205


def test_rmr_round_resolves_with_baseline_input() -> None:
    plan = resolve_round_plan("R-MR-001")
    assert plan is not None
    assert plan["phase"] == "refine"
    assert plan["chapter_start"] == 171
    assert plan["input_source"] == "draft_full_baseline"
