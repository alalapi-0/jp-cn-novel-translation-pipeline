"""Tests for Workbench export boundaries."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from workbench.export_service import export_status, run_export  # noqa: E402
from workbench.project_registry import patch_project_review_state_cas  # noqa: E402
from workbench.review_state import approval_identity, patch_project_review_state  # noqa: E402


def _write_manifest(repo: Path) -> None:
    manifests = repo / "workspace" / "manifests"
    manifests.mkdir(parents=True)
    (manifests / "demo-jp-cn.json").write_text(
        json.dumps(
            {
                "project_id": "demo-jp-cn",
                "name": "Demo",
                "language_direction": "JP_TO_CN",
                "status": "draft",
                "chapters": 1,
                "segments": [
                    {
                        "id": "seg-1",
                        "source": "source",
                        "draft": "译文",
                        "status": "approved",
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    segment = {
        "id": "seg-1",
        "source": "source",
        "draft": "译文",
        "status": "approved",
    }
    identity = approval_identity(
        project_id="demo-jp-cn",
        language_direction="JP_TO_CN",
        segment=segment,
    )
    patch_project_review_state_cas(
        repo,
        "demo-jp-cn",
        segments={
            "seg-1": {"status": "approved", "expected_identity": identity},
        },
    )


def test_manifest_export_writes_workbench_exports_not_output_cn(tmp_path: Path) -> None:
    _write_manifest(tmp_path)

    result = run_export(
        tmp_path,
        source="manifest",
        project_id="demo-jp-cn",
        status_mode="approved",
    )

    assert result["translated_path"] == "workspace/workbench_exports/translated/workbench_demo-jp-cn_cn.md"
    assert result["bilingual_path"] == "workspace/workbench_exports/bilingual/workbench_demo-jp-cn_bilingual.md"
    assert not (tmp_path / "output_cn" / "translated" / "workbench_demo-jp-cn_cn.md").exists()


def test_embedded_and_legacy_unbound_approval_require_reapproval(tmp_path: Path) -> None:
    _write_manifest(tmp_path)
    review_path = tmp_path / "workspace" / "review_state.json"
    review_path.unlink()
    patch_project_review_state(
        tmp_path,
        "demo-jp-cn",
        segments={"seg-1": {"status": "approved", "note": "legacy note"}},
    )

    with pytest.raises(ValueError, match="no approved segments"):
        run_export(
            tmp_path,
            source="manifest",
            project_id="demo-jp-cn",
            status_mode="approved",
        )

    state = json.loads(review_path.read_text(encoding="utf-8"))
    assert state["projects"]["demo-jp-cn"]["segments"]["seg-1"]["note"] == "legacy note"


def test_approval_identity_cannot_be_inherited_across_projects(tmp_path: Path) -> None:
    segment = {"id": "seg-1", "source": "same", "draft": "相同", "status": "pending"}
    manifests = tmp_path / "workspace" / "manifests"
    manifests.mkdir(parents=True)
    for project_id in ("project-a", "project-b"):
        (manifests / f"{project_id}.json").write_text(
            json.dumps(
                {
                    "project_id": project_id,
                    "name": project_id,
                    "language_direction": "JP_TO_CN",
                    "segments": [segment],
                }
            ),
            encoding="utf-8",
        )
    identity_a = approval_identity(
        project_id="project-a",
        language_direction="JP_TO_CN",
        segment=segment,
    )
    patch_project_review_state(
        tmp_path,
        "project-b",
        segments={
            "seg-1": {"status": "approved", "approval_identity": identity_a},
        },
    )

    with pytest.raises(ValueError, match="no approved segments"):
        run_export(
            tmp_path,
            source="manifest",
            project_id="project-b",
            status_mode="approved",
        )


def test_runs_export_is_disabled(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="workspace/runs export is disabled"):
        run_export(tmp_path, source="runs")


def test_export_status_reports_singleton_final_separately(tmp_path: Path) -> None:
    final_path = tmp_path / "output_cn" / "translated" / "full_volume_cn.md"
    final_path.parent.mkdir(parents=True)
    final_path.write_text("最终稿\n", encoding="utf-8")
    manifest_path = tmp_path / "output_cn" / "final_export_manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "canonical_final_translation_count": 1,
                "final_translation_policy": "singleton_full_volume_cn",
            }
        ),
        encoding="utf-8",
    )

    status = export_status(tmp_path)

    assert status["translated_dir"] == "workspace/workbench_exports/translated"
    assert status["production_summary"]["canonical_final_translation"] == "output_cn/translated/full_volume_cn.md"
    assert status["production_summary"]["canonical_final_exists"] is True
    assert status["production_summary"]["canonical_final_translation_count"] == 1
