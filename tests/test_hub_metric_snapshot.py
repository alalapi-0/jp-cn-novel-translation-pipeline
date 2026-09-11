"""Project-side entry tests for the shared Hub metric snapshot."""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "export_hub_metric_snapshot.py"
OBSERVED_AT = "2026-09-10T16:00:00+00:00"


def _load_script(name: str = "light_novel_hub_metric_export"):
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _write_json(root: Path, relative: str, value: dict) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value), encoding="utf-8")


def _write_metadata_fixture(root: Path) -> Path:
    _write_json(
        root,
        "workspace/manifests/chapter_manifest.json",
        {
            "schema_version": 1,
            "generated_at": OBSERVED_AT,
            "total_expected_chapters": 2,
            "chapters": {
                "ch-1": {"chapter_id": "ch-1", "draft_status": "complete"},
                "ch-2": {"chapter_id": "ch-2", "draft_status": "partial"},
            },
        },
    )
    _write_json(
        root,
        "output_cn/final_export_manifest.json",
        {
            "schema": "consistency_final_export_v2",
            "generated_at": OBSERVED_AT,
            "chapters_discovered": 2,
            "chapters_exported": 1,
            "chapters_incomplete": ["ch-2"],
            "chapters_missing": [],
        },
    )
    _write_json(
        root,
        "workspace/stage_state_production.json",
        {"run_id": "run_fixture", "status": "in_progress"},
    )
    progress = root / "workspace/runs/run_fixture/run_progress.json"
    _write_json(
        root,
        "workspace/runs/run_fixture/run_progress.json",
        {
            "schema_version": 1,
            "run_id": "run_fixture",
            "status": "in_progress",
            "total_segments": 4,
            "completed_segments": 3,
            "pending_segments": 1,
            "updated_at": OBSERVED_AT,
        },
    )
    return progress


def test_entry_delegates_collection_schema_and_atomic_write_to_shared_hub(
    tmp_path: Path,
) -> None:
    module = _load_script()
    project_root = tmp_path / "project"
    project_root.mkdir()
    hub_root = tmp_path / "hub"
    calls: dict = {}

    def collect(root, project_id, observed_at):
        calls["collector"] = (root, project_id, observed_at)
        return {"metrics": [], "issues": [], "disposition": "partial", "source_version": "fixture"}

    def export(root, project_id, collectors, **kwargs):
        observed_at = kwargs["clock"]()
        calls["export"] = (root, project_id, sorted(collectors), kwargs)
        collectors["business"](root, project_id, observed_at)
        return {
            "project_id": project_id,
            "snapshot_id": "sha256:" + "a" * 64,
            "disposition": "partial",
            "metrics": [],
            "issues": [],
        }

    module._shared_hub_modules = lambda selected: (export, collect)
    result = module.export_snapshot(
        project_root,
        hub_root,
        clock=lambda: OBSERVED_AT,
    )

    assert result["project_id"] == "light-novel"
    assert calls["collector"] == (project_root, "light-novel", OBSERVED_AT)
    assert calls["export"][2] == ["business"]
    assert calls["export"][3]["exporter_id"] == "light-novel-metadata"
    assert calls["export"][3]["exporter_version"] == "1.0"


def test_symlinked_hub_root_is_rejected_before_import(tmp_path: Path) -> None:
    module = _load_script("light_novel_hub_metric_export_symlink")
    target = tmp_path / "hub"
    (target / "src/hub").mkdir(parents=True)
    for name in ("metric_export.py", "metric_novel.py", "metric_snapshot.py"):
        (target / "src/hub" / name).write_text("", encoding="utf-8")
    link = tmp_path / "hub-link"
    link.symlink_to(target, target_is_directory=True)

    with pytest.raises(ValueError, match="ordinary directory"):
        module._shared_hub_modules(link)


def test_cli_emits_only_a_bounded_receipt(tmp_path: Path, capsys) -> None:
    module = _load_script("light_novel_hub_metric_export_cli")
    module.export_snapshot = lambda project_root, hub_root: {
        "project_id": "light-novel",
        "snapshot_id": "sha256:" + "b" * 64,
        "disposition": "partial",
        "metrics": [{}, {}],
        "issues": [{}],
    }

    assert module.main(["--hub-root", str(tmp_path)]) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt == {
        "schema": "light_novel_hub_export_receipt_v1",
        "project_id": "light-novel",
        "snapshot_id": "sha256:" + "b" * 64,
        "disposition": "partial",
        "metric_count": 2,
        "issue_count": 1,
        "snapshot_path": ".hub/status.json",
    }


@pytest.mark.skipif(
    not os.environ.get("PROJECT_DATA_HUB_ROOT"),
    reason="shared Hub checkout not supplied to this standalone repository",
)
def test_shared_snapshot_is_local_idempotent_restartable_and_unknown_safe(
    tmp_path: Path,
    capsys,
) -> None:
    hub_root = Path(os.environ["PROJECT_DATA_HUB_ROOT"])
    project_root = tmp_path / "project"
    project_root.mkdir()
    progress_path = _write_metadata_fixture(project_root)

    first_module = _load_script("light_novel_hub_metric_export_first")
    first = first_module.export_snapshot(
        project_root,
        hub_root,
        clock=lambda: OBSERVED_AT,
    )
    restarted_module = _load_script("light_novel_hub_metric_export_restarted")
    repeated = restarted_module.export_snapshot(
        project_root,
        hub_root,
        clock=lambda: OBSERVED_AT,
    )

    assert repeated == first
    assert json.loads((project_root / ".hub/status.json").read_text()) == first
    assert list((project_root / ".hub").glob(".status.*.tmp")) == []
    first_rows = {row["metric_id"]: row for row in first["metrics"]}
    review = first_rows["novel.review_pending"]
    assert review["value"] is None
    assert review["quality"] == "unknown"
    assert review["reason"]

    progress = json.loads(progress_path.read_text())
    progress.update(completed_segments=2, pending_segments=2)
    progress_path.write_text(json.dumps(progress), encoding="utf-8")
    changed = restarted_module.export_snapshot(
        project_root,
        hub_root,
        clock=lambda: OBSERVED_AT,
    )
    changed_rows = {row["metric_id"]: row for row in changed["metrics"]}
    changed_ids = {
        metric_id
        for metric_id in first_rows
        if first_rows[metric_id] != changed_rows[metric_id]
    }
    assert changed_ids == {
        "novel.batch_completed_segments",
        "novel.batch_pending_segments",
    }
    assert changed_rows["novel.review_pending"]["value"] is None
    assert changed_rows["novel.review_pending"]["quality"] == "unknown"

    assert restarted_module.main(
        ["--hub-root", str(hub_root), "--project-root", str(project_root)]
    ) == 0
    receipt = json.loads(capsys.readouterr().out)
    assert receipt["project_id"] == "light-novel"
    assert receipt["snapshot_path"] == ".hub/status.json"
    assert receipt["metric_count"] == len(changed["metrics"])
