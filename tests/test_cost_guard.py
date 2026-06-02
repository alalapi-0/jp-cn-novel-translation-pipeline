"""Tests for cost guard: budget ceiling, abort, logging."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from providers.cost_guard import CostGuard, CostGuardConfig, CostGuardError
from providers.dry_run_provider import DryRunProvider
from providers.fake_provider import FakeProvider
from providers.registry import ProviderMode, get_provider
from providers.types import Message


def _long_messages(count: int = 50) -> list[Message]:
    return [Message(role="user", content="x" * 500) for _ in range(count)]


def test_default_guard_blocks_real_api():
    guard = CostGuard(CostGuardConfig.from_env())
    assert guard.allow_real_network() is False
    with pytest.raises(RuntimeError, match="REAL_API_TESTS_ENABLED"):
        get_provider(ProviderMode.REAL, cost_guard=guard)


def test_budget_exceeded_aborts_and_writes_log(tmp_path):
    log_dir = tmp_path / "model_runs"
    guard = CostGuard(
        CostGuardConfig(max_test_cost_usd=0.0, max_tokens_per_run=100, log_dir=log_dir)
    )
    provider = DryRunProvider(cost_guard=guard)
    messages = _long_messages(20)

    with pytest.raises(CostGuardError) as exc_info:
        provider.generate(messages)

    assert guard.aborted is True
    assert exc_info.value.report["reason"] == "max_tokens_per_run_exceeded"
    logs = list(log_dir.glob("cost_guard_abort_*.json"))
    assert len(logs) == 1
    payload = json.loads(logs[0].read_text(encoding="utf-8"))
    assert payload["reason"] == "max_tokens_per_run_exceeded"


def test_cost_ceiling_aborts(tmp_path):
    log_dir = tmp_path / "model_runs"
    guard = CostGuard(
        CostGuardConfig(
            max_test_cost_usd=0.000001,
            max_tokens_per_run=0,
            cost_per_million_tokens=10.0,
            log_dir=log_dir,
        )
    )
    provider = FakeProvider(cost_guard=guard)
    messages = [Message(role="user", content="a" * 2000)]

    with pytest.raises(CostGuardError) as exc_info:
        provider.generate(messages)

    assert exc_info.value.report["reason"] == "max_test_cost_usd_exceeded"
    assert guard.aborted


def test_subsequent_call_fails_after_abort(tmp_path):
    guard = CostGuard(
        CostGuardConfig(max_test_cost_usd=0.0, max_tokens_per_run=10, log_dir=tmp_path)
    )
    provider = FakeProvider(cost_guard=guard)
    msgs = _long_messages(5)
    with pytest.raises(CostGuardError):
        provider.generate(msgs)
    with pytest.raises(CostGuardError, match="already aborted"):
        provider.generate([Message(role="user", content="retry")])


def test_real_api_enabled_when_env_set(monkeypatch):
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    guard = CostGuard(CostGuardConfig.from_env())
    assert guard.allow_real_network() is True
    provider = get_provider(ProviderMode.REAL, cost_guard=guard)
    assert provider.provider_id == "openrouter"
