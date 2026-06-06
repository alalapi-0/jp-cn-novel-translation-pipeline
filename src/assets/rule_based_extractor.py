"""Rule-based asset extraction — no API calls."""

from __future__ import annotations

import re
import uuid
from typing import Iterable

from .loader import LoadedChapter
from .types import (
    ChapterStructureAsset,
    GameDesignAsset,
    NarrativeAsset,
    NamingPatternAsset,
)

_GAME_KEYWORDS: tuple[tuple[str, str, list[str]], ...] = (
    ("vr_world", "虚拟现实世界机制", ["ＶＲ", "VR", "ヴァーチャル", "虚拟", "虚拟现实"]),
    ("status_system", "角色状态/等级系统", ["レベル", "等级", "経験値", "经验值", "ステータス", "状态"]),
    ("skill_acquisition", "技能获取机制", ["スキル", "技能", "能力", "特技", "天赋"]),
    ("achievement", "成就/称号机制", ["称号", "実績", "成就", "ランク", "排名"]),
)

_NAMING_PATTERNS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("katakana_proper_noun", "片假名专有名词模式", re.compile(r"[ァ-ヴー]{3,}")),
    ("dialogue_marker", "对话引号标记模式", re.compile(r"[「『].+?[」』]")),
    ("bracket_annotation", "方括号注释模式", re.compile(r"【[^】]+】")),
)

_NARRATIVE_HOOKS: tuple[tuple[str, str, re.Pattern[str]], ...] = (
    ("world_building_opening", "世界观铺陈开场", re.compile(r"(新暦|公元|时代|世界|文明|技術|技术)")),
    ("dialogue_hook", "对话悬念钩子", re.compile(r"[「『].+?\?|？.+?[」』]")),
    ("foreshadowing", "伏笔暗示句式", re.compile(r"(まさか|没想到|竟然|しかし|但是|然而|不料)")),
)


def _new_id(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10]}"


def _synthetic_examples(kind: str) -> list[str]:
    """Generic placeholders — never copied from source text."""
    templates = {
        "vr_world": ["玩家在虚拟主城接受日常任务。", "角色通过神经接口进入模拟训练场。"],
        "status_system": ["角色升级后解锁新的被动加成槽位。", "经验条满后触发分支职业选择。"],
        "skill_acquisition": ["完成试炼后获得可进化的基础技能。", "隐藏任务奖励赋予区域限定能力。"],
        "achievement": ["达成连续登录成就获得称号装饰。", "首次通关副本解锁纪念徽章。"],
        "katakana_proper_noun": ["示例：アルファ団の拠点へ向かう。", "示例：ベータ技術を研究する。"],
        "dialogue_marker": ["「这里还安全吗？」", "「下一步去哪里？」"],
        "bracket_annotation": ["【系统提示】任务已更新", "【稀有】掉落概率提升"],
        "world_building_opening": ["故事以宏观时代背景切入，再聚焦主角。", "开篇交代技术革命后的社会结构。"],
        "dialogue_hook": ["「你听到了吗？」", "「那扇门后面是什么？」"],
        "foreshadowing": ["看似普通的物件将在后文发挥作用。", "配角随口一提的传闻埋下后续冲突。"],
        "chapter_opening": ["章节以场景描写建立氛围。", "章节以短对话迅速进入冲突。"],
        "chapter_closing": ["章末以未解问题收束。", "章末以新信息揭示推动翻页。"],
        "info_pacing": ["先抛现象再解释规则。", "信息分层释放避免设定堆砌。"],
    }
    return templates.get(kind, ["抽象示例 A", "抽象示例 B"])


def _chapter_blob(chapter: LoadedChapter) -> str:
    return "\n".join(seg.source_text for seg in chapter.segments)


def extract_game_design_assets(chapters: Iterable[LoadedChapter]) -> list[GameDesignAsset]:
    assets: list[GameDesignAsset] = []
    for chapter in chapters:
        blob = _chapter_blob(chapter)
        for key, label, keywords in _GAME_KEYWORDS:
            hits = [kw for kw in keywords if kw in blob]
            if not hits:
                continue
            assets.append(
                GameDesignAsset(
                    asset_id=_new_id("gd"),
                    abstraction_level="high",
                    copyright_safety_level="safe",
                    reuse_guidance="仅作机制灵感，不得复刻具体设定名或剧情桥段。",
                    pattern_description=(
                        f"检测到{label}相关信号（关键词抽象匹配：{', '.join(hits[:3])}）。"
                        "可泛化为同类轻小说/游戏化叙事机制模板。"
                    ),
                    generated_examples=_synthetic_examples(key),
                    source_chapter_ids=[chapter.chapter_id],
                    tags=["rule-based", label, "mechanism"],
                    mechanism_category=key,
                    abstraction_scope="cross_title_mechanism",
                )
            )
    return assets


