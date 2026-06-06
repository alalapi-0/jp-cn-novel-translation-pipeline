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
