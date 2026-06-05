"""Tests for project_id validation."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from workbench.project_id import InvalidProjectIdError, is_test_project_id, validate_project_id  # noqa: E402


@pytest.mark.parametrize(
    "project_id",
    [
        "../etc",
        "..",
        ".",
        "foo/bar",
        "foo\\bar",
        "has space",
        "bad/id",
        "",
        "___",
    ],
)
def test_validate_project_id_rejects_invalid(project_id: str) -> None:
    with pytest.raises(InvalidProjectIdError):
        validate_project_id(project_id)


@pytest.mark.parametrize(
    "project_id",
    [
        "demo-jp-cn",
        "quickstart-demo",
        "user_project-1",
    ],
)
def test_validate_project_id_accepts_safe_ids(project_id: str) -> None:
    assert validate_project_id(project_id) == project_id


def test_is_test_project_id() -> None:
    assert is_test_project_id("pw-pending-123") is True
    assert is_test_project_id("codex-demo") is True
    assert is_test_project_id("dupe-demo-jp-cn") is True
    assert is_test_project_id("demo-jp-cn") is False
