from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "src"))

from revision_sync.aligner import align_revisions

FIXTURES = Path(__file__).parent / "fixtures" / "user_revision_sync"


def _segments(name: str):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["segments"]


def test_unchanged_input_aligns_one_hundred_percent_without_mutation():
    canonical = _segments("canonical.json")
    revision = _segments("unchanged.json")
    before = copy.deepcopy((canonical, revision))
    result = align_revisions(canonical, revision)

    assert result["summary"]["complete_alignment"] is True
    assert result["summary"]["unchanged_segment_count"] == 3
    assert result["summary"]["modified_segment_count"] == 0
    assert result["manual_queue"] == []
    assert (canonical, revision) == before


def test_unique_normalized_target_anchor_precedes_similarity():
    canonical = _segments("canonical.json")
    revision = [{"chapter_id": "ch-1", "target_text": " 门\n开了。 "}]
    result = align_revisions(canonical, revision)
    assert result["aligned_segments"][0]["segment_id"] == "ch-1-seg-003"
    assert result["aligned_segments"][0]["alignment_method"] == "exact_normalized_target"


def test_exact_target_anchor_is_chapter_conditioned():
    canonical = [
        {"segment_id": "ch-1-seg-001", "chapter_id": "ch-1", "target_text": "同一句。"},
        {"segment_id": "ch-2-seg-001", "chapter_id": "ch-2", "target_text": "同一句。"},
    ]
    result = align_revisions(canonical, [{"chapter_id": "ch-2", "target_text": "同一句。"}])
    assert [item["segment_id"] for item in result["aligned_segments"]] == ["ch-2-seg-001"]
    assert result["aligned_segments"][0]["alignment_method"] == "exact_normalized_target"


def test_source_less_revision_allows_only_close_unique_same_chapter_match():
    canonical = [{
        "segment_id": "ch-3-seg-001", "chapter_id": "ch-3",
        "target_text": "他沿着安静的石板路慢慢走向远处那座古老的城堡。",
    }]
    revision = [{
        "chapter_id": "ch-3",
        "target_text": "他沿着寂静的石板路慢慢走向远处那座古老的城堡。",
    }]
    result = align_revisions(canonical, revision)
    assert result["aligned_segments"][0]["segment_id"] == "ch-3-seg-001"
    assert result["aligned_segments"][0]["alignment_method"] == "monotonic_high_confidence"
    assert result["manual_queue"] == []


def test_repeated_anchor_and_insertion_are_manual_not_ordinally_forced():
    canonical = [
        {"segment_id": "ch-2-seg-001", "chapter_id": "ch-2", "target_text": "重复。"},
        {"segment_id": "ch-2-seg-002", "chapter_id": "ch-2", "target_text": "重复。"},
    ]
    revision = _segments("ambiguous.json")
    result = align_revisions(canonical, revision)
    assert result["aligned_segments"] == []
    assert result["summary"]["manual_item_count"] == 4
    assert {item["kind"] for item in result["manual_queue"]} == {
        "unmatched_revision", "unmatched_canonical"
    }
    assert result["manual_queue"][0]["candidate_segment_ids"] == [
        "ch-2-seg-001", "ch-2-seg-002"
    ]


def test_source_conditioned_monotonic_alignment_accepts_clear_revision():
    canonical = _segments("canonical.json")
    revision = [{"source_text": "彼は歩いた。", "target_text": "他慢慢地走了。"}]
    result = align_revisions(canonical, revision)
    assert result["aligned_segments"][0]["segment_id"] == "ch-1-seg-002"
    assert result["aligned_segments"][0]["alignment_method"] == "monotonic_high_confidence"
    assert result["aligned_segments"][0]["change_type"] == "modified"
