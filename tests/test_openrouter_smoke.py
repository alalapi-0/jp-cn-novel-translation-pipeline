"""Tests for OpenRouter smoke script (dry-run only — no network)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "run_openrouter_smoke.py"


def test_openrouter_smoke_dry_run_cli(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "false")
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), "--dry-run", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr or proc.stdout
    assert "dry_run" in proc.stdout.lower() or "DRY" in proc.stdout


def _load_smoke_module():
    import importlib.util

    spec = importlib.util.spec_from_file_location("run_openrouter_smoke", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_openrouter_smoke_module_force_dry_run(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "true")
    smoke = _load_smoke_module()
    summary = smoke.run_smoke(max_cost_usd=0.05, force_dry_run=True)
    assert summary["mode"] == "dry_run"


def test_smoke_report_written_under_workspace(monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "false")
    smoke = _load_smoke_module()
    summary = smoke.run_smoke(max_cost_usd=0.01, force_dry_run=True)
    assert summary["mode"] == "dry_run"
    reports = list(smoke.SMOKE_DIR.glob("openrouter_smoke_*.json"))
    assert reports
    payload = json.loads(reports[-1].read_text(encoding="utf-8"))
    assert "openrouter_key_present" in payload
