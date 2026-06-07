"""Tests for API status cost guard readiness."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from workbench.api_status import build_api_status, resolve_api_mode, workbench_real_api_ready  # noqa: E402
from workbench.local_env import reset_local_env_cache  # noqa: E402


def test_resolve_api_mode_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    assert resolve_api_mode() == "missing_api_key"


def test_resolve_api_mode_dry_run(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "false")
    assert resolve_api_mode() == "dry_run"


def test_workbench_real_api_fix_command_when_budget_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "true")
    monkeypatch.setenv("MAX_TEST_COST_USD", "0")
    status = build_api_status(tmp_path)
    assert status["workbench_real_api_fix_command"]
    assert "MAX_TEST_COST_USD=0.01" in status["workbench_real_api_fix_command"]
    assert status["workbench_real_api_block_reason_label"]


def test_workbench_real_api_blocked_when_budget_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "true")
    monkeypatch.setenv("MAX_TEST_COST_USD", "0")
    ready, reason = workbench_real_api_ready()
    assert ready is False
    assert reason == "max_test_cost_usd_zero"
    status = build_api_status(tmp_path)
    assert status["workbench_real_api_ready"] is False
    assert status["max_test_cost_usd"] == 0.0


def test_api_status_separates_runner_note(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    runtime = tmp_path / ".agent_runtime"
    runtime.mkdir(parents=True)
    (runtime / "status.json").write_text('{"api_mode": "real_api"}', encoding="utf-8")
    status = build_api_status(tmp_path)
    assert status["api_mode"] == "missing_api_key"
    assert status["runner_status_note"] is not None


def test_build_api_status_loads_dotenv_for_probe(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    reset_local_env_cache()
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    (tmp_path / ".env").write_text("OPENROUTER_API_KEY=dotenv-key\nREAL_API_TESTS_ENABLED=true\n", encoding="utf-8")
    status = build_api_status(tmp_path)
    assert status["has_api_key"] is True
    assert "openrouter" in status["detected_providers"]
    assert "OPENROUTER_API_KEY" in status["env_keys_applied_from_dotenv"]


def test_api_status_pipeline_and_smoke_ignorable(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "true")
    monkeypatch.setenv("MAX_TEST_COST_USD", "2.0")
    runtime = tmp_path / ".agent_runtime" / "real_api_reports"
    runtime.mkdir(parents=True)
    (runtime / "real_api_smoke_old.json").write_text(
        '{"mode":"real","success":false,"created_at":"2020-01-01T00:00:00Z","error_summary":"old failure"}',
        encoding="utf-8",
    )
    workspace = tmp_path / "workspace"
    workspace.mkdir(parents=True)
    (workspace / "stage_state_production.json").write_text(
        '{"run_id":"run_prod_test","status":"in_progress"}',
        encoding="utf-8",
    )
    status = build_api_status(tmp_path)
    assert status.get("workbench_mode") == "production"
    assert status.get("pipeline_status", {}).get("run_id") == "run_prod_test"
    assert status["last_smoke"]["ignorable"] is True
    assert status["last_smoke"]["ignorable_note"]
