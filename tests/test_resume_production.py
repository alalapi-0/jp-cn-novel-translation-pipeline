"""Tests for scripts/resume_production.py compatibility wrapper."""

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

    def fake_run(cmd, *, check=True, capture=False, with_production_env=False):
        assert capture is True
        assert "throughput_gate.py" in " ".join(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout=json.dumps(gate_doc), stderr="")

    monkeypatch.setattr(resume, "_run", fake_run)
    assert resume._run_gate_json("python3") == gate_doc


def test_run_gate_json_raises_on_empty_stdout(monkeypatch: pytest.MonkeyPatch) -> None:
    resume = _load_resume()

    def fake_run(cmd, *, check=True, capture=False, with_production_env=False):
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


def test_refine_dry_run_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    resume = _load_resume()
    calls: list[list[str]] = []

    def fake_run(cmd, *, check=True, capture=False, with_production_env=False):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="refined=1\n", stderr="")

    monkeypatch.setattr(resume, "_run", fake_run)
    monkeypatch.delenv("ALLOW_LEGACY_REFINEMENT", raising=False)
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
    assert resume.main() == 2
    assert calls == []


def test_resume_delegates_to_scheduler_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    resume = _load_resume()
    calls: list[list[str]] = []

    def fake_run(cmd, *, check=True, capture=False, with_production_env=False):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="{}", stderr="")

    monkeypatch.setattr(resume, "_run", fake_run)
    monkeypatch.setattr(resume, "apply_local_env", lambda repo: [])
    monkeypatch.setattr(
        resume.sys,
        "argv",
        ["resume_production.py", "--run-id", "run_old", "--hydrate-apply", "--skip-gate"],
    )
    assert resume.main() == 0
    assert len(calls) == 1
    cmd = calls[0]
    assert cmd[1].endswith("local_scheduler_tick.py")
    assert "--dry-run" in cmd
    assert "translate.py" not in " ".join(cmd)


def test_resume_real_api_requires_budget(monkeypatch: pytest.MonkeyPatch) -> None:
    resume = _load_resume()
    monkeypatch.setattr(resume.sys, "argv", ["resume_production.py", "--real-api"])
    assert resume.main() == 2


def test_scheduler_tick_command_for_real_api() -> None:
    resume = _load_resume()
    args = type(
        "Args",
        (),
        {
            "real_api": True,
            "max_api_calls": 5,
            "max_segments": 20,
            "max_wall_time_minutes": None,
            "batch_token_budget": None,
            "max_segments_per_call": None,
        },
    )()
    cmd = resume._scheduler_tick_command("python3", args)
    assert cmd == [
        "python3",
        "scripts/local_scheduler_tick.py",
        "--json",
        "--real-api",
        "--max-api-calls",
        "5",
        "--max-segments",
        "20",
    ]


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
