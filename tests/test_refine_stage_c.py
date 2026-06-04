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


def test_refine_pilot_dry_run_module(pilot_run_dir: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "false")
    sys.path.insert(0, str(REPO_ROOT / "src"))
    from translation.refine_runner import run_refine_pilot

    repo = pilot_run_dir.parent.parent.parent
    summary, _ = run_refine_pilot(
        repo_root=repo,
        run_id=pilot_run_dir.name,
        limit_segments=10,
        force_dry_run=True,
    )
    assert summary.refined_segments == 2
    doc = json.loads((pilot_run_dir / "segments.json").read_text(encoding="utf-8"))
    refined = [
        s
        for ch in doc["chapters"]
        for s in ch["segments"]
        if (s.get("refined_text") or "").strip()
    ]
    assert len(refined) == 2
    assert (pilot_run_dir / "refine_diff.json").is_file()


def test_refine_stage_c_cli_dry_run(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "false")
    run_id = "run_20260602_203645_draft_stage_b_50ch"
    proc = subprocess.run(
        [
            sys.executable,
            str(SCRIPT),
            "--run-id",
            run_id,
            "--limit-segments",
            "3",
            "--dry-run",
        ],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=180,
        env={**dict(**__import__("os").environ), "REAL_API_TESTS_ENABLED": "false"},
    )
    if not (REPO_ROOT / "workspace/runs" / run_id / "segments.json").is_file():
        pytest.skip("Stage B run not present locally")
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "refined=" in proc.stdout or "refined_segments" in proc.stdout
