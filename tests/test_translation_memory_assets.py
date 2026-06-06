"""Tests for translation-memory asset deposition and consumption."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from assets.translation_memory import (  # noqa: E402
    ExternalAssetExtractionUnavailable,
    build_translation_memory_assets,
    render_translation_asset_context,
)
from translation.draft_runner import run_draft_stage_a  # noqa: E402
from translation.prompt_builder import build_batch_messages  # noqa: E402
from translation.chapter_parser import Segment  # noqa: E402
from workbench.project_registry import create_project_manifest  # noqa: E402
from workbench.review_state import patch_project_review_state  # noqa: E402


def _seed_workbench_project(repo: Path) -> str:
    project_id = "asset-memory-test"
    create_project_manifest(
        repo,
        project_id=project_id,
        name="Asset Memory",
        language_direction="JP_TO_CN",
        segments=[
            {
                "id": "seg-001",
                "segment_id": "seg-001",
                "chapter": 1,
                "source": "アルファの森へ向かう。",
                "draft": "前往阿尔法之森。",
                "status": "pending",
            },
            {
                "id": "seg-002",
                "segment_id": "seg-002",
                "chapter": 1,
                "source": "【レア】称号を獲得した。",
                "draft": "【稀有】获得了称号。",
                "status": "pending",
            },
        ],
    )
    patch_project_review_state(
        repo,
        project_id,
        segments={
            "seg-001": {"status": "approved"},
            "seg-002": {"status": "rejected"},
        },
    )
    return project_id


def test_agent_mode_builds_approved_translation_memory_without_api(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-be-used")
    project_id = _seed_workbench_project(tmp_path)

    doc = build_translation_memory_assets(repo_root=tmp_path, project_id=project_id)

    assert doc["mode"] == "agent"
    assert doc["stats"]["api_calls"] == 0
    assert doc["stats"]["pairs"] == 1
    assert doc["approved_pairs"][0]["segment_id"] == "seg-001"
    assert "seg-002" not in doc["segment_map"]
    assert Path(doc["asset_path"]).is_file()
    assert "アルファ" in doc["context_prompt"]


def test_run_source_translated_mode_can_deposit_completed_pairs(tmp_path):
    run_id = "run-memory-source"
    run_root = tmp_path / "workspace" / "runs" / run_id
    run_root.mkdir(parents=True)
    (run_root / "segments.json").write_text(
        json.dumps(
            {
                "language_direction": "JP_TO_CN",
                "chapters": [
                    {
                        "chapter_id": "ch-001",
                        "segments": [
                            {
                                "segment_id": "ch-001-seg-001",
                                "source_text": "主人公はレベル1だった。",
                                "draft_text": "主角是等级1。",
                                "status": "machine_translated",
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    doc = build_translation_memory_assets(
        repo_root=tmp_path,
        source_run=run_id,
        status_mode="translated",
    )

    assert doc["stats"]["pairs"] == 1
    assert doc["segment_map"]["ch-001-seg-001"] == "主角是等级1。"


def test_external_api_mode_requires_explicit_enablement(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    project_id = _seed_workbench_project(tmp_path)

    with pytest.raises(ExternalAssetExtractionUnavailable):
        build_translation_memory_assets(
            repo_root=tmp_path,
            project_id=project_id,
            mode="external_api",
        )


def test_prompt_builder_includes_asset_context():
    messages = build_batch_messages(
        [Segment(segment_id="seg-003", source_text="テスト")],
        chapter_label="章",
        asset_context="Term: アルファ => 阿尔法",
    )

    assert "翻译记忆资产" in messages[1].content
    assert "アルファ => 阿尔法" in messages[1].content


def test_draft_run_records_and_consumes_asset_context(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROLLED_RUN_ENABLED", "true")
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "false")
    asset_path = tmp_path / "workspace" / "assets" / "translation_memory" / "ctx.json"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_text(
        json.dumps(
            {
                "asset_kind": "translation_memory",
                "context_prompt": "Term: アルファ => 阿尔法",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    input_dir = tmp_path / "input_jp"
    input_dir.mkdir()
    (input_dir / "001-test.md").write_text("# 测试\n\n## 节\n\nアルファです。\n", encoding="utf-8")

    seen_messages: list[str] = []

    class StubProvider:
        provider_id = "stub"
        model_name = "stub-model"

        def __init__(self, cost_guard=None):
            self.cost_guard = cost_guard

        def generate(self, messages, options=None):  # noqa: ARG002
            from providers.types import ModelResult

            seen_messages.append(messages[1].content)
            fixed = {"items": [{"segment_id": "ch-001-seg-001", "translation": "这是阿尔法。"}]}
            result = ModelResult(
                provider_id=self.provider_id,
                model_name=self.model_name,
                raw_output=json.dumps(fixed, ensure_ascii=False),
                parsed_output=fixed,
            )
            result.mark_finished("ok")
            return result

    summary, run_root = run_draft_stage_a(
        repo_root=tmp_path,
        input_dir=input_dir,
        limit_chapters=1,
        run_id="asset-context-run",
        provider_factory=lambda g: StubProvider(cost_guard=g),
        asset_context_path=asset_path,
    )

    assert summary.asset_context_path == "workspace/assets/translation_memory/ctx.json"
    assert "アルファ => 阿尔法" in seen_messages[0]
    meta = json.loads((run_root / "run_metadata.json").read_text(encoding="utf-8"))
    assert meta["asset_context_path"] == "workspace/assets/translation_memory/ctx.json"
    assert render_translation_asset_context(asset_path) == "Term: アルファ => 阿尔法"
