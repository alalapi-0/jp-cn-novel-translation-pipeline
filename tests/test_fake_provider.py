"""Tests for fake provider (fixed output, no network)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from providers.cost_guard import CostGuard, CostGuardConfig
from providers.fake_provider import FakeProvider
from providers.types import GenerateOptions, Message


@pytest.fixture
def messages():
    return [Message(role="user", content="Translate this short segment.")]


def test_fake_provider_returns_fixed_json(messages):
    provider = FakeProvider()
    result = provider.generate(messages, GenerateOptions(project_id="p1"))
    assert result.provider_id == "fake_provider"
    assert result.status == "ok"
    assert result.network_calls == 0 if hasattr(result, "network_calls") else provider.network_calls == 0
    parsed = json.loads(result.raw_output)
    assert parsed["translation"].startswith("[fake]")
    assert result.parsed_output is not None
    assert result.estimated_tokens > 0


def test_fake_provider_no_network(monkeypatch, messages):
    def _fail(*_a, **_k):
        raise AssertionError("network must not be called")

    monkeypatch.setattr("urllib.request.urlopen", _fail, raising=False)
    provider = FakeProvider()
    provider.generate(messages)
    assert provider.network_calls == 0


def test_fake_provider_respects_cost_guard(messages, tmp_path):
    guard = CostGuard(
        CostGuardConfig(max_test_cost_usd=1.0, max_tokens_per_run=10_000, log_dir=tmp_path)
    )
    provider = FakeProvider(cost_guard=guard)
    result = provider.generate(messages)
    assert guard.call_count == 1
    assert result.cost_estimate_usd >= 0
