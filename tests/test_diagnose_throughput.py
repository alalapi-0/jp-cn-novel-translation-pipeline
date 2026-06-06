"""Tests for read-only throughput diagnostics."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "diagnose_throughput.py"


def _load_module():
    mod_name = "light_novel_diagnose_throughput_test"
    spec = importlib.util.spec_from_file_location(mod_name, SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_build_metrics_from_synthetic_workspace(monkeypatch, tmp_path):
    diag = _load_module()
    workspace = tmp_path / "workspace"
    runtime = tmp_path / ".agent_runtime"
    run_dir = workspace / "runs" / "run_001_draft_stage_b_50ch"
    model_dir = workspace / "model_runs"
    checkpoint_dir = workspace / "checkpoints"
    docs_dir = tmp_path / "docs"

    run_dir.mkdir(parents=True)
    model_dir.mkdir(parents=True)
    checkpoint_dir.mkdir(parents=True)
    runtime.mkdir()
    for name in ("real_api_reports", "inspection_reports", "quality_reports", "fix_reports"):
        (runtime / name).mkdir()

    (run_dir / "run_metadata.json").write_text(
        json.dumps(
            {
                "run_id": "run_001_draft_stage_b_50ch",
                "scope": "draft_stage_b_50ch",
                "started_at": "2026-06-01T00:00:00+00:00",
                "provider_mode": "real/openrouter",
                "model_name": "model-a",
                "summary": {"api_calls": 1, "spent_usd": 0.1, "spent_tokens": 100},
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "segments.json").write_text(
        json.dumps(
            {
                "chapters": [
                    {
                        "chapter_id": "ch-001",
                        "segments": [
                            {
                                "segment_id": "s1",
                                "draft_text": "draft",
                                "refined_text": "refined",
                            }
                        ],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (run_dir / "draft_quality_report.json").write_text(
        json.dumps({"passed": True, "stage_c_eligible": True, "generated_at": "2026-06-01T00:01:00+00:00"}),
        encoding="utf-8",
    )
    (model_dir / "m1.json").write_text(
        json.dumps(
            {
                "provider_id": "openrouter",
                "model_name": "model-a",
                "pipeline_stage": "draft_translation",
                "status": "ok",
                "latency_ms": 1000,
                "usage": {"total_tokens": 100},
                "cost_estimate_usd": 0.001,
                "finished_at": "2026-06-01T00:02:00+00:00",
            }
        ),
        encoding="utf-8",
    )
    (checkpoint_dir / "run_001_draft_stage_b_50ch.json").write_text(
        json.dumps({"status": "completed", "completed_segments": ["s1"]}),
        encoding="utf-8",
    )
    (runtime / "status.json").write_text(json.dumps({"round": 1}), encoding="utf-8")
    (runtime / "queue.jsonl").write_text("", encoding="utf-8")
    (runtime / "blockers.jsonl").write_text("", encoding="utf-8")

    monkeypatch.setattr(diag, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(diag, "WORKSPACE", workspace)
    monkeypatch.setattr(diag, "DIAG_DIR", workspace / "diagnostics")
    monkeypatch.setattr(diag, "SUMMARY_PATH", docs_dir / "throughput_metrics_summary.md")
    monkeypatch.setattr(diag, "JSON_PATH", workspace / "diagnostics" / "throughput_metrics.json")

    metrics = diag.build_metrics()
    assert metrics["runs"]["totals"]["draft_chapters"] == 1
    assert metrics["runs"]["totals"]["refined_chapters"] == 1
    assert metrics["model_runs"]["count"] == 1

    diag.write_summary(metrics)
    summary = (docs_dir / "throughput_metrics_summary.md").read_text(encoding="utf-8")
    assert "Throughput Metrics Summary" in summary
    assert "source_text" not in summary
