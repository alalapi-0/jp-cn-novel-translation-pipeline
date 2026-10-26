"""Stage C refine pilot tests (dry-run only)."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "refine_stage_c.py"
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "refine_pilot_segments.json"


@pytest.fixture()
def pilot_run_dir(tmp_path: Path) -> Path:
    run_id = "test_refine_pilot_run"
    run_root = tmp_path / "workspace" / "runs" / run_id
    run_root.mkdir(parents=True)
    shutil.copy(FIXTURE, run_root / "segments.json")
    (run_root / "draft_quality_report.json").write_text(
        json.dumps({"stage_c_eligible": True, "passed": True}) + "\n",
        encoding="utf-8",
    )
    state = {
        "phase": "draft",
        "run_id": run_id,
        "refine_blocked": True,
    }
    (tmp_path / "workspace" / "stage_state.json").write_text(
        json.dumps(state) + "\n",
        encoding="utf-8",
    )
    return run_root


def test_refine_controlled_dry_run_60_segments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "false")
    monkeypatch.setenv("STAGE_C_MAX_SEGMENTS", "100")
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from translation.refine_runner import run_refine_controlled

    run_id = "test_refine_60"
    run_root = tmp_path / "workspace" / "runs" / run_id
    run_root.mkdir(parents=True)
    segments = []
    for i in range(1, 61):
        segments.append(
            {
                "segment_id": f"ch-001-seg-{i:03d}",
                "source_text": f"src{i}",
                "draft_text": f"draft{i}",
            }
        )
    (run_root / "segments.json").write_text(
        json.dumps({"chapters": [{"chapter_id": "ch-001", "segments": segments}]}),
        encoding="utf-8",
    )
    (run_root / "draft_quality_report.json").write_text(
        json.dumps({"stage_c_eligible": True}),
        encoding="utf-8",
    )
    before = (run_root / 'segments.json').read_bytes()
    with pytest.raises(RuntimeError, match='legacy_refinement_disabled'):
        run_refine_controlled(repo_root=tmp_path, run_id=run_id, limit_segments=60, force_dry_run=True)
    assert (run_root / 'segments.json').read_bytes() == before
    assert not (run_root / 'run_progress.json').exists()


def test_refine_pilot_dry_run_module(pilot_run_dir: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "false")
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from translation.refine_runner import run_refine_pilot

    repo = pilot_run_dir.parent.parent.parent
    before = (pilot_run_dir / 'segments.json').read_bytes()
    with pytest.raises(RuntimeError, match='legacy_refinement_disabled'):
        run_refine_pilot(repo_root=repo, run_id=pilot_run_dir.name, limit_segments=10, force_dry_run=True)
    assert (pilot_run_dir / 'segments.json').read_bytes() == before
    assert not (pilot_run_dir / 'refine_diff.json').exists()


@pytest.mark.parametrize('legacy_override', ['', '1'])
def test_refine_stage_c_cli_disabled_by_default(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, legacy_override):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv('ALLOW_LEGACY_REFINEMENT', legacy_override)
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "false")
    run_id = "run_20260602_203645_draft_stage_b_50ch"
    stage_state = tmp_path / "stage_state.json"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--run-id",
            run_id,
            "--limit-segments",
            "3",
            "--dry-run",
            "--stage-state-path",
            str(stage_state),
            "--json",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
        env={**dict(**__import__("os").environ), "REAL_API_TESTS_ENABLED": "false"},
    )
    assert proc.returncode == 2
    payload = json.loads(proc.stdout)
    assert payload["reason"] == "legacy_refinement_disabled"
    assert not stage_state.exists()
