"""Tests for scripts/resume_production.py gate capture and env."""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "resume_production.py"


def _load_resume():
    spec = importlib.util.spec_from_file_location("resume_production_test", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_run_gate_json_parses_captured_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    resume = _load_resume()
    gate_doc = {"decision": "ALLOW", "fix_paths": []}

    def fake_run(cmd, *, check=True, capture=False):
        assert capture is True
        assert "throughput_gate.py" in " ".join(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(gate_doc), stderr="")

    monkeypatch.setattr(resume, "_run", fake_run)
    assert resume._run_gate_json("python3") == gate_doc


def test_run_gate_json_raises_on_empty_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    resume = _load_resume()

    def fake_run(cmd, *, check=True, capture=False):
        return subprocess.CompletedProcess(cmd, 2, stdout=None, stderr="gate failed")

    monkeypatch.setattr(resume, "_run", fake_run)
    with pytest.raises(json.JSONDecodeError):
        resume._run_gate_json("python3")


def test_ensure_production_env_sets_controlled_run(monkeypatch: pytest.MonkeyPatch) -> None:
    resume = _load_resume()
    monkeypatch.delenv("CONTROLLED_RUN_ENABLED", raising=False)
    monkeypatch.delenv("REAL_API_TESTS_ENABLED", raising=False)
    resume._ensure_production_env()
    assert resume.os.environ.get("CONTROLLED_RUN_ENABLED") == "1"
    assert resume.os.environ.get("REAL_API_TESTS_ENABLED") == "1"


def test_refine_dry_run_skips_translate_exit(monkeypatch: pytest.MonkeyPatch) -> None:
    resume = _load_resume()
    calls: list[list[str]] = []

    def fake_run(cmd, *, check=True, capture=False):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="refined=1\n", stderr="")

    monkeypatch.setattr(resume, "_run", fake_run)
    monkeypatch.setattr(
        resume.sys,
        "argv",
        [
            "resume_production.py",
            "--refine",
            "--dry-run",
            "--no-hydrate",
            "--skip-gate",
        ],
    )
    assert resume.main() == 0
    assert len(calls) == 1
    assert "refine_stage_c.py" in " ".join(calls[0])
    assert "--dry-run" in calls[0]


def test_cli_dry_run_help() -> None:
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--help"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    assert proc.returncode == 0
    assert "resume_production" in proc.stdout or "续跑" in proc.stdout
