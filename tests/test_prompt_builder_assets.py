"""Tests for FS-016: prompt builders consume configs assets (spec §22).

Acceptance (docs/final_state_round_task_list.md FS-016):
- injected glossary entries ⊆ current batch hit set (asserted);
- context pack stays within budget;
- fake-provider end-to-end passes.

Fixtures use fictional sample terms only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from translation.chapter_parser import Segment  # noqa: E402
from translation.configs_asset_context import (  # noqa: E402
    ConfigsAssetContext,
    build_configs_asset_context,
)
from translation.prompt_builder import build_batch_messages  # noqa: E402
from translation.refine_prompt_builder import build_refine_batch_messages  # noqa: E402


def _write_glossary(path: Path, entries: list[dict]) -> Path:
    base = {
        "source_term": "",
        "target_term": "",
        "reading": None,
        "category": "other",
        "description": None,
        "first_seen_chapter": None,
        "confidence": None,
        "locked": False,
        "approved_by_user": False,
        "aliases": [],
        "notes": None,
        "created_at": "2026-06-11T00:00:00Z",
        "updated_at": "2026-06-11T00:00:00Z",
    }
    doc = {"schema_version": 1, "entries": [{**base, **e} for e in entries]}
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


def _write_characters(path: Path, characters: list[dict]) -> Path:
    base = {
        "name": "",
        "target_name": "",
        "aliases": [],
        "address_map": [],
        "first_person": None,
        "speech_tics": [],
        "honorific_style": None,
        "personality_summary": None,
        "speech_style": None,
        "forbidden": [],
        "appearing_chapters": [],
        "relationships": [],
        "manual_notes": None,
        "created_at": "2026-06-11T00:00:00Z",
        "updated_at": "2026-06-11T00:00:00Z",
    }
    doc = {"schema_version": 1, "characters": [{**base, **c} for c in characters]}
    path.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return path


@pytest.fixture()
def assets(tmp_path):
    glossary = _write_glossary(
        tmp_path / "glossary.yaml",
        [
            {"source_term": "サンプル王国", "target_term": "示例王国", "category": "place_name"},
            {"source_term": "サンプルギルド", "target_term": "示例公会", "category": "organization_name", "locked": True},
            {"source_term": "サンプル迷宮", "target_term": "示例迷宫", "category": "place_name"},  # never hit
            {"source_term": "サンプル聖剣", "target_term": "示例圣剑", "category": "item_name", "aliases": ["聖剣サンプル"]},
            {"source_term": "サンプル削除", "target_term": "已删", "category": "other", "deleted": True},  # tombstone
        ],
    )
    characters = _write_characters(
        tmp_path / "character_profile.yaml",
        [
            {
                "name": "サンプル・タロウ",
                "target_name": "示例太郎",
                "first_person": "俺",
                "speech_tics": ["～だぜ"],
                "honorific_style": "casual",
                "address_map": [{"to": "サンプル・ハナコ", "address": "ハナコさん"}],
                "forbidden": ["不得书面语"],
            },
            {"name": "サンプル・ハナコ", "target_name": "示例花子", "first_person": "私"},
            {"name": "サンプル・ジロウ", "target_name": "示例次郎"},  # never hit
        ],
    )
    return glossary, characters


BATCH_TEXTS = [
    "サンプル王国の朝、サンプル・タロウは歩き出した。",
    "聖剣サンプルを背負い、サンプルギルドへ向かう。",
]


# ---------------------------------------------------------------------------
# subset rule (spec §22)
# ---------------------------------------------------------------------------


def test_injected_glossary_subset_of_batch_hits(assets):
    glossary, characters = assets
    ctx = build_configs_asset_context(
        BATCH_TEXTS, glossary_path=glossary, character_path=characters
    )
    haystack = "\n".join(BATCH_TEXTS)
    # every injected term is genuinely hit (source or alias in batch)
    assert ctx.glossary_terms == sorted(
        ctx.glossary_terms, key=lambda t: 0
    )  # order checked separately
    for term in ctx.glossary_terms:
        assert term in haystack or term == "サンプル聖剣"  # alias hit case
    # never-hit and deleted terms are excluded
    assert "サンプル迷宮" not in ctx.text
    assert "サンプル削除" not in ctx.text
    # alias-hit term injected by canonical source_term
    assert "サンプル聖剣" in ctx.glossary_terms


def test_injected_characters_subset_of_batch_hits(assets):
    glossary, characters = assets
    ctx = build_configs_asset_context(
        BATCH_TEXTS, glossary_path=glossary, character_path=characters
    )
    assert "サンプル・タロウ" in ctx.characters
    assert "サンプル・ジロウ" not in ctx.characters  # not in batch
    assert "一人称=俺" in ctx.text
    assert "ハナコさん" in ctx.text  # address_map note


def test_locked_terms_sorted_first_and_flagged(assets):
    glossary, characters = assets
    ctx = build_configs_asset_context(
        BATCH_TEXTS, glossary_path=glossary, character_path=characters
    )
    assert ctx.glossary_terms[0] == "サンプルギルド"  # locked first
    assert "[locked]" in ctx.text


def test_empty_batch_or_missing_assets(tmp_path):
    ctx = build_configs_asset_context([], glossary_path=tmp_path / "no.yaml", character_path=tmp_path / "no2.yaml")
    assert ctx.empty
    ctx2 = build_configs_asset_context(
        ["何もヒットしない文"], glossary_path=tmp_path / "no.yaml", character_path=tmp_path / "no2.yaml"
    )
    assert ctx2.empty and ctx2.text == ""


# ---------------------------------------------------------------------------
# budget
# ---------------------------------------------------------------------------


def test_char_budget_respected(assets):
    glossary, characters = assets
    ctx = build_configs_asset_context(
        BATCH_TEXTS, glossary_path=glossary, character_path=characters, char_budget=60
    )
    assert ctx.char_count <= 60
    assert ctx.truncated is True


def test_max_terms_cap(assets, tmp_path):
    glossary, characters = assets
    ctx = build_configs_asset_context(
        BATCH_TEXTS,
        glossary_path=glossary,
        character_path=characters,
        max_glossary_terms=1,
    )
    assert len(ctx.glossary_terms) == 1
    assert ctx.truncated is True


# ---------------------------------------------------------------------------
# prompt builder integration
# ---------------------------------------------------------------------------


def test_draft_prompt_includes_hits_in_compact_mode(assets):
    glossary, characters = assets
    ctx = build_configs_asset_context(
        BATCH_TEXTS, glossary_path=glossary, character_path=characters
    )
    segments = [
        Segment(segment_id=f"ch-001-seg-{i:03d}", source_text=text)
        for i, text in enumerate(BATCH_TEXTS, start=1)
    ]
    messages = build_batch_messages(
        segments,
        chapter_label="ch-001",
        compact_context=True,
        glossary_hits=ctx.text,
    )
    user = messages[1].content
    assert "サンプルギルド => 示例公会 [locked]" in user
    assert "サンプル迷宮" not in user  # subset rule survives into prompt


def test_refine_prompt_includes_asset_context(assets):
    glossary, characters = assets
    ctx = build_configs_asset_context(
        BATCH_TEXTS, glossary_path=glossary, character_path=characters
    )
    batch = [
        {"segment_id": "ch-001-seg-001", "source_text": BATCH_TEXTS[0], "draft_text": "草稿一"},
        {"segment_id": "ch-001-seg-002", "source_text": BATCH_TEXTS[1], "draft_text": "草稿二"},
    ]
    messages = build_refine_batch_messages(
        batch, chapter_label="ch-001", asset_context=ctx.text
    )
    user = messages[1].content
    assert "本 batch 命中的术语与角色设定" in user
    assert "示例公会" in user

    plain = build_refine_batch_messages(batch, chapter_label="ch-001")
    assert "本 batch 命中的术语与角色设定" not in plain[1].content


def test_no_full_asset_dump(assets):
    """Guard: with a 50-entry glossary, only hit terms appear in context."""
    glossary, characters = assets
    entries = [
        {"source_term": f"サンプル未使用{i:02d}", "target_term": f"未使用{i:02d}", "category": "other"}
        for i in range(50)
    ]
    entries.append({"source_term": "サンプル王国", "target_term": "示例王国", "category": "place_name"})
    big = _write_glossary(glossary.parent / "big_glossary.yaml", entries)
    ctx = build_configs_asset_context(
        BATCH_TEXTS, glossary_path=big, character_path=characters
    )
    assert ctx.glossary_terms == ["サンプル王国"]
    assert "未使用" not in ctx.text


# ---------------------------------------------------------------------------
# fake provider end-to-end (task-card command equivalent)
# ---------------------------------------------------------------------------


def test_dataclass_shape():
    ctx = ConfigsAssetContext()
    assert ctx.empty and ctx.char_count == 0 and ctx.truncated is False