def extract_naming_pattern_assets(chapters: Iterable[LoadedChapter]) -> list[NamingPatternAsset]:
    assets: list[NamingPatternAsset] = []
    for chapter in chapters:
        blob = _chapter_blob(chapter)
        for key, label, pattern in _NAMING_PATTERNS:
            matches = pattern.findall(blob)
            if not matches:
                continue
            assets.append(
                NamingPatternAsset(
                    asset_id=_new_id("np"),
                    abstraction_level="high",
                    copyright_safety_level="safe",
                    reuse_guidance="学习命名结构，不复制具体专名；新作品应替换为原创名称。",
                    pattern_description=(
                        f"章节呈现「{label}」：匹配次数 {min(len(matches), 99)}。"
                        "建议在新作中使用同类结构但不同词形。"
                    ),
                    generated_examples=_synthetic_examples(key),
                    source_chapter_ids=[chapter.chapter_id],
                    tags=["rule-based", "naming", key],
                    pattern_kind=key,
                    linguistic_markers=[label],
                )
            )
    return assets


def extract_narrative_assets(chapters: Iterable[LoadedChapter]) -> list[NarrativeAsset]:
    assets: list[NarrativeAsset] = []
    for chapter in chapters:
        blob = _chapter_blob(chapter)
        for key, label, pattern in _NARRATIVE_HOOKS:
            if not pattern.search(blob):
                continue
            assets.append(
                NarrativeAsset(
                    asset_id=_new_id("na"),
                    abstraction_level="high",
                    copyright_safety_level="safe",
                    reuse_guidance="借鉴叙事功能与结构节奏，不复述具体情节。",
                    pattern_description=f"结构模式：{label}。关注信息释放顺序与读者悬念管理。",
                    generated_examples=_synthetic_examples(key),
                    source_chapter_ids=[chapter.chapter_id],
                    tags=["rule-based", "narrative", key],
                    narrative_role="hook_or_foreshadow",
                    structural_pattern=key,
                )
            )
    return assets


def extract_chapter_structure_assets(chapters: Iterable[LoadedChapter]) -> list[ChapterStructureAsset]:
    assets: list[ChapterStructureAsset] = []
    for chapter in chapters:
        segs = chapter.segments
        if not segs:
            continue
        dialogue_count = sum(1 for s in segs if "「" in s.source_text or "『" in s.source_text)
        ratio = dialogue_count / max(len(segs), 1)
        opening = segs[0].source_text[:80]
        closing = segs[-1].source_text[:80]

        hook_type = "dialogue_led" if ratio >= 0.35 else "exposition_led"
        pacing = "对话驱动" if ratio >= 0.35 else "叙述驱动"

        assets.append(
            ChapterStructureAsset(
                asset_id=_new_id("cs"),
                abstraction_level="medium",
                copyright_safety_level="safe",
                reuse_guidance="参考章节节奏与钩子类型，不照搬首尾句。",
                pattern_description=(
                    f"章节功能分析：共 {len(segs)} 段，对话段占比约 {ratio:.0%}。"
                    f"开篇特征：{'对话/引语' if '「' in opening else '叙述/场景'}；"
                    f"收束特征：{'悬念式' if '？' in closing or '?' in closing else '陈述式'}。"
                ),
                generated_examples=_synthetic_examples("chapter_opening")
                + _synthetic_examples("chapter_closing"),
                source_chapter_ids=[chapter.chapter_id],
                tags=["rule-based", "structure", hook_type],
                chapter_function="setup_and_hook",
                hook_type=hook_type,
                pacing_notes=pacing,
            )
        )

        if len(segs) >= 4:
            assets.append(
                ChapterStructureAsset(
                    asset_id=_new_id("cs"),
                    abstraction_level="high",
                    copyright_safety_level="safe",
                    reuse_guidance="采用分层信息披露，避免一次性倾倒设定。",
                    pattern_description="信息释放节奏：前段建立场景，中段引入冲突或规则，末段留钩子。",
                    generated_examples=_synthetic_examples("info_pacing"),
                    source_chapter_ids=[chapter.chapter_id],
                    tags=["rule-based", "structure", "pacing"],
                    chapter_function="information_release",
                    hook_type="layered_reveal",
                    pacing_notes="分层释放",
                )
            )
    return assets


def extract_all_rule_based(chapters: list[LoadedChapter]) -> dict[str, list]:
    return {
        "narrative": extract_narrative_assets(chapters),
        "game_design": extract_game_design_assets(chapters),
        "naming_pattern": extract_naming_pattern_assets(chapters),
        "chapter_structure": extract_chapter_structure_assets(chapters),
    }
