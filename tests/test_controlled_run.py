"""Tests for controlled run checkpoint."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from providers.controlled_run import ControlledRunConfig, ControlledRunManager


def test_checkpoint_persists_segments(tmp_path):
    cfg = ControlledRunConfig(enabled=True, checkpoint_dir=tmp_path, run_id="trial-1")
    mgr = ControlledRunManager(cfg)
    mgr.mark_segment_done("seg-001", tokens=100, cost_usd=0.001)
    mgr.mark_segment_done("seg-002", tokens=50, cost_usd=0.0005)

    mgr2 = ControlledRunManager(cfg)
    assert mgr2.is_segment_done("seg-001")
    assert mgr2.is_segment_done("seg-002")
    assert mgr2.checkpoint.spent_tokens == 150


def test_require_enabled_raises_when_disabled(tmp_path):
    cfg = ControlledRunConfig(enabled=False, checkpoint_dir=tmp_path)
    mgr = ControlledRunManager(cfg)
    with pytest.raises(RuntimeError, match="controlled run is disabled"):
        mgr.require_enabled()


def test_abort_writes_status(tmp_path):
    cfg = ControlledRunConfig(enabled=True, checkpoint_dir=tmp_path, run_id="abort-test")
    mgr = ControlledRunManager(cfg)
    mgr.abort("budget_exceeded")
    data = json.loads((tmp_path / "abort-test.json").read_text(encoding="utf-8"))
    assert data["status"] == "aborted:budget_exceeded"
