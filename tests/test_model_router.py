"""Tests for the unified model router."""

from __future__ import annotations

import json
import sys
from http.client import IncompleteRead
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "model-router" / "src"))

from model_router import ChatOptions, chat, reset_router  # noqa: E402
from model_router.errors import ParameterError, RateLimitError  # noqa: E402
from model_router.modelRouter import ModelRouter  # noqa: E402
from model_router.config_loader import load_router_config  # noqa: E402


@pytest.fixture(autouse=True)
def _reset_router_cache():
    reset_router()
    yield
    reset_router()


def test_chat_openai_compatible_success(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    config = load_router_config(REPO_ROOT / "model-router" / "config" / "models.yaml")
    router = ModelRouter(config)

    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = json.dumps(
        {
            "model": "deepseek/deepseek-v4-pro",
            "choices": [{"message": {"content": "hello"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
        }
    ).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = router.chat(
            [{"role": "user", "content": "hi"}],
            ChatOptions(profile="coding", provider="openrouter", model="deepseek/deepseek-v4-pro"),
        )

    assert result.content == "hello"
    assert result.provider == "openrouter"
    assert result.usage.total_tokens == 5
    assert "choices" in result.raw


def test_parameter_error_does_not_fallback(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    config = load_router_config(REPO_ROOT / "model-router" / "config" / "models.yaml")
    router = ModelRouter(config)

    err = ParameterError("bad request body", "openrouter", 400)

    with patch.object(router, "_get_provider") as get_provider:
        provider = MagicMock()
        provider.chat.side_effect = err
        get_provider.return_value = provider

        with pytest.raises(RuntimeError, match="bad request body"):
            router.chat([{"role": "user", "content": "x"}], ChatOptions(profile="coding"))

    assert provider.chat.call_count == 1


def test_fallback_on_rate_limit(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "ds-key")
    config = load_router_config(REPO_ROOT / "model-router" / "config" / "models.yaml")
    router = ModelRouter(config)

    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = json.dumps(
        {
            "choices": [{"message": {"content": "fallback_ok"}}],
            "usage": {"total_tokens": 4},
        }
    ).encode("utf-8")

    call_count = {"n": 0}

    def fake_urlopen(req, timeout=60):
        call_count["n"] += 1
        if call_count["n"] == 1:
            import urllib.error

            raise urllib.error.HTTPError(req.full_url, 429, "rate limit", hdrs=None, fp=None)
        return mock_resp

    with patch("urllib.request.urlopen", side_effect=fake_urlopen):
        result = router.chat(
            [{"role": "user", "content": "hi"}],
            ChatOptions(profile="coding"),
        )

    assert result.content == "fallback_ok"
    assert call_count["n"] >= 2


def test_openai_compatible_network_error(monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    config = load_router_config(REPO_ROOT / "model-router" / "config" / "models.yaml")
    router = ModelRouter(config)

    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.side_effect = IncompleteRead(b"partial", 8000)

    with patch("urllib.request.urlopen", return_value=mock_resp):
        with pytest.raises(RuntimeError, match="exhausted fallback chain"):
            router.chat(
                [{"role": "user", "content": "hello"}],
                ChatOptions(profile="coding", provider="openrouter"),
            )


def test_module_level_chat_helper(monkeypatch, tmp_path):
    monkeypatch.setenv("MODEL_ROUTER_CONFIG_PATH", str(REPO_ROOT / "model-router" / "config" / "models.yaml"))
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")

    mock_resp = MagicMock()
    mock_resp.__enter__ = MagicMock(return_value=mock_resp)
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.read.return_value = json.dumps(
        {"choices": [{"message": {"content": "ok"}}], "usage": {"total_tokens": 1}}
    ).encode("utf-8")

    with patch("urllib.request.urlopen", return_value=mock_resp):
        result = chat([{"role": "user", "content": "ping"}], profile="fast")

    assert result.content == "ok"
