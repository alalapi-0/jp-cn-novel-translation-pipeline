"""Build refinement prompts for Stage C (JP_TO_CN)."""

from __future__ import annotations

import json
from typing import Any

from providers.types import Message

REFINE_SYSTEM_PROMPT = """你是专业日文轻小说润色编辑。输入为日文原文与机器初译稿，请输出改进后的中文润色稿。

## 核心原则
1. 修正机翻腔、语序别扭与用词不当，不擅自改剧情、不增删信息。
2. 严格按 JSON 契约输出，不要输出 Markdown 代码围栏外的其他内容。

## 术语一致性
- 专名（人名、地名、组织、技能、物品、称号）全书译法须统一；同一日文表述不得出现多种中文写法。
- 已出现的固定译名须沿用，勿凭语感随意替换；必要注音或括号说明仅在原文需要时保留。
- 数字、日期、计量单位与原文信息一致。

## 角色语气一致性
- 对话须符合角色性格、年龄、社会身份与口癖；勿把所有角色润成同一种腔调。
- 敬语/常体、粗俗/文雅、简短/啰嗦等人设差异须保留并强化可读性。
- 称呼关系（你/您、昵称/全名、辈分称谓）前后一致。

## 叙事连贯性
- 叙述视角、人称与时态前后一致；段落衔接自然，避免重复主语或断裂感。
- 同一章节内语气风格连贯，勿局部过度文艺化或口语化。"""


def build_refine_batch_messages(
    segments: list[dict[str, Any]],
    *,
    chapter_label: str,
    prompt_version: str = "refine_v2",
    asset_context: str | None = None,
) -> list[Message]:
    items = [
        {
            "segment_id": s["segment_id"],
            "source_text": s.get("source_text", ""),
            "draft_text": s.get("draft_text", ""),
        }
        for s in segments
    ]
    contract = {
        "prompt_version": prompt_version,
        "language_direction": "JP_TO_CN",
        "pipeline_stage": "refinement",
        "chapter_label": chapter_label,
        "output_contract": {
            "format": "json",
            "schema": {
                "items": [
                    {
                        "segment_id": "string",
                        "refined_translation": "string",
                        "notes": "string (optional)",
                    }
                ]
            },
        },
        "segments": items,
    }
    context_prefix = ""
    if asset_context and asset_context.strip():
        context_prefix = (
            "以下为本 batch 命中的术语与角色设定（仅含命中子集，须严格遵循；"
            "locked 术语逐字使用）：\n" + asset_context.strip() + "\n\n"
        )
    user_content = (
        context_prefix
        + "请对以下 segments 进行对照式润色，返回单个 JSON 对象，键为 items（数组）。\n"
        "每个 item 必须包含 segment_id 与 refined_translation（也可用 translation 字段）。\n\n"
        + json.dumps(contract, ensure_ascii=False, indent=2)
    )
    return [
        Message(role="system", content=REFINE_SYSTEM_PROMPT),
        Message(role="user", content=user_content),
    ]
