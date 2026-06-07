"""Tests for translation batch planner."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))

from plan_translation_batches import (  # noqa: E402
    classify_segment_length,
    plan_batches,
    split_failed_batch,
)
from translation.chapter_parser import Segment


def _seg(n: int, text: str) -> Segment:
    return Segment(segment_id=f"ch-001-seg-{n:03d}", source_text=text)


def test_classify_segment_length():
    assert classify_segment_length("短") == "short"
    assert classify_segment_length("x" * 100) == "medium"
    assert classify_segment_length("x" * 300) == "long"
    assert classify_segment_length("x" * 600) == "extra_long"


def test_plan_batches_short_segments_meets_min_per_call():
    segments = [_seg(i, f"段落{i}です。") for i in range(1, 41)]
    plan = plan_batches(segments, token_budget=12_000, max_segments_per_call=30)
    assert plan.total_segments == 40
    assert len(plan.batches) >= 1
    full_batches = [b for b in plan.batches if b.segment_count >= 15]
    assert full_batches, "expected at least one batch with >=15 segments"
    assert all(b.segment_count >= 15 for b in full_batches)


def test_plan_batches_extra_long_isolated():
    segments = [_seg(1, "x" * 20)] + [_seg(2, "y" * 700)]
    plan = plan_batches(segments, token_budget=12_000, max_segments_per_call=30)
    counts = [b.segment_count for b in plan.batches]
    assert 1 in counts


def test_split_failed_batch_halves():
    batch = [_seg(i, "a" * 10) for i in range(1, 9)]
    parts = split_failed_batch(batch)
    assert len(parts) == 2
    assert len(parts[0]) == 4
    assert len(parts[1]) == 4


def test_chapter_209_segment_plan():
    chapter_file = REPO_ROOT / "input_jp" / "209-*.md"
    matches = list(REPO_ROOT.glob("input_jp/209-*.md"))
    if not matches:
        return
    from plan_translation_batches import segments_from_chapter_file

    segments = segments_from_chapter_file(matches[0])
    plan = plan_batches(segments, token_budget=12_000, max_segments_per_call=30)
    assert plan.total_segments == len(segments)
    avg = plan.total_segments / max(len(plan.batches), 1)
    assert avg >= 8
