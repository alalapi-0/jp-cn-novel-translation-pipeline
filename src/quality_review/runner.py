from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .checkers import run_all_checkers, summarize_issues
from .types import ReviewIssue, ReviewReport, utc_now_iso

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_SEGMENTS = REPO_ROOT / "data" / "examples" / "review_segments.fixture.json"
DEFAULT_GLOSSARY = REPO_ROOT / "data" / "examples" / "review_glossary.fixture.json"
SCHEMA_PATH = REPO_ROOT / "data" / "schemas" / "review_issue.schema.json"
EXAMPLE_REPORT = REPO_ROOT / "data" / "examples" / "review_issue_report.example.json"

REQUIRED_REPORT_KEYS = (
    "schema_version",
    "project_id",
    "language_direction",
    "review_status",
    "generated_at",
    "generated_by",
    "issues",
    "summary",
)

REQUIRED_ISSUE_KEYS = (
    "issue_id",
    "project_id",
    "language_direction",
    "chapter_id",
    "issue_type",
    "severity",
    "description",
    "status",
    "created_by",
    "created_at",
    "requires_human_review",
    "auto_fixable",
)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def derive_review_status(issues: list[ReviewIssue]) -> str:
    types = {i.issue_type for i in issues}
    if "LOCKED_TERM_VIOLATION" in types or "INCONSISTENT_TERM" in types:
        return "term_conflict"
    if "MISTRANSLATION" in types or "PLACEHOLDER_LOST" in types:
        return "review_needed"
    if "SEGMENT_ALIGNMENT_ERROR" in types or "OMISSION" in types:
        return "review_needed"
    if "OVER_REFINEMENT" in types:
        return "style_issue"
    if not issues:
        return "human_reviewed"
    return "review_needed"


def run_review(
    segments_path: Path | None = None,
    glossary_path: Path | None = None,
    *,
    generated_by: str = "quality_review_runner",
    segments_doc: dict[str, Any] | None = None,
    glossary_doc: dict[str, Any] | None = None,
) -> ReviewReport:
    if segments_doc is None:
        segments_doc = load_json(segments_path or DEFAULT_SEGMENTS)
    if glossary_doc is None:
        glossary_doc = load_json(glossary_path or DEFAULT_GLOSSARY)
    issues = run_all_checkers(segments_doc, glossary_doc)
    summary = summarize_issues(issues)
    return ReviewReport(
        schema_version="1.0.0",
        project_id=segments_doc["project_id"],
        language_direction=segments_doc["language_direction"],
        review_status=derive_review_status(issues),
        generated_at=utc_now_iso(),
        generated_by=generated_by,
        issues=issues,
        summary=summary,
    )


def validate_report_dict(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_REPORT_KEYS:
        if key not in report:
            errors.append(f"report missing key: {key}")
    if not isinstance(report.get("issues"), list):
        errors.append("issues must be a list")
        return errors
    for idx, issue in enumerate(report["issues"]):
        if not isinstance(issue, dict):
            errors.append(f"issue[{idx}] must be object")
            continue
        for key in REQUIRED_ISSUE_KEYS:
            if key not in issue:
                errors.append(f"issue[{idx}] missing key: {key}")
    summary = report.get("summary")
    if not isinstance(summary, dict):
        errors.append("summary must be object")
    elif summary.get("total") != len(report.get("issues", [])):
        errors.append("summary.total does not match issues length")
    return errors


def write_report(report: ReviewReport, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def aggregate_exit_code(errors: list[str], issue_count: int) -> int:
    if errors:
        return 2
    if issue_count == 0:
        return 1
    return 0
