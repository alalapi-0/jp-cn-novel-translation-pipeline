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


def test_draft_resume_hydrates_segments_json(tmp_path, monkeypatch):
    """Resume must load draft_text from segments.json and skip already-translated batches."""
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
    run_id = "test-resume-hydrate"
    run_root = tmp_path / "workspace" / "runs" / run_id
    run_root.mkdir(parents=True)
    segments_doc = {
        "chapters": [
            {
                "chapter_id": "ch-001",
                "segments": [
                    {
                        "segment_id": "ch-001-seg-001",
                        "draft_text": "已有译文一。",
                        "status": "machine_translated",
                    },
                    {"segment_id": "ch-001-seg-002", "draft_text": "", "status": "pending"},
                ],
            }
        ]
    }
    (run_root / "segments.json").write_text(
        json.dumps(segments_doc, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    cp_dir = tmp_path / "workspace" / "checkpoints"
    cp_dir.mkdir(parents=True)
    (cp_dir / f"{run_id}.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "completed_segments": ["ch-001-seg-001"],
                "spent_usd": 0.0,
                "spent_tokens": 0,
                "status": "in_progress",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "metadata": {},
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )

    class StubProvider:
        provider_id = "stub"
        model_name = "stub-model"
        network_calls = 0

        def __init__(self, cost_guard=None):
            self.cost_guard = cost_guard

        def generate(self, messages, options=None):
            from providers.types import ModelResult

            self.network_calls += 1
            fixed = {
                "items": [{"segment_id": "ch-001-seg-002", "translation": "段落二。"}]
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

    provider_holder: dict[str, StubProvider] = {}

    def factory(guard):
        provider_holder["p"] = StubProvider(cost_guard=guard)
        return provider_holder["p"]

    summary, _ = run_draft_stage_a(
        repo_root=tmp_path,
        input_dir=input_dir,
        limit_chapters=1,
        run_id=run_id,
        provider_factory=factory,
    )
    assert provider_holder["p"].network_calls == 1
    assert summary.translated_segments == 2
    report = json.loads((run_root / "draft_quality_report.json").read_text(encoding="utf-8"))
    assert report["passed"] is True


def test_draft_resume_retranslates_when_checkpoint_done_but_no_draft(tmp_path, monkeypatch):
    """Checkpoint may list a segment done while segments.json lost draft_text; must re-translate."""
    monkeypatch.setenv("CONTROLLED_RUN_ENABLED", "true")
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "false")
    input_dir = tmp_path / "input_jp"
    input_dir.mkdir()
    (input_dir / "001-test.md").write_text(
        "# 测试\n\n## 节\n\n段落一です。\n",
        encoding="utf-8",
    )
    run_id = "test-resume-missing-draft"
    run_root = tmp_path / "workspace" / "runs" / run_id
    run_root.mkdir(parents=True)
    (run_root / "segments.json").write_text(
        json.dumps(
            {
                "chapters": [
                    {
                        "chapter_id": "ch-001",
                        "segments": [{"segment_id": "ch-001-seg-001", "draft_text": "", "status": "pending"}],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    cp_dir = tmp_path / "workspace" / "checkpoints"
    cp_dir.mkdir(parents=True)
    (cp_dir / f"{run_id}.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "completed_segments": ["ch-001-seg-001"],
                "spent_usd": 0.0,
                "spent_tokens": 0,
                "status": "completed",
                "updated_at": "2026-01-01T00:00:00+00:00",
                "metadata": {},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    class StubProvider:
        provider_id = "stub"
        model_name = "stub-model"
        network_calls = 0

        def __init__(self, cost_guard=None):
            self.cost_guard = cost_guard

        def generate(self, messages, options=None):
            from providers.types import ModelResult

            self.network_calls += 1
            fixed = {"items": [{"segment_id": "ch-001-seg-001", "translation": "段落一。"}]}
            raw = json.dumps(fixed, ensure_ascii=False)
            result = ModelResult(
                provider_id=self.provider_id,
                model_name=self.model_name,
                raw_output=raw,
                parsed_output=fixed,
            )
            result.mark_finished("ok")
            return result

    provider_holder: dict[str, StubProvider] = {}

    def factory(guard):
        provider_holder["p"] = StubProvider(cost_guard=guard)
        return provider_holder["p"]

    summary, _ = run_draft_stage_a(
        repo_root=tmp_path,
        input_dir=input_dir,
        limit_chapters=1,
        run_id=run_id,
        provider_factory=factory,
    )
    assert provider_holder["p"].network_calls == 1
    assert summary.translated_segments == 1
    cp = json.loads((cp_dir / f"{run_id}.json").read_text(encoding="utf-8"))
    assert cp["status"] == "completed"
