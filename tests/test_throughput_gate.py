"""Tests for throughput safety gate."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_gate():
    spec = importlib.util.spec_from_file_location(
        "throughput_gate_test",
        REPO_ROOT / "scripts" / "throughput_gate.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_gate_allow_clean_workspace(tmp_path, monkeypatch):
    gate = _load_gate()
    workspace = tmp_path / "workspace"
    runs = workspace / "runs" / "run_001_draft_stage_b_50ch"
    runs.mkdir(parents=True)
    (runs / "run_metadata.json").write_text(
        json.dumps({"run_id": "run_001_draft_stage_b_50ch", "chapter_offset": 0}),
        encoding="utf-8",
    )
    (runs / "segments.json").write_text(
        json.dumps(
            {
                "chapters": [
                    {
                        "chapter_id": "ch-001",
                        "segments": [
                            {"segment_id": "s1", "draft_text": "d", "refined_text": "r"}
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (runs / "run_progress.json").write_text(
        json.dumps({"status": "completed", "run_id": "run_001_draft_stage_b_50ch"}),
        encoding="utf-8",
    )
    (workspace / "checkpoints").mkdir(parents=True)
    (workspace / "checkpoints" / "run_001_draft_stage_b_50ch.json").write_text(
        json.dumps({"status": "completed", "completed_segments": ["s1"]}),
        encoding="utf-8",
    )
    (workspace / "stage_state.json").write_text(
        json.dumps({"status": "completed", "run_id": "run_001_draft_stage_b_50ch"}),
        encoding="utf-8",
    )

    monkeypatch.setattr(gate, "WORKSPACE", workspace)
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)

    result = gate.evaluate_gate()
    assert result["decision"] in {"ALLOW", "WARN"}
    assert result["exportable_chapters"] == 1
    assert result["draft_completed_chapters"] == 1
    assert result["refined_exportable_chapters"] == 1


def test_gate_split_draft_vs_refined_metrics(tmp_path, monkeypatch):
    gate = _load_gate()
    workspace = tmp_path / "workspace"
    runs = workspace / "runs" / "run_split_draft_stage_b_50ch"
    runs.mkdir(parents=True)
    (runs / "run_metadata.json").write_text(
        json.dumps({"run_id": "run_split_draft_stage_b_50ch", "chapter_offset": 0}),
        encoding="utf-8",
    )
    (runs / "segments.json").write_text(
        json.dumps(
            {
                "chapters": [
                    {
                        "chapter_id": "ch-001",
                        "segments": [
                            {"segment_id": "s1", "draft_text": "d", "refined_text": ""},
                            {"segment_id": "s2", "draft_text": "d2", "refined_text": "r2"},
                        ],
                    },
                    {
                        "chapter_id": "ch-002",
                        "segments": [
                            {"segment_id": "s3", "draft_text": "d3", "refined_text": "r3"},
                        ],
                    },
                ]
            }
        ),
        encoding="utf-8",
    )
    (runs / "run_progress.json").write_text(
        json.dumps({"status": "completed", "run_id": "run_split_draft_stage_b_50ch"}),
        encoding="utf-8",
    )
    (workspace / "checkpoints").mkdir(parents=True)
    (workspace / "checkpoints" / "run_split_draft_stage_b_50ch.json").write_text(
        json.dumps({"status": "completed", "completed_segments": ["s1"]}),
        encoding="utf-8",
    )
    (workspace / "stage_state.json").write_text(
        json.dumps({"status": "completed", "run_id": "run_split_draft_stage_b_50ch"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "WORKSPACE", workspace)
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)

    result = gate.evaluate_gate()
    assert result["draft_completed_chapters"] == 2
    assert result["refined_exportable_chapters"] == 1


def test_gate_ignores_diagnostic_state_conflict(tmp_path, monkeypatch):
    gate = _load_gate()
    workspace = tmp_path / "workspace"
    run_dir = workspace / "runs" / "asset-context-user-verify"
    run_dir.mkdir(parents=True)
    (run_dir / "run_progress.json").write_text(
        json.dumps({"status": "failed", "run_id": "asset-context-user-verify"}),
        encoding="utf-8",
    )
    (workspace / "checkpoints").mkdir(parents=True)
    (workspace / "checkpoints" / "asset-context-user-verify.json").write_text(
        json.dumps({"status": "aborted:test", "completed_segments": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "WORKSPACE", workspace)
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)

    result = gate.evaluate_gate()
    assert not any("state_conflict: run_id=asset-context-user-verify" in b for b in result["blocks"])
    rows = gate._analyze_runs()
    assert not any(r["run_id"] == "asset-context-user-verify" for r in rows)


def test_gate_warns_refine_pending_after_draft_complete(tmp_path, monkeypatch):
    gate = _load_gate()
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    prod_state = workspace / "stage_state_production.json"
    prod_state.write_text(
        json.dumps(
            {
                "phase": "draft",
                "status": "completed",
                "run_id": "run_prod_draft_done",
                "refine_blocked": True,
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "WORKSPACE", workspace)
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)

    result = gate.evaluate_gate()
    assert any("refine_pending" in w for w in result["warnings"])


def _write_run(workspace, run_id, *, offset, cp_status, progress_status):
    runs = workspace / "runs" / run_id
    runs.mkdir(parents=True)
    (runs / "run_metadata.json").write_text(
        json.dumps({"run_id": run_id, "chapter_offset": offset}),
        encoding="utf-8",
    )
    (runs / "segments.json").write_text(
        json.dumps({"chapters": [{"chapter_id": "ch-x", "segments": [{"segment_id": "s1", "draft_text": "d"}]}]}),
        encoding="utf-8",
    )
    (runs / "run_progress.json").write_text(
        json.dumps({"status": progress_status, "run_id": run_id}),
        encoding="utf-8",
    )
    (workspace / "checkpoints").mkdir(parents=True, exist_ok=True)
    (workspace / "checkpoints" / f"{run_id}.json").write_text(
        json.dumps({"status": cp_status, "completed_segments": ["s1"]}),
        encoding="utf-8",
    )


def test_gate_single_backfill_in_progress_is_warning_not_block(tmp_path, monkeypatch):
    """Gap backfill: one in-progress run below completed offsets must pass."""
    gate = _load_gate()
    workspace = tmp_path / "workspace"
    _write_run(
        workspace,
        "run_hi_draft_stage_b_50ch",
        offset=238,
        cp_status="completed",
        progress_status="completed",
    )
    _write_run(
        workspace,
        "run_backfill_draft_stage_b_50ch",
        offset=190,
        cp_status="in_progress",
        progress_status="in_progress",
    )
    (workspace / "stage_state.json").write_text(
        json.dumps({"status": "completed", "run_id": "run_hi_draft_stage_b_50ch"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "WORKSPACE", workspace)
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)

    result = gate.evaluate_gate()
    assert not any("offset_skip" in b for b in result["blocks"])
    assert any("backfill_in_progress" in w for w in result["warnings"])


def test_gate_multiple_in_progress_offsets_still_block(tmp_path, monkeypatch):
    gate = _load_gate()
    workspace = tmp_path / "workspace"
    _write_run(
        workspace,
        "run_a_draft_stage_b_50ch",
        offset=190,
        cp_status="in_progress",
        progress_status="in_progress",
    )
    _write_run(
        workspace,
        "run_b_draft_stage_b_50ch",
        offset=250,
        cp_status="in_progress",
        progress_status="in_progress",
    )
    (workspace / "stage_state.json").write_text(
        json.dumps({"status": "completed", "run_id": "run_a_draft_stage_b_50ch"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "WORKSPACE", workspace)
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)

    result = gate.evaluate_gate()
    assert any("offset_skip" in b for b in result["blocks"])


def test_gate_block_state_conflict(tmp_path, monkeypatch):
    gate = _load_gate()
    workspace = tmp_path / "workspace"
    cp_dir = workspace / "checkpoints"
    cp_dir.mkdir(parents=True)
    (cp_dir / "run_conflict.json").write_text(
        json.dumps({"status": "completed", "completed_segments": ["s1"]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "WORKSPACE", workspace)
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)

    result = gate.evaluate_gate()
    assert result["decision"] == "BLOCK"
    assert any("completed_run_missing_artifacts" in b for b in result["blocks"])


def test_gate_skips_diagnostic_realapi_runs_in_analysis(tmp_path, monkeypatch):
    gate = _load_gate()
    workspace = tmp_path / "workspace"
    diag_id = "run_20260606_082933_realapi_diagnostic_translate_dryrun"
    run_dir = workspace / "runs" / diag_id
    run_dir.mkdir(parents=True)
    (run_dir / "run_progress.json").write_text(
        json.dumps({"status": "in_progress", "run_id": diag_id}),
        encoding="utf-8",
    )
    (workspace / "checkpoints").mkdir(parents=True)
    (workspace / "checkpoints" / f"{diag_id}.json").write_text(
        json.dumps({"status": "in_progress", "completed_segments": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "WORKSPACE", workspace)
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)

    rows = gate._analyze_runs()
    assert not any(r["run_id"] == diag_id for r in rows)


def test_gate_duplicate_worker_is_warn_not_block(tmp_path, monkeypatch):
    gate = _load_gate()
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "stage_state_production.json").write_text(
        json.dumps({"status": "in_progress", "run_id": "run_dup"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "WORKSPACE", workspace)
    monkeypatch.setattr(gate, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(
        gate._registry,
        "summarize_registry",
        lambda: {
            "active_workers": [
                {"pid": 1, "task_type": "translate", "run_id": "run_a"},
                {"pid": 2, "task_type": "refine", "run_id": "run_b"},
            ],
            "active_count": 2,
        },
    )

    result = gate.evaluate_gate()
    assert result["decision"] == "WARN"
    assert not any("duplicate_worker" in b for b in result["blocks"])
    assert any("duplicate_worker" in w for w in result["warnings"])
    assert any("duplicate_worker" in sb for sb in result["soft_blocks"])
