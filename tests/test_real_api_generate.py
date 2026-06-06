"""Tests for real API sample generation guardrails."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from workbench.real_api_generate import generate_segments_real_api, real_api_available  # noqa: E402


def test_real_api_unavailable_without_key(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "false")
    assert real_api_available() is False
    with pytest.raises(ValueError, match="real_api_unavailable"):
        generate_segments_real_api(
            sample_text="テスト",
            language_direction="JP_TO_CN",
            repo_root=tmp_path,
        )


def test_real_api_unavailable_when_budget_zero(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "true")
    monkeypatch.setenv("MAX_TEST_COST_USD", "0")
    assert real_api_available() is False
    with pytest.raises(ValueError, match="max_test_cost_usd_zero"):
        generate_segments_real_api(
            sample_text="テスト",
            language_direction="JP_TO_CN",
            repo_root=tmp_path,
        )
