"""Tests for workspace review state persistence."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from workbench.review_state import (  # noqa: E402
    approval_identity,
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


def test_approval_identity_binds_every_canonical_dimension() -> None:
    base = {
        "project_id": "project-a",
        "language_direction": "JP_TO_CN",
        "segment": {"id": "seg-1", "source": " source ", "draft": " target "},
    }
    original = approval_identity(**base)
    variants = [
        {**base, "project_id": "project-b"},
        {**base, "language_direction": "CN_TO_JP"},
        {**base, "segment": {**base["segment"], "id": "seg-2"}},
        {**base, "segment": {**base["segment"], "source": "source"}},
        {**base, "segment": {**base["segment"], "draft": "target"}},
    ]
    assert original.startswith("sha256:")
    assert len(original) == 71
    assert all(approval_identity(**variant) != original for variant in variants)


def test_cross_project_review_patches_do_not_lose_updates(tmp_path: Path) -> None:
    barrier = threading.Barrier(2)

    def patch(project_id: str) -> None:
        barrier.wait()
        for index in range(25):
            patch_project_review_state(
                tmp_path,
                project_id,
                segments={f"seg-{index}": {"status": "rejected"}},
            )

    first = threading.Thread(target=patch, args=("project-a",))
    second = threading.Thread(target=patch, args=("project-b",))
    first.start()
    second.start()
    first.join()
    second.join()

    assert len(get_project_review_state(tmp_path, "project-a")["segments"]) == 25
    assert len(get_project_review_state(tmp_path, "project-b")["segments"]) == 25
