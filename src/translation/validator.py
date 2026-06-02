"""Validate draft translation structured results."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .response_extractor import ExtractedItem


@dataclass
class ValidationIssue:
    code: str
    message: str
    segment_id: str = ""


@dataclass
class ValidationResult:
    passed: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "issues": [
                {"code": i.code, "message": i.message, "segment_id": i.segment_id}
                for i in self.issues
            ],
        }


def validate_draft_items(
    items: list[ExtractedItem],
    expected_segment_ids: list[str],
    source_lengths: dict[str, int],
) -> ValidationResult:
    issues: list[ValidationIssue] = []
    by_id = {i.segment_id: i for i in items}

    for sid in expected_segment_ids:
        item = by_id.get(sid)
        if item is None:
            issues.append(ValidationIssue("segment_id_coverage", f"missing: {sid}", sid))
            continue
        if not item.translation.strip():
            issues.append(ValidationIssue("non_empty", "empty translation", sid))
            continue
        src_len = source_lengths.get(sid, 1)
        ratio = len(item.translation) / max(src_len, 1)
        if ratio < 0.05:
            issues.append(
                ValidationIssue("length_ratio", f"translation too short (ratio={ratio:.3f})", sid)
            )
        elif ratio > 8.0:
            issues.append(
                ValidationIssue("length_ratio", f"translation too long (ratio={ratio:.3f})", sid)
            )

    extra = set(by_id) - set(expected_segment_ids)
    for sid in sorted(extra):
        issues.append(ValidationIssue("no_extra_segment", f"unexpected segment: {sid}", sid))

    return ValidationResult(passed=len(issues) == 0, issues=issues)
