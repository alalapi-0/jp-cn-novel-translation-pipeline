"""Tests for scripts/run_real_api_smoke.py content validation."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "run_real_api_smoke.py"
sys.path.insert(0, str(REPO_ROOT / "src"))


def _load_module():
    name = "run_real_api_smoke_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture()
def smoke_mod():
    return _load_module()


def _patch_openrouter_provider(monkeypatch: pytest.MonkeyPatch, *, output: str) -> None:
    import providers.openrouter_provider as op
    from providers.types import ModelResult

    class StubProvider:
        provider_id = "openrouter"

        def __init__(self, **kwargs):
            self.kwargs = kwargs

        def generate(self, messages, options=None):  # noqa: ARG002
            result = ModelResult(
                provider_id="openrouter",
                model_name="stub-openrouter",
                raw_output=output,
                usage={"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                cost_estimate_usd=0.0001,
                latency_ms=10,
            )
            result.mark_finished("ok")
            return result

    monkeypatch.setattr(op, "OpenRouterProvider", StubProvider)


def test_real_smoke_empty_content_not_success(
    smoke_mod,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_openrouter_provider(monkeypatch, output="   ")
    report = smoke_mod.base_report(mode="real_api", detected=["openrouter"], created_at=smoke_mod.iso_now())
    report = smoke_mod.run_openrouter_real(report, max_cost_usd=0.01, max_tokens=32, timeout_sec=1)
    assert report["transport_success"] is True
    assert report["content_success"] is False
    assert report["success"] is False
    assert report["error_summary"] == "empty_content"


def test_real_smoke_requires_smoke_token(
    smoke_mod,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_openrouter_provider(monkeypatch, output="smoke_ok")
    report = smoke_mod.base_report(mode="real_api", detected=["openrouter"], created_at=smoke_mod.iso_now())
    report = smoke_mod.run_openrouter_real(report, max_cost_usd=0.01, max_tokens=32, timeout_sec=1)
    assert report["transport_success"] is True
    assert report["content_success"] is True
    assert report["success"] is True
    assert report["error_summary"] is None
