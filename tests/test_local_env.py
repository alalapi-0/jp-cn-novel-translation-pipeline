"""Tests for local .env loading helper."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from workbench.local_env import apply_local_env, reset_local_env_cache  # noqa: E402


def test_apply_local_env_sets_unset_keys(tmp_path: Path, monkeypatch) -> None:
    reset_local_env_cache()
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("REAL_API_TESTS_ENABLED", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text('OPENROUTER_API_KEY="from-dotenv"\nREAL_API_TESTS_ENABLED=true\n', encoding="utf-8")
    applied = apply_local_env(tmp_path)
    assert "OPENROUTER_API_KEY" in applied
    assert "REAL_API_TESTS_ENABLED" in applied
    assert os.environ["OPENROUTER_API_KEY"] == "from-dotenv"


def test_apply_local_env_does_not_override_existing(tmp_path: Path, monkeypatch) -> None:
    reset_local_env_cache()
    monkeypatch.setenv("OPENROUTER_API_KEY", "already-set")
    env_file = tmp_path / ".env"
    env_file.write_text("OPENROUTER_API_KEY=from-dotenv\n", encoding="utf-8")
    applied = apply_local_env(tmp_path)
    assert applied == []
    assert os.environ["OPENROUTER_API_KEY"] == "already-set"


def test_apply_local_env_fills_blank_shell_value(tmp_path: Path, monkeypatch) -> None:
    reset_local_env_cache()
    monkeypatch.setenv("OPENROUTER_API_KEY", "   ")
    env_file = tmp_path / ".env"
    env_file.write_text("OPENROUTER_API_KEY=from-dotenv\n", encoding="utf-8")
    applied = apply_local_env(tmp_path)
    assert "OPENROUTER_API_KEY" in applied
    assert os.environ["OPENROUTER_API_KEY"] == "from-dotenv"


def test_apply_local_env_skips_empty_dotenv_values(tmp_path: Path, monkeypatch) -> None:
    reset_local_env_cache()
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("REAL_API_TESTS_ENABLED", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text("OPENROUTER_API_KEY=\nREAL_API_TESTS_ENABLED=true\n", encoding="utf-8")
    applied = apply_local_env(tmp_path)
    assert "OPENROUTER_API_KEY" not in applied
    assert "REAL_API_TESTS_ENABLED" in applied
    assert "OPENROUTER_API_KEY" not in os.environ
