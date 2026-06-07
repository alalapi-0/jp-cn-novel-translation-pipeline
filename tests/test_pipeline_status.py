"""Tests for production pipeline status aggregation."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from workbench.pipeline_status import (  # noqa: E402
    build_pipeline_status,
    list_production_runs,
    resolve_segment_progress,
)


def test_pipeline_status_completed_segments_max_checkpoint(tmp_path: Path) -> None:
    repo = tmp_path
    workspace = repo / "workspace"
    run_id = "run_progress_max_test"
    run_root = workspace / "runs" / run_id
    run_root.mkdir(parents=True)
    (workspace / "stage_state_production.json").write_text(
        json.dumps({"run_id": run_id, "phase": "draft", "status": "in_progress"}),
        encoding="utf-8",
    )
    (run_root / "run_metadata.json").write_text(
        json.dumps({"chapter_offset": 170, "limit_chapters": 50}),
        encoding="utf-8",
    )
    (run_root / "run_progress.json").write_text(
        json.dumps({"completed_segments": 40, "total_segments": 100, "status": "in_progress"}),
        encoding="utf-8",
    )
    (workspace / "checkpoints").mkdir(parents=True)
    (workspace / "checkpoints" / f"{run_id}.json").write_text(
        json.dumps({"status": "in_progress", "completed_segments": ["s"] * 55}),
        encoding="utf-8",
    )

    status = build_pipeline_status(repo)
    assert status["completed_segments"] == 55
    assert status["segment_progress_label"] == "55/100"


def test_list_production_runs_uses_checkpoint_max(tmp_path: Path) -> None:
    repo = tmp_path
    workspace = repo / "workspace"
    run_id = "run_20260607_040204_draft_stage_b_50ch"
    run_root = workspace / "runs" / run_id
    run_root.mkdir(parents=True)
    (workspace / "stage_state_production.json").write_text(
        json.dumps({"run_id": "run_other_draft_stage_b_50ch", "phase": "refine", "status": "in_progress"}),
        encoding="utf-8",
    )
    (run_root / "run_metadata.json").write_text(
        json.dumps({"chapter_offset": 170, "limit_chapters": 50}),
        encoding="utf-8",
    )
    (run_root / "run_progress.json").write_text(
        json.dumps({"completed_segments": 111, "total_segments": 6984, "status": "in_progress"}),
        encoding="utf-8",
    )
    (workspace / "checkpoints").mkdir(parents=True)
    (workspace / "checkpoints" / f"{run_id}.json").write_text(
        json.dumps({"status": "in_progress", "completed_segments": ["s"] * 399}),
        encoding="utf-8",
    )

    rows = list_production_runs(repo)
    assert len(rows) == 1
    assert rows[0]["completed_segments"] == 399
    assert rows[0]["segment_progress_label"] == "399/6984"


def test_active_run_cards_parallel_refine_and_draft(tmp_path: Path) -> None:
    repo = tmp_path
    workspace = repo / "workspace"
    refine_id = "run_20260605_111734_draft_stage_b_50ch"
    draft_id = "run_20260607_040204_draft_stage_b_50ch"
    for run_id, offset, done, total in [
        (refine_id, 150, 1800, 2196),
        (draft_id, 170, 111, 6984),
    ]:
        run_root = workspace / "runs" / run_id
        run_root.mkdir(parents=True)
        (run_root / "run_metadata.json").write_text(
            json.dumps({"chapter_offset": offset, "limit_chapters": 50}),
            encoding="utf-8",
        )
        (run_root / "run_progress.json").write_text(
            json.dumps({"completed_segments": done, "total_segments": total, "status": "in_progress"}),
            encoding="utf-8",
        )
    (workspace / "checkpoints").mkdir(parents=True)
    (workspace / "stage_state_production.json").write_text(
        json.dumps(
            {
                "run_id": refine_id,
                "phase": "refine",
                "stage": "refine_stage_c",
                "status": "in_progress",
            }
        ),
        encoding="utf-8",
    )

    status = build_pipeline_status(repo)
    cards = status["active_run_cards"]
    run_ids = {c["run_id"] for c in cards}
    assert refine_id in run_ids
    assert draft_id in run_ids
    refine_card = next(c for c in cards if c["run_id"] == refine_id)
    assert refine_card["phase"] == "refine"
    assert refine_card["task_label"] == "精修 Stage C"


def test_resolve_segment_progress_helper(tmp_path: Path) -> None:
    repo = tmp_path
    run_id = "run_helper_test"
    run_root = repo / "workspace" / "runs" / run_id
    run_root.mkdir(parents=True)
    (run_root / "run_progress.json").write_text(
        json.dumps({"completed_segments": 10, "total_segments": 50}),
        encoding="utf-8",
    )
    (repo / "workspace" / "checkpoints").mkdir(parents=True)
    (repo / "workspace" / "checkpoints" / f"{run_id}.json").write_text(
        json.dumps({"completed_segments": ["a"] * 25}),
        encoding="utf-8",
    )
    seg = resolve_segment_progress(repo, run_id)
    assert seg["completed_segments"] == 25
    assert seg["segment_progress_label"] == "25/50"
