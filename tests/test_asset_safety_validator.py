"""Tests for asset safety validator."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from assets.asset_safety_validator import validate_asset
from assets.types import NarrativeAsset


def _safe_asset(**overrides):
    base = {
        "asset_id": "test-001",
        "asset_type": "narrative",
        "abstraction_level": "high",
        "copyright_safety_level": "safe",
        "reuse_guidance": "仅作结构参考。",
        "pattern_description": "章节以对话悬念开场。",
        "generated_examples": ["「接下来去哪？」", "「你听到了吗？」"],
    }
    base.update(overrides)
    return base


def test_missing_safety_fields_blocked():
    result = validate_asset(_safe_asset(reuse_guidance=""))
    assert not result.passed
    assert any("missing_required_field" in v for v in result.violations)


def test_long_text_blocked():
    result = validate_asset(_safe_asset(pattern_description="x" * 600))
    assert not result.passed
    assert any("long_text" in v for v in result.violations)


def test_unsafe_level_blocked():
    result = validate_asset(_safe_asset(copyright_safety_level="unsafe"))
    assert not result.passed
    assert "copyright_safety_level:unsafe" in result.violations


def test_example_from_source_blocked():
    source = "主人公はレベル1のステータス画面を開いた。まさかスキルが覚醒するなんて"
    result = validate_asset(
        _safe_asset(
            generated_examples=["主人公はレベル1のステータス画面を開いた。まさかスキルが覚醒"]
        ),
        source_corpus=source,
    )
    assert not result.passed
    assert any("example_from_source" in v for v in result.violations)


def test_too_many_source_specific_names():
    result = validate_asset(
        _safe_asset(
            pattern_description="アルファ団とベータ技術、ガンマ基地、デルタ計画、シグマ連盟が登場",
            generated_examples=["イプシロン商会の依頼"],
        )
    )
    assert not result.passed
    assert "too_many_source_specific_names" in result.violations


def test_narrative_retelling_blocked():
    result = validate_asset(
        _safe_asset(
            asset_type="narrative",
            pattern_description=(
                "然后主角去了森林，接着遇到敌人，随后战斗，与此同时队友支援，"
                "章节内容讲述了角色升级的故事讲述了很长的情节发展过程。"
            ),
            generated_examples=["然后他们继续前进，接着发生战斗。"],
        )
    )
    assert not result.passed
    assert "narrative_retelling_not_pattern" in result.violations


def test_safe_asset_passes():
    result = validate_asset(_safe_asset())
    assert result.passed
    assert result.violations == []


def test_dataclass_asset_passes():
    asset = NarrativeAsset(
        asset_id="na-1",
        abstraction_level="high",
        copyright_safety_level="safe",
        reuse_guidance="参考结构。",
        pattern_description="伏笔式对话开场。",
        generated_examples=["「那扇门后是什么？」"],
        structural_pattern="dialogue_hook",
    )
    result = validate_asset(asset)
    assert result.passed
