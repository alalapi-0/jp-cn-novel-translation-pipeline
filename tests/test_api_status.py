"""Tests for runtime API status probe."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from workbench.api_status import build_api_status, resolve_api_mode  # noqa: E402


def test_resolve_api_mode_missing_key(monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert resolve_api_mode() == "missing_api_key"


def test_resolve_api_mode_dry_run_with_key(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "false")
    assert resolve_api_mode() == "dry_run"


def test_build_api_status_shape(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    status = build_api_status(tmp_path)
    assert status["api_mode"] == "missing_api_key"
    assert status["has_api_key"] is False
    assert "config_hint" in status
