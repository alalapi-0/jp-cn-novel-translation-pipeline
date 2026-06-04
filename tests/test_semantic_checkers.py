"""Round 54 semantic checker MVP — MISTRANSLATION / PLACEHOLDER_LOST."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from quality_review.checkers import (  # noqa: E402
    check_mistranslation,
    check_placeholder_lost,
    reset_issue_counter,
)
from quality_review.runner import run_review  # noqa: E402
from quality_review.workbench_adapter import (  # noqa: E402
    run_review_for_workbench,
    segments_doc_from_workbench,
)

SEGMENTS = REPO_ROOT / "data" / "examples" / "review_segments.fixture.json"
GLOSSARY = REPO_ROOT / "data" / "examples" / "review_glossary.fixture.json"


def test_placeholder_lost_detects_url_and_token():
    doc = {
        "project_id": "demo",
        "language_direction": "JP_TO_CN",
        "chapter_id": "ch-1",
        "paragraphs": [
            {
                "paragraph_id": "p1",
                "segments": [
                    {
                        "segment_id": "s1",
                        "source_text": "see {{PH_A}} and https://x.test/a",
                        "target_text": "见文档",
                    }
                ],
            }
        ],
    }
    reset_issue_counter()
    issues = check_placeholder_lost(doc)
    types = {i.issue_type for i in issues}
    assert "PLACEHOLDER_LOST" in types
    placeholders = {i.evidence.get("placeholder") for i in issues}
    assert "{{PH_A}}" in placeholders
    assert "https://x.test/a" in placeholders


def test_mistranslation_negation_polarity():
    doc = {
        "project_id": "demo",
        "language_direction": "JP_TO_CN",
        "chapter_id": "ch-1",
        "paragraphs": [
            {
                "paragraph_id": "p1",
                "segments": [
                    {
                        "segment_id": "s1",
                        "source_text": "彼女は学校に行かなかった。",
                        "target_text": "她去了学校。",
                    }
                ],
            }
        ],
    }
    reset_issue_counter()
    issues = check_mistranslation(doc)
    assert any(i.issue_type == "MISTRANSLATION" for i in issues)


def test_fixture_includes_semantic_issue_types():
    report = run_review(SEGMENTS, GLOSSARY)
    types = set(report.summary["by_type"])
    assert "PLACEHOLDER_LOST" in types
    assert "MISTRANSLATION" in types


def test_workbench_adapter_maps_segments():
    doc = segments_doc_from_workbench(
        project_id="demo-jp-cn",
        language_direction="JP_TO_CN",
        segments=[
            {
                "id": "seg-005",
                "source": "彼女は学校に行かなかった。",
                "draft": "她去了学校。",
            }
        ],
    )
    assert doc["expected_segment_ids"] == ["seg-005"]
    assert doc["paragraphs"][0]["segments"][0]["target_text"] == "她去了学校。"


def test_workbench_review_api_shape():
    example = REPO_ROOT / "data" / "examples" / "workbench_project.demo-jp-cn.example.json"
    payload = json.loads(example.read_text(encoding="utf-8"))
    report = run_review_for_workbench(
        project_id=payload["project_id"],
        language_direction=payload["language_direction"],
        segments=payload["segments"],
    )
    types = set(report.summary["by_type"])
    assert "MISTRANSLATION" in types
    assert report.project_id == "demo-jp-cn"
