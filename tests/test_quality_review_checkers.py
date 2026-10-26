"""Tests for deterministic quality review checkers (synthetic fixtures)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from quality_review.checkers import (  # noqa: E402
    _likely_omission,
    _text_length_units,
    check_segment_alignment,
    check_term_consistency,
    reset_issue_counter,
)
from quality_review.runner import (  # noqa: E402
    EXAMPLE_REPORT,
    DEFAULT_GLOSSARY,
    DEFAULT_SEGMENTS,
    run_review,
    validate_report_dict,
)

SEGMENTS = REPO_ROOT / "data" / "examples" / "review_segments.fixture.json"
GLOSSARY = REPO_ROOT / "data" / "examples" / "review_glossary.fixture.json"


@pytest.fixture
def segments_doc():
    return json.loads(SEGMENTS.read_text(encoding="utf-8"))


@pytest.fixture
def glossary_doc():
    return json.loads(GLOSSARY.read_text(encoding="utf-8"))


def test_term_checker_finds_locked_violation(segments_doc, glossary_doc):
    reset_issue_counter()
    issues = check_term_consistency(segments_doc, glossary_doc)
    locked = [i for i in issues if i.issue_type == "LOCKED_TERM_VIOLATION"]
    assert len(locked) >= 1
    assert locked[0].segment_id == "seg-001"
    assert locked[0].auto_fixable is False
    assert locked[0].requires_human_review is True


def test_japanese_char_length_omission_heuristic():
    source = "彼女は異世界の空を見上げ、胸の奥で小さな期待と不安がせめぎ合うのを感じていた。"
    target = "异界。"
    src_len = _text_length_units(source, "JP_TO_CN")
    tgt_len = _text_length_units(target, "JP_TO_CN")
    assert src_len >= 20
    assert tgt_len <= 3
    assert _likely_omission(src_len, tgt_len, "JP_TO_CN")


def test_alignment_checker_finds_orphan(segments_doc):
    reset_issue_counter()
    issues = check_segment_alignment(segments_doc)
    orphans = [i for i in issues if "orphan" in i.description or "seg-extra" in i.description]
    assert len(orphans) >= 1


def test_run_review_deterministic_issue_count():
    report_a = run_review(SEGMENTS, GLOSSARY)
    report_b = run_review(SEGMENTS, GLOSSARY)
    assert report_a.summary["total"] == report_b.summary["total"]
    assert report_a.summary["total"] >= 7
    types = set(report_a.summary["by_type"])
    assert "LOCKED_TERM_VIOLATION" in types
    assert "SEGMENT_ALIGNMENT_ERROR" in types
    assert "PLACEHOLDER_LOST" in types
    assert "MISTRANSLATION" in types


def test_example_report_validates():
    assert EXAMPLE_REPORT.is_file()
    payload = json.loads(EXAMPLE_REPORT.read_text(encoding="utf-8"))
    assert validate_report_dict(payload) == []


def test_human_edited_not_auto_fixable(segments_doc, glossary_doc):
    reset_issue_counter()
    issues = check_term_consistency(segments_doc, glossary_doc)
    human = [i for i in issues if i.human_edited_segment]
    for issue in human:
        assert issue.auto_fixable is False


def clean_machine_report():
    doc = {"project_id": "synthetic-clean", "language_direction": "JP_TO_CN",
           "chapter_id": "ch-synthetic", "expected_segment_ids": ["s1"],
           "paragraphs": [{"paragraph_id": "p1", "segments": [
               {"segment_id": "s1", "source_text": "風が吹く。", "target_text": "风吹过。"}]}]}
    return run_review(segments_doc=doc, glossary_doc={"terms": []}, generated_by="human_user_claim")


def test_zero_issue_machine_result_cannot_create_human_review():
    report = clean_machine_report()
    assert not report.issues and report.review_status == "machine_checked"
    data = report.to_dict()
    assert data["schema_version"] == "1.1.0"
    assert data["review_actor_type"] == "machine"
    assert data["approval_state"] == "not_granted"
    assert validate_report_dict(data) == []


def test_zero_issue_report_schema_separates_machine_and_legacy_human_claims():
    import jsonschema
    from quality_review.runner import SCHEMA_PATH
    schema = json.loads(SCHEMA_PATH.read_text())
    data = clean_machine_report().to_dict()
    jsonschema.validate(data, schema)
    data.update(review_actor_type="machine", approval_state="not_granted", review_status="human_reviewed")
    with pytest.raises(jsonschema.ValidationError): jsonschema.validate(data, schema)
    assert validate_report_dict(data)
    # Old records remain readable; absent actor evidence never becomes new approval.
    del data["review_actor_type"]; del data["approval_state"]
    data["schema_version"] = "1.0.0"
    legacy = json.loads(json.dumps(data))
    assert validate_report_dict(data) == [] and data == legacy
    jsonschema.validate(data, schema)
