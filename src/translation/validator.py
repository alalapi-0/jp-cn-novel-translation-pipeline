"""Validate draft translation structured results."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from .response_extractor import ExtractedItem


@dataclass
class ValidationIssue:
    code: str
    message: str
    segment_id: str = ""
    severity: str = "error"


@dataclass
class ValidationResult:
    passed: bool
    issues: list[ValidationIssue] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "issues": [
                {"code": i.code, "message": i.message, "segment_id": i.segment_id, "severity": i.severity}
                for i in self.issues
            ],
        }


def validate_draft_items(
    items: list[ExtractedItem],
    expected_segment_ids: list[str],
    source_lengths: dict[str, int],
) -> ValidationResult:
    issues: list[ValidationIssue] = []
    if not expected_segment_ids:
        issues.append(ValidationIssue("empty_expected_source", "expected source segment list is empty"))
    expected: list[str] = []
    for sid in expected_segment_ids:
        if not isinstance(sid, str) or not sid.strip():
            issues.append(ValidationIssue("invalid_expected_id", "invalid expected source identity"))
        else:
            expected.append(sid)
    for sid, count in Counter(expected).items():
        if count > 1:
            issues.append(ValidationIssue("duplicate_expected_id", "duplicate expected source identity", sid))
    valid_items: list[ExtractedItem] = []
    for item in items:
        sid = getattr(item, "segment_id", None)
        if not isinstance(sid, str) or not sid.strip():
            issues.append(ValidationIssue("invalid_segment_id", "invalid target identity"))
        else:
            valid_items.append(item)
    for sid, count in Counter(i.segment_id for i in valid_items).items():
        if count > 1:
            issues.append(ValidationIssue("duplicate_segment_id", "duplicate target identity", sid))
    by_id = {i.segment_id: i for i in valid_items}

    for sid in expected:
        item = by_id.get(sid)
        if item is None:
            issues.append(ValidationIssue("segment_id_coverage", f"missing: {sid}", sid))
            continue
        if not isinstance(item.translation, str) or not item.translation.strip():
            issues.append(ValidationIssue("non_empty", "empty translation", sid))
            continue
        src_len = source_lengths.get(sid, 0)
        if not isinstance(src_len, int) or src_len <= 0:
            issues.append(ValidationIssue("empty_or_unknown_source", "source length is absent or empty", sid))
            continue
        ratio = len(item.translation) / max(src_len, 1)
        if ratio < 0.05:
            issues.append(
                ValidationIssue("length_ratio", f"translation unusually short (ratio={ratio:.3f}); semantic coverage unverified", sid, "warning")
            )
        elif ratio > 8.0:
            issues.append(
                ValidationIssue("length_ratio", f"translation unusually long (ratio={ratio:.3f}); semantic fidelity unverified", sid, "warning")
            )

    extra = set(by_id) - set(expected)
    for sid in sorted(extra):
        issues.append(ValidationIssue("no_extra_segment", f"unexpected segment: {sid}", sid))

    return ValidationResult(passed=not any(i.severity == "error" for i in issues), issues=issues)
