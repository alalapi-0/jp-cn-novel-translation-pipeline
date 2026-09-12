"""Tests for manifest write locking."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from workbench import project_registry as registry  # noqa: E402
from workbench import review_state as review_state_module  # noqa: E402
from workbench.project_registry import (  # noqa: E402
    ApprovalIdentityConflictError,
    ManifestWriteInProgressError,
    create_project_manifest,
    get_project_manifest,
    patch_project_review_state_cas,
    refresh_example_manifests,
    update_project_segments,
)
from workbench.review_state import approval_identity, get_project_review_state  # noqa: E402


def test_concurrent_update_project_segments_one_busy(tmp_path: Path) -> None:
    create_project_manifest(
        tmp_path,
        project_id="lock-test",
        name="Lock",
        language_direction="JP_TO_CN",
    )
    barrier = threading.Barrier(2)
    results: list[str] = []

    def worker(tag: str) -> None:
        barrier.wait()
        try:
            update_project_segments(
                tmp_path,
                "lock-test",
                [{"id": "seg-001", "source": tag, "draft": tag, "status": "pending"}],
            )
            results.append(f"ok:{tag}")
        except ManifestWriteInProgressError:
            results.append(f"busy:{tag}")

    t1 = threading.Thread(target=worker, args=("a",))
    t2 = threading.Thread(target=worker, args=("b",))
    t1.start()
    t2.start()
    t1.join()
    t2.join()
    assert any(r.startswith("ok:") for r in results)
    assert any(r.startswith("busy:") for r in results)


def test_manifest_change_blocks_concurrent_approval_then_rejects_stale_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    segment_a = {"id": "seg-001", "source": "A", "draft": "甲", "status": "pending"}
    segment_b = {"id": "seg-001", "source": "B", "draft": "乙", "status": "pending"}
    create_project_manifest(
        tmp_path,
        project_id="approval-lock-test",
        name="Lock",
        language_direction="JP_TO_CN",
        segments=[segment_a],
    )
    identity_a = approval_identity(
        project_id="approval-lock-test",
        language_direction="JP_TO_CN",
        segment=segment_a,
    )
    entered_save = threading.Event()
    release_save = threading.Event()
    original_save = registry._save_project_manifest_unlocked

    def delayed_save(repo_root: Path, data: dict):
        entered_save.set()
        assert release_save.wait(timeout=5)
        return original_save(repo_root, data)

    monkeypatch.setattr(registry, "_save_project_manifest_unlocked", delayed_save)
    updater = threading.Thread(
        target=update_project_segments,
        args=(tmp_path, "approval-lock-test", [segment_b]),
    )
    updater.start()
    assert entered_save.wait(timeout=5)

    with pytest.raises(ManifestWriteInProgressError):
        patch_project_review_state_cas(
            tmp_path,
            "approval-lock-test",
            segments={
                "seg-001": {
                    "status": "approved",
                    "expected_identity": identity_a,
                    "note": "must not be written",
                }
            },
        )
    release_save.set()
    updater.join(timeout=5)
    assert not updater.is_alive()

    with pytest.raises(ApprovalIdentityConflictError) as stale:
        patch_project_review_state_cas(
            tmp_path,
            "approval-lock-test",
            segments={
                "seg-001": {
                    "status": "approved",
                    "expected_identity": identity_a,
                    "note": "must not be written",
                }
            },
        )
    assert stale.value.error_code == "approval_identity_stale"
    assert get_project_review_state(tmp_path, "approval-lock-test")["segments"] == {}

    identity_b = approval_identity(
        project_id="approval-lock-test",
        language_direction="JP_TO_CN",
        segment=segment_b,
    )
    result = patch_project_review_state_cas(
        tmp_path,
        "approval-lock-test",
        segments={
            "seg-001": {"status": "approved", "expected_identity": identity_b},
        },
    )
    assert result["segments"]["seg-001"]["approval_identity"] == identity_b


def test_stale_rejection_cannot_override_fresh_approval(tmp_path: Path) -> None:
    project_id = "stale-rejection-test"
    segment_a = {"id": "seg-001", "source": "A", "draft": "甲"}
    segment_b = {"id": "seg-001", "source": "B", "draft": "乙"}
    create_project_manifest(
        tmp_path,
        project_id=project_id,
        name="Stale rejection",
        language_direction="JP_TO_CN",
        segments=[segment_a],
    )
    identity_a = approval_identity(
        project_id=project_id,
        language_direction="JP_TO_CN",
        segment=segment_a,
    )
    update_project_segments(tmp_path, project_id, [segment_b])
    identity_b = approval_identity(
        project_id=project_id,
        language_direction="JP_TO_CN",
        segment=segment_b,
    )
    patch_project_review_state_cas(
        tmp_path,
        project_id,
        segments={
            "seg-001": {
                "status": "approved",
                "expected_identity": identity_b,
                "note": "fresh B",
            }
        },
    )

    with pytest.raises(ApprovalIdentityConflictError) as stale:
        patch_project_review_state_cas(
            tmp_path,
            project_id,
            segments={
                "seg-001": {
                    "status": "rejected",
                    "expected_identity": identity_a,
                    "note": "stale A",
                }
            },
            issues={"stale": {"status": "resolved"}},
        )
    assert stale.value.error_code == "approval_identity_stale"
    state = get_project_review_state(tmp_path, project_id)
    assert state["segments"]["seg-001"]["status"] == "approved"
    assert state["segments"]["seg-001"]["approval_identity"] == identity_b
    assert state["segments"]["seg-001"]["note"] == "fresh B"
    assert state["issues"] == {}

    rejected = patch_project_review_state_cas(
        tmp_path,
        project_id,
        segments={
            "seg-001": {"status": "rejected", "expected_identity": identity_b},
        },
    )
    assert rejected["segments"]["seg-001"]["status"] == "rejected"
    assert rejected["segments"]["seg-001"]["approval_identity"] == identity_b


def test_refresh_cannot_replace_manifest_during_approval_cas(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    project_id = "refresh-cas-test"
    segment_a = {"id": "seg-001", "source": "A", "draft": "甲", "status": "pending"}
    segment_b = {"id": "seg-001", "source": "B", "draft": "乙", "status": "pending"}
    create_project_manifest(
        tmp_path,
        project_id=project_id,
        name="Current",
        language_direction="JP_TO_CN",
        segments=[segment_a],
    )
    example_dir = tmp_path / "data" / "examples"
    example_dir.mkdir(parents=True)
    (example_dir / "workbench_project.refresh-cas.example.json").write_text(
        json.dumps(
            {
                "project_id": project_id,
                "name": "Replacement",
                "language_direction": "JP_TO_CN",
                "segments": [segment_b],
            }
        ),
        encoding="utf-8",
    )
    identity_a = approval_identity(
        project_id=project_id,
        language_direction="JP_TO_CN",
        segment=segment_a,
    )
    entered_review_save = threading.Event()
    release_review_save = threading.Event()
    original_patch = review_state_module.patch_project_review_state

    def delayed_patch(*args, **kwargs):
        entered_review_save.set()
        assert release_review_save.wait(timeout=5)
        return original_patch(*args, **kwargs)

    monkeypatch.setattr(review_state_module, "patch_project_review_state", delayed_patch)
    result: dict = {}

    def approve() -> None:
        result.update(
            patch_project_review_state_cas(
                tmp_path,
                project_id,
                segments={
                    "seg-001": {
                        "status": "approved",
                        "expected_identity": identity_a,
                    }
                },
            )
        )

    approver = threading.Thread(target=approve)
    approver.start()
    assert entered_review_save.wait(timeout=5)
    with pytest.raises(ManifestWriteInProgressError):
        refresh_example_manifests(tmp_path)
    current = get_project_manifest(tmp_path, project_id)
    assert current is not None
    assert current.segments[0]["source"] == "A"

    release_review_save.set()
    approver.join(timeout=5)
    assert not approver.is_alive()
    assert result["segments"]["seg-001"]["approval_identity"] == identity_a


@pytest.mark.parametrize(
    "segment",
    [
        {"id": "seg-001", "source": "", "draft": "译文"},
        {"id": "seg-001", "source": "原文", "draft": "   "},
    ],
)
def test_formal_approval_rejects_blank_selected_content(
    tmp_path: Path,
    segment: dict,
) -> None:
    project_id = "blank-content-test"
    create_project_manifest(
        tmp_path,
        project_id=project_id,
        name="Blank",
        language_direction="JP_TO_CN",
        segments=[segment],
    )
    identity = approval_identity(
        project_id=project_id,
        language_direction="JP_TO_CN",
        segment=segment,
    )

    with pytest.raises(ApprovalIdentityConflictError) as invalid:
        patch_project_review_state_cas(
            tmp_path,
            project_id,
            segments={
                "seg-001": {"status": "approved", "expected_identity": identity},
            },
        )
    assert invalid.value.error_code == "approval_identity_invalid"
    assert get_project_review_state(tmp_path, project_id)["segments"] == {}
