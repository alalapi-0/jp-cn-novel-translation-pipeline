"""Map Workbench project manifests to quality-review segment documents."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from .runner import DEFAULT_GLOSSARY, run_review
from .types import ReviewReport
from workbench.project_registry import validated_source_entries
from workbench.review_state import segment_id, segment_text

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def segments_doc_from_workbench(
    *,
    project_id: str,
    language_direction: str,
    segments: list[dict[str, Any]],
    chapter_id: str = "ch-workbench",
    source_inventory: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Convert flat Workbench segment rows into checker paragraph layout."""
    try:
        source_entries = validated_source_entries(source_inventory, language_direction=language_direction)
        expected = [row["segment_id"] for row in source_entries]
        hashes = {row["segment_id"]: row["source_sha256"] for row in source_entries}
        inventory_status = "pinned_source_import"
    except ValueError:
        expected = None; hashes = {}; inventory_status = "unknown_or_invalid_source_inventory"
    checker_segments: list[dict[str, Any]] = []
    for row in segments:
        if not isinstance(row, dict):
            checker_segments.append({"segment_id": "", "source_text": "", "target_text": "",
                                     "input_shape_error": "non_object_segment"})
            continue
        try:
            sid = segment_id(row)
        except ValueError:
            sid = ""
        checker_segments.append(
            {
                "segment_id": sid,
                "source_text": segment_text(row, "source", "source_text"),
                "target_text": segment_text(row, "draft", "draft_text", "target_text", "translation"),
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
        "source_expected_sha256": hashes,
        "source_inventory_status": inventory_status,
        "paragraphs": [{"paragraph_id": "wb-para-001", "segments": checker_segments}],
        "orphan_segment_ids": [],
    }


def glossary_path_for_project(project_id: str) -> Path | None:
    """Demo fixtures are never an implicit knowledge source for a real project."""
    if project_id == "demo-jp-cn":
        return DEFAULT_GLOSSARY
    return None


def run_review_for_workbench(
    *,
    project_id: str,
    language_direction: str,
    segments: list[dict[str, Any]],
    generated_by: str = "workbench.quality_review_api",
    source_inventory: dict[str, Any] | None = None,
    glossary_doc: dict[str, Any] | None = None,
) -> ReviewReport:
    segments_doc = segments_doc_from_workbench(
        project_id=project_id,
        language_direction=language_direction,
        segments=segments,
        source_inventory=source_inventory,
    )
    path = glossary_path_for_project(project_id) if glossary_doc is None else None
    source = "explicit_document_unverified" if glossary_doc is not None else (
        "synthetic_demo_fixture" if path else "none_no_project_glossary")
    report = run_review(
        glossary_path=path,
        glossary_doc=glossary_doc if glossary_doc is not None else (None if path else {"terms": []}),
        generated_by=generated_by,
        segments_doc=segments_doc,
    )
    report.summary["glossary_source"] = source
    report.summary["source_inventory_status"] = segments_doc["source_inventory_status"]
    return report
