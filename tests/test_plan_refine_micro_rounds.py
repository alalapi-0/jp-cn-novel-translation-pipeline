"""Tests for R-MR refinement queue planner (FS-040)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from micro_round_plan import (  # noqa: E402
    FIRST_REFINE_MR_CHAPTER,
    build_refine_mr_queue,
    refine_mr_plan,
    resolve_round_plan,
)
from plan_refine_micro_rounds import (  # noqa: E402
    build_queue_stats,
    parse_baseline_chapter,
    plan_refine_batches,
    plan_round,
    segments_from_baseline_range,
)
from translation.chapter_parser import Segment  # noqa: E402


def test_refine_mr_plan_first_and_last_round() -> None:
    first = refine_mr_plan("R-MR-001")
    assert first is not None
    assert first["phase"] == "refine"
    assert first["chapter_start"] == 171
    assert first["chapter_end"] == 173
    assert first["model_profile"] == "refine_primary"
    assert first["input_source"] == "draft_full_baseline"

    last = refine_mr_plan("R-MR-148")
    assert last is not None
    assert last["chapter_start"] == 612
    assert last["chapter_end"] == 612

    assert refine_mr_plan("R-MR-149") is None


def test_refine_queue_has_148_rounds_covering_442_chapters() -> None:
    queue = build_refine_mr_queue()
    assert len(queue) == 148
    assert queue[0]["round_id"] == "R-MR-001"
    assert queue[-1]["round_id"] == "R-MR-148"
    chapters = sum(item["limit"] for item in queue)
    assert chapters == 442


def test_resolve_round_plan_handles_rmr() -> None:
    plan = resolve_round_plan("R-MR-002")
    assert plan is not None
    assert plan["phase"] == "refine"
    assert plan["chapter_start"] == 174
    assert plan["chapter_end"] == 176


def test_parse_baseline_chapter_segment_markers() -> None:
    sample = REPO_ROOT / "draft_full_baseline" / "chapter_171_draft_zh.md"
    if not sample.is_file():
        pytest.skip("baseline chapter 171 not present")
    segments = parse_baseline_chapter(sample)
    assert len(segments) >= 10
    assert segments[0].segment_id.startswith("ch-171-seg-")
    assert segments[0].draft_text.strip()


def test_plan_refine_batches_respects_char_budget() -> None:
    long_text = "x" * 3000
    segments = [
        Segment(segment_id=f"ch-1-seg-{i:03d}", source_text="", draft_text=long_text)
        for i in range(1, 6)
    ]
    plan = plan_refine_batches(segments, max_segments=8, max_chars=6000)
    assert plan.total_segments == 5
    assert len(plan.batches) >= 2
    assert all(b.segment_count <= 8 for b in plan.batches)


def test_plan_round_rmr001_from_real_baseline() -> None:
    if not (REPO_ROOT / "draft_full_baseline_metadata.json").is_file():
        pytest.skip("baseline not locked in workspace")
    payload = plan_round(REPO_ROOT, round_id="R-MR-001")
    assert payload["round_id"] == "R-MR-001"
    assert payload["chapter_range"] == "171-173"
    assert payload["baseline_locked"] is True
    assert payload["missing_baseline_chapters"] == []
    assert payload["total_segments"] > 0
    assert payload["batch_count"] >= 1


def test_queue_stats_align_with_baseline() -> None:
    if not (REPO_ROOT / "draft_full_baseline_metadata.json").is_file():
        pytest.skip("baseline not locked in workspace")
    stats = build_queue_stats(REPO_ROOT)
    assert stats["total_rounds"] == 148
    assert stats["chapters_to_refine"] == 442
    assert stats["rmr_anchor_chapter"] == FIRST_REFINE_MR_CHAPTER
    assert stats["baseline_locked"] is True
    assert stats["missing_baseline_chapters"] == []
    assert stats["first_round"]["round_id"] == "R-MR-001"
    assert stats["last_round"]["round_id"] == "R-MR-148"


def test_segments_from_baseline_range_missing(tmp_path: Path) -> None:
    baseline = tmp_path / "draft_full_baseline"
    baseline.mkdir()
    path = baseline / "chapter_171_draft_zh.md"
    path.write_text(
        "# ch171\n\n<!-- ch-171-seg-001 -->\nhello\n",
        encoding="utf-8",
    )
    (tmp_path / "draft_full_baseline_metadata.json").write_text(
        json.dumps({"locked": True}),
        encoding="utf-8",
    )
    segments, missing = segments_from_baseline_range(tmp_path, 171, 173)
    assert len(segments) == 1
    assert missing == [172, 173]
