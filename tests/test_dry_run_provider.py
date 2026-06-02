"""Tests for dry-run provider (records request, no network)."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from providers.dry_run_provider import DryRunProvider
from providers.types import GenerateOptions, Message


@pytest.fixture
def messages():
    return [
        Message(role="system", content="You are a translator."),
        Message(role="user", content="短いテスト文です。"),
    ]


def test_dry_run_records_request_without_network(messages):
    provider = DryRunProvider()
    with patch("urllib.request.urlopen") as mock_urlopen:
        result = provider.generate(messages, GenerateOptions(pipeline_stage="translation"))
        mock_urlopen.assert_not_called()

    assert len(provider.records) == 1
    rec = provider.records[0]
    assert rec.estimated_tokens > 0
    assert rec.request_hash
    assert result.dry_run is True
    assert result.status == "dry_run"
    assert result.finish_reason == "dry_run"
    assert provider.network_calls == 0


def test_dry_run_multiple_calls_accumulate_records(messages):
    provider = DryRunProvider()
    provider.generate(messages)
    provider.generate([Message(role="user", content="second call")])
    assert len(provider.records) == 2


def test_dry_run_parsed_output_has_summary(messages):
    provider = DryRunProvider()
    result = provider.generate(messages)
    assert result.parsed_output is not None
    assert result.parsed_output["dry_run"] is True
    assert "cost_estimate_usd" in result.parsed_output
