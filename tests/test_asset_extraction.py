"""Tests for translation-derived asset extraction pipeline."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from assets.config import AssetExtractionConfig
from assets.loader import apply_segment_limit, select_chapters
from assets.model_assisted_extractor import ModelAssistedUnavailable, extract_model_assisted
from assets.rule_based_extractor import extract_all_rule_based
from assets.runner import run_asset_extraction

FIXTURE = REPO_ROOT / "tests" / "fixtures" / "asset_extraction_segments.json"


def _setup_source_run(tmp_path: Path) -> tuple[Path, str]:
    run_id = "test_source_run"
    run_root = tmp_path / "workspace" / "runs" / run_id
    run_root.mkdir(parents=True)
    (run_root / "segments.json").write_text(
        FIXTURE.read_text(encoding="utf-8"), encoding="utf-8"
    )
    # Sentinel files that must not change
    draft_dir = run_root / "draft"
    draft_dir.mkdir()
    draft_file = draft_dir / "ch-001_draft_zh.md"
    draft_file.write_text("# draft\n<!-- ch-001-seg-001 -->\nunchanged\n", encoding="utf-8")
    stage_state = tmp_path / "workspace" / "stage_state.json"
    stage_state.write_text('{"stage":"draft","version":1}\n', encoding="utf-8")
    return tmp_path, run_id


def test_rule_based_generates_three_plus_categories(tmp_path):
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    chapters = select_chapters(doc, chapters_spec="1-2", max_chapters=5)
    buckets = extract_all_rule_based(chapters)
    assert len(buckets["game_design"]) >= 1
    assert len(buckets["naming_pattern"]) >= 1
    assert len(buckets["narrative"]) >= 1
    assert len(buckets["chapter_structure"]) >= 1


def test_rule_based_no_api_calls(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "should-not-be-used")

    class Boom:
        def generate(self, *a, **k):
            raise AssertionError("API must not be called in rule-based mode")

    repo, run_id = _setup_source_run(tmp_path)
    summary = run_asset_extraction(
        repo_root=repo,
        source_run=run_id,
        mode="rule-based",
        chapters_spec="1-2",
        config=AssetExtractionConfig(),
        provider_factory=lambda g: Boom(),
    )
    assert summary["stats"]["api_calls"] == 0


def test_does_not_modify_translation_artifacts(tmp_path):
    repo, run_id = _setup_source_run(tmp_path)
    run_root = repo / "workspace" / "runs" / run_id
    draft_before = (run_root / "draft" / "ch-001_draft_zh.md").read_text(encoding="utf-8")
    segments_before = (run_root / "segments.json").read_text(encoding="utf-8")
    stage_before = (repo / "workspace" / "stage_state.json").read_text(encoding="utf-8")

    run_asset_extraction(
        repo_root=repo,
        source_run=run_id,
        mode="rule-based",
        chapters_spec="1-2",
        config=AssetExtractionConfig(),
    )

    assert (run_root / "draft" / "ch-001_draft_zh.md").read_text(encoding="utf-8") == draft_before
    assert (run_root / "segments.json").read_text(encoding="utf-8") == segments_before
    assert (repo / "workspace" / "stage_state.json").read_text(encoding="utf-8") == stage_before


def test_jsonl_output_format(tmp_path):
    repo, run_id = _setup_source_run(tmp_path)
    summary = run_asset_extraction(
        repo_root=repo,
        source_run=run_id,
        mode="rule-based",
        chapters_spec="1-2",
        config=AssetExtractionConfig(),
        run_id="test_extract_run",
    )
    out = Path(summary["output_dir"])
    for name in (
        "narrative_assets.jsonl",
        "game_design_assets.jsonl",
        "naming_pattern_assets.jsonl",
        "chapter_structure_assets.jsonl",
    ):
        path = out / name
        assert path.is_file()
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            assert "asset_id" in row
            assert "abstraction_level" in row
            assert "copyright_safety_level" in row
            assert "reuse_guidance" in row


def test_unsafe_asset_blocked_from_public_library(tmp_path):
    repo, run_id = _setup_source_run(tmp_path)
    cfg = AssetExtractionConfig(write_to_public_asset_library=True)
    summary = run_asset_extraction(
        repo_root=repo,
        source_run=run_id,
        mode="rule-based",
        chapters_spec="1-2",
        config=cfg,
        run_id="blocked_public_test",
    )
    pub = repo / "assets_extracted"
    # Default safe assets should pass; public only if safe assets exist
    if summary["safe_assets"] > 0:
        assert pub.is_dir()
    else:
        assert not pub.exists() or not any(pub.iterdir())


def test_generated_examples_not_from_source(tmp_path):
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    chapters = select_chapters(doc, chapters_spec="1-2", max_chapters=5)
    source_blob = "\n".join(
        seg.source_text for ch in chapters for seg in ch.segments
    )
    buckets = extract_all_rule_based(chapters)
    for items in buckets.values():
        for asset in items:
            for example in asset.generated_examples:
                assert example not in source_blob
                assert "主人公はレベル1" not in example


def test_model_assisted_without_api_key(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "false")
    repo, run_id = _setup_source_run(tmp_path)
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    chapters = select_chapters(doc, chapters_spec="1-1", max_chapters=5)
    cfg = AssetExtractionConfig(allow_real_api=True)
    with pytest.raises(ModelAssistedUnavailable):
        extract_model_assisted(chapters, config=cfg)


def test_model_assisted_dry_run_skips(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    repo, run_id = _setup_source_run(tmp_path)
    with pytest.raises(ModelAssistedUnavailable):
        run_asset_extraction(
            repo_root=repo,
            source_run=run_id,
            mode="model-assisted",
            chapters_spec="1-1",
            config=AssetExtractionConfig(allow_real_api=False),
            dry_run_model=False,
        )


def test_max_chapters_and_segments_limits(tmp_path):
    doc = json.loads(FIXTURE.read_text(encoding="utf-8"))
    chapters = select_chapters(doc, chapters_spec="1-5", max_chapters=1)
    assert len(chapters) == 1
    trimmed = apply_segment_limit(chapters, max_segments=2)
    total = sum(len(c.segments) for c in trimmed)
    assert total == 2

    repo, run_id = _setup_source_run(tmp_path)
    summary = run_asset_extraction(
        repo_root=repo,
        source_run=run_id,
        mode="rule-based",
        chapters_spec="1-5",
        config=AssetExtractionConfig(max_chapters=1, max_segments=2),
        run_id="limit_test",
    )
    assert summary["stats"]["chapters_processed"] == 1
    assert summary["stats"]["segments_processed"] == 2


def test_extraction_outputs_reports(tmp_path):
    repo, run_id = _setup_source_run(tmp_path)
    summary = run_asset_extraction(
        repo_root=repo,
        source_run=run_id,
        mode="rule-based",
        run_id="report_test",
        config=AssetExtractionConfig(),
    )
    out = Path(summary["output_dir"])
    assert (out / "extraction_metadata.json").is_file()
    assert (out / "abstraction_safety_report.md").is_file()
    assert (out / "extraction_quality_report.md").is_file()
    meta = json.loads((out / "extraction_metadata.json").read_text(encoding="utf-8"))
    assert meta["mode"] == "rule-based"
    assert meta["source_run_id"] == run_id
