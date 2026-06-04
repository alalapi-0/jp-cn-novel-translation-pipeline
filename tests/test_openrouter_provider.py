"""Tests for OpenRouter provider error handling (no real API)."""

from __future__ import annotations

import json
import sys
from http.client import IncompleteRead
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from providers.cost_guard import CostGuard, CostGuardConfig
from providers.openrouter_provider import OpenRouterProvider
from providers.types import GenerateOptions, Message


def test_openrouter_incomplete_read_becomes_runtime_error(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    guard = CostGuard(
        CostGuardConfig(max_test_cost_usd=10.0, max_tokens_per_run=0, real_api_tests_enabled=True)
    )
    provider = OpenRouterProvider(cost_guard=guard)
    messages = [Message(role="user", content="hello")]

    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.side_effect = IncompleteRead(b"partial", 8000)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="OpenRouter network error"):
            provider.generate(messages, GenerateOptions())


def test_openrouter_provider_sends_optional_smoke_limits(monkeypatch, tmp_path):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    guard = CostGuard(
        CostGuardConfig(
            max_test_cost_usd=10.0,
            max_tokens_per_run=100,
            real_api_tests_enabled=True,
            log_dir=tmp_path,
        )
    )
    provider = OpenRouterProvider(
        cost_guard=guard,
        max_tokens=8,
        temperature=0.0,
        timeout_sec=5,
    )
    messages = [Message(role="user", content="hello")]

    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = json.dumps(
        {
            "choices": [{"message": {"content": "smoke_ok"}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "total_tokens": 3},
        }
    ).encode("utf-8")

    def fake_urlopen(req, timeout):
        payload = json.loads(req.data.decode("utf-8"))
        assert payload["max_tokens"] == 8
        assert payload["temperature"] == 0.0
        assert timeout == 5
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = provider.generate(messages, GenerateOptions())

    assert result.raw_output == "smoke_ok"
