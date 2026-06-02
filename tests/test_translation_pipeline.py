"""Tests for draft translation pipeline (no real API)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from providers.cost_guard import CostGuard, CostGuardConfig
from providers.registry import ProviderMode, get_provider
from translation.chapter_parser import parse_chapter_file
from translation.draft_runner import run_draft_stage_a, run_draft_stage_b
from translation.response_extractor import extract_translations
from translation.validator import validate_draft_items


def test_extract_json_items():
    raw = json.dumps(
        {
            "items": [
                {"segment_id": "ch-001-seg-001", "translation": "你好"},
                {"segment_id": "ch-001-seg-002", "translation": "世界"},
            ]
        },
        ensure_ascii=False,
    )
    result = extract_translations(raw, ["ch-001-seg-001", "ch-001-seg-002"])
    assert result.parse_status == "ok"
    assert len(result.items) == 2


def test_registry_real_returns_openrouter(monkeypatch):
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "true")
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")
    guard = CostGuard(CostGuardConfig.from_env())
    provider = get_provider(ProviderMode.REAL, cost_guard=guard)
    assert provider.provider_id == "openrouter"


def test_run_draft_stage_a_fake(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROLLED_RUN_ENABLED", "true")
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "false")
    input_dir = tmp_path / "input_jp"
    input_dir.mkdir()
    sample = """# 测试章

## 第一节

段落一です。

段落二です。
"""
    (input_dir / "001-test.md").write_text(sample, encoding="utf-8")

    fixed = {
        "items": [
            {"segment_id": "ch-001-seg-001", "translation": "段落一。"},
            {"segment_id": "ch-001-seg-002", "translation": "段落二。"},
        ]
    }

    class StubProvider:
        provider_id = "stub"
        model_name = "stub-model"
        network_calls = 0

        def __init__(self, cost_guard=None):
            self.cost_guard = cost_guard

        def generate(self, messages, options=None):
            from providers.types import ModelResult

            self.network_calls += 1
            raw = json.dumps(fixed, ensure_ascii=False)
            result = ModelResult(
                provider_id=self.provider_id,
                model_name=self.model_name,
                raw_output=raw,
                parsed_output=fixed,
            )
            result.mark_finished("ok")
            if self.cost_guard:
                self.cost_guard.record_call(10, 0.0001)
            return result

    summary, run_root = run_draft_stage_a(
        repo_root=tmp_path,
        input_dir=input_dir,
        limit_chapters=1,
        run_id="test-run",
        provider_factory=lambda g: StubProvider(cost_guard=g),
    )
    assert summary.translated_segments == 2
    assert (run_root / "draft_quality_report.json").is_file()
    report = json.loads((run_root / "draft_quality_report.json").read_text(encoding="utf-8"))
    assert report["passed"] is True


def test_run_draft_stage_b_fake(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROLLED_RUN_ENABLED", "true")
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "false")
    input_dir = tmp_path / "input_jp"
    input_dir.mkdir()
    for n in (1, 2):
        sample = f"""# 测试章{n}

## 节

段落一です。

段落二です。
"""
        (input_dir / f"{n:03d}-test.md").write_text(sample, encoding="utf-8")

    call_count = {"n": 0}

    class StubProvider:
        provider_id = "stub"
        model_name = "stub-model"
        network_calls = 0

        def __init__(self, cost_guard=None):
            self.cost_guard = cost_guard

        def generate(self, messages, options=None):
            from providers.types import ModelResult

            self.network_calls += 1
            call_count["n"] += 1
            ch = "001" if call_count["n"] <= 1 else "002"
            fixed = {
                "items": [
                    {"segment_id": f"ch-{ch}-seg-001", "translation": "段落一。"},
                    {"segment_id": f"ch-{ch}-seg-002", "translation": "段落二。"},
                ]
            }
            raw = json.dumps(fixed, ensure_ascii=False)
            result = ModelResult(
                provider_id=self.provider_id,
                model_name=self.model_name,
                raw_output=raw,
                parsed_output=fixed,
            )
            result.mark_finished("ok")
            if self.cost_guard:
                self.cost_guard.record_call(10, 0.0001)
            return result

    summary, run_root = run_draft_stage_b(
        repo_root=tmp_path,
        input_dir=input_dir,
        limit_chapters=2,
        run_id="test-run-b",
        provider_factory=lambda g: StubProvider(cost_guard=g),
    )
    assert summary.translated_segments == 4
    assert (run_root / "draft_quality_report.json").is_file()
    assert (run_root / "stage_draft_b_50ch_go_decision.md").is_file()
    report = json.loads((run_root / "draft_quality_report.json").read_text(encoding="utf-8"))
    assert report["passed"] is True
    assert report["stage_c_eligible"] is True


def test_parse_e2e_sample():
    path = REPO_ROOT / "data" / "examples" / "e2e_trial_chapter.md"
    if not path.is_file():
        pytest.skip("e2e sample missing")
    ch = parse_chapter_file(path)
    assert len(ch.segments) >= 1
