"""Project ID validation and test-project classification."""

from __future__ import annotations

import re

PROJECT_ID_RE = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}$")

TEST_PROJECT_PREFIXES = ("pw-", "codex-", "dupe-")
TEST_PROJECT_EXACT = frozenset(
    {
        "quickstart-test",
        "review-state-test",
    }
)


class InvalidProjectIdError(ValueError):
    """Raised when project_id is empty or contains unsafe characters."""


def validate_project_id(project_id: str) -> str:
    """Return normalized project_id or raise InvalidProjectIdError."""
    raw = str(project_id or "")
    if raw != raw.strip():
        raise InvalidProjectIdError("project_id must not contain leading or trailing whitespace")
    normalized = raw.strip()
    if not normalized:
        raise InvalidProjectIdError("project_id is required")
    if normalized in {".", ".."}:
        raise InvalidProjectIdError("project_id must not be '.' or '..'")
    if ".." in normalized:
        raise InvalidProjectIdError("project_id must not contain '..'")
    if "/" in normalized or "\\" in normalized:
        raise InvalidProjectIdError("project_id must not contain path separators")
    if any(ch.isspace() for ch in normalized):
        raise InvalidProjectIdError("project_id must not contain whitespace")
    if not PROJECT_ID_RE.match(normalized):
        raise InvalidProjectIdError(
            "project_id must start with a letter or digit and contain only letters, digits, '_' or '-'"
        )
    return normalized


def is_test_project_id(project_id: str) -> bool:
    if project_id in TEST_PROJECT_EXACT:
        return True
    return any(project_id.startswith(prefix) for prefix in TEST_PROJECT_PREFIXES)
