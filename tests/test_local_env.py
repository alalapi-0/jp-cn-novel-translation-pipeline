"""Tests for local .env loading helper."""

from __future__ import annotations

import os
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from local_env import apply_local_env  # noqa: E402


def test_apply_local_env_sets_unset_keys(tmp_path: Path, monkeypatch) -> None:
    import local_env as le

    le._APPLIED_KEYS = None
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text('OPENROUTER_API_KEY="from-dotenv"\nREAL_API_TESTS_ENABLED=true\n', encoding="utf-8")
    applied = apply_local_env(tmp_path)
    assert "OPENROUTER_API_KEY" in applied
    assert "REAL_API_TESTS_ENABLED" in applied
    assert os.environ["OPENROUTER_API_KEY"] == "from-dotenv"


def test_apply_local_env_does_not_override_existing(tmp_path: Path, monkeypatch) -> None:
    import local_env as le

    le._APPLIED_KEYS = None
    monkeypatch.setenv("OPENROUTER_API_KEY", "already-set")
    env_file = tmp_path / ".env"
    env_file.write_text("OPENROUTER_API_KEY=from-dotenv\n", encoding="utf-8")
    applied = apply_local_env(tmp_path)
    assert applied == []
    assert os.environ["OPENROUTER_API_KEY"] == "already-set"
