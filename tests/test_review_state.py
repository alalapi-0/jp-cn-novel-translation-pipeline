"""Tests for workspace review state persistence."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from workbench.review_state import (  # noqa: E402
    get_project_review_state,
    patch_project_review_state,
)


def test_review_state_persists_segment_and_issue(tmp_path: Path) -> None:
    patch_project_review_state(
        tmp_path,
        "demo-jp-cn",
        segments={"seg-001": {"status": "approved"}},
        issues={"ri-0001": {"status": "resolved"}},
    )
    state = get_project_review_state(tmp_path, "demo-jp-cn")
    assert state["segments"]["seg-001"]["status"] == "approved"
    assert state["issues"]["ri-0001"]["status"] == "resolved"

    reloaded = get_project_review_state(tmp_path, "demo-jp-cn")
    assert reloaded["segments"]["seg-001"]["status"] == "approved"
