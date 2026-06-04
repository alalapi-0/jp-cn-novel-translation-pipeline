"""Map Workbench project manifests to quality-review segment documents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .runner import DEFAULT_GLOSSARY, run_review
from .types import ReviewReport

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def segments_doc_from_workbench(
    *,
    project_id: str,
    language_direction: str,
    segments: list[dict[str, Any]],
    chapter_id: str = "ch-workbench",
) -> dict[str, Any]:
    """Convert flat Workbench segment rows into checker paragraph layout."""
    expected: list[str] = []
    checker_segments: list[dict[str, Any]] = []
    for row in segments:
        if not isinstance(row, dict):
            continue
        sid = str(row.get("segment_id") or row.get("id") or "").strip()
        if not sid:
            continue
        expected.append(sid)
        checker_segments.append(
            {
                "segment_id": sid,
                "source_text": str(row.get("source_text") or row.get("source") or ""),
                "target_text": str(
                    row.get("target_text") or row.get("draft") or row.get("translation") or ""
                ),
                "draft_text": str(row.get("draft_text") or row.get("draft") or ""),
                "refined_text": str(row.get("refined_text") or row.get("refined") or ""),
                "human_edited": bool(row.get("human_edited"))
                or str(row.get("status") or "") == "human_reviewed",
            }
        )
    return {
        "project_id": project_id,
        "language_direction": language_direction,
        "chapter_id": chapter_id,
        "expected_segment_ids": expected,
        "paragraphs": [{"paragraph_id": "wb-para-001", "segments": checker_segments}],
        "orphan_segment_ids": [],
    }


def glossary_path_for_project(project_id: str) -> Path:
    fixture = REPO_ROOT / "data" / "examples" / f"review_glossary.{project_id}.fixture.json"
    if fixture.is_file():
        return fixture
    if project_id == "demo-jp-cn":
        return DEFAULT_GLOSSARY
    return DEFAULT_GLOSSARY


def run_review_for_workbench(
    *,
    project_id: str,
    language_direction: str,
    segments: list[dict[str, Any]],
    generated_by: str = "workbench.quality_review_api",
) -> ReviewReport:
    segments_doc = segments_doc_from_workbench(
        project_id=project_id,
        language_direction=language_direction,
        segments=segments,
    )
    return run_review(
        glossary_path=glossary_path_for_project(project_id),
        generated_by=generated_by,
        segments_doc=segments_doc,
    )
