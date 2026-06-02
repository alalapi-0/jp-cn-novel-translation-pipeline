"""Round 50 E2E trial script smoke tests."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
TRIAL_SCRIPT = REPO_ROOT / "scripts" / "run_round_50_e2e_trial.py"
SYNTHETIC_SOURCE = REPO_ROOT / "data" / "examples" / "e2e_trial_chapter.md"
SEGMENTS_PATH = REPO_ROOT / "workspace" / "e2e_trial" / "segments.json"
ISSUE_REPORT_PATH = REPO_ROOT / "workspace" / "review" / "issue_report.json"
EXPORT_META = REPO_ROOT / "workspace" / "e2e_trial" / "export" / "export_meta.json"


@pytest.fixture(scope="module")
def trial_result():
    proc = subprocess.run(
        [sys.executable, str(TRIAL_SCRIPT), "--skip-report"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    return proc


def test_e2e_trial_script_exits_zero(trial_result):
    assert trial_result.returncode == 0, trial_result.stdout + trial_result.stderr


def test_synthetic_source_exists():
    assert SYNTHETIC_SOURCE.is_file()
    text = SYNTHETIC_SOURCE.read_text(encoding="utf-8")
    assert "E2E Synthetic" in text or "合成试跑" in text
    assert "魔力結晶" in text


def test_trial_produces_segments_and_issues(trial_result):
    assert trial_result.returncode == 0
    assert SEGMENTS_PATH.is_file()
    doc = json.loads(SEGMENTS_PATH.read_text(encoding="utf-8"))
    segs = doc["paragraphs"][0]["segments"]
    assert len(segs) == 3
    assert any(s.get("human_edited") for s in segs)
    assert ISSUE_REPORT_PATH.is_file()
    report = json.loads(ISSUE_REPORT_PATH.read_text(encoding="utf-8"))
    assert report["summary"]["total"] >= 1


def test_export_not_marked_final(trial_result):
    assert trial_result.returncode == 0
    assert EXPORT_META.is_file()
    meta = json.loads(EXPORT_META.read_text(encoding="utf-8"))
    assert meta["final_status"] == "draft_not_final"
    assert meta["high_issues_unresolved"] is True
