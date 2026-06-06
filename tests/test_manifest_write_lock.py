"""Tests for manifest write locking."""

from __future__ import annotations

import sys
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from workbench.project_registry import (  # noqa: E402
    ManifestWriteInProgressError,
    create_project_manifest,
    update_project_segments,
)


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
