from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass
class ReviewIssue:
    issue_id: str
    project_id: str
    language_direction: str
    chapter_id: str
    issue_type: str
    severity: str
    description: str
    status: str
    created_by: str
    created_at: str
    requires_human_review: bool
    auto_fixable: bool
    paragraph_id: str = ""
    segment_id: str = ""
    source_text_ref: str = ""
    target_text_ref: str = ""
    suggested_fix: str = ""
    evidence: dict[str, Any] = field(default_factory=dict)
    related_term_ids: list[str] = field(default_factory=list)
    related_character_ids: list[str] = field(default_factory=list)
    related_world_bible_ids: list[str] = field(default_factory=list)
    resolved_at: str | None = None
    human_edited_segment: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class ReviewReport:
    schema_version: str
    project_id: str
    language_direction: str
    review_status: str
    generated_at: str
    generated_by: str
    issues: list[ReviewIssue]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "project_id": self.project_id,
            "language_direction": self.language_direction,
            "review_status": self.review_status,
            "generated_at": self.generated_at,
            "generated_by": self.generated_by,
            "issues": [i.to_dict() for i in self.issues],
            "summary": self.summary,
        }
