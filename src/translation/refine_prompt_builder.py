"""Build refinement prompts for Stage C (JP_TO_CN)."""

from __future__ import annotations

import json
from typing import Any

from providers.types import Message

REFINE_SYSTEM_PROMPT = """你是专业日文轻小说润色编辑。输入为日文原文与机器初译稿，请输出改进后的中文润色稿。
要求：
1. 修正机翻腔与不自然表达，不擅自改剧情、不增删信息。
2. 保持术语与角色语气一致；勿过度文艺化或统一文风。
3. 严格按 JSON 契约输出，不要输出 Markdown 代码围栏外的其他内容。"""


def build_refine_batch_messages(
    segments: list[dict[str, Any]],
    *,
    chapter_label: str,
    prompt_version: str = "refine_v1",
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
    user_content = (
        "请对以下 segments 进行对照式润色，返回单个 JSON 对象，键为 items（数组）。\n"
        "每个 item 必须包含 segment_id 与 refined_translation（也可用 translation 字段）。\n\n"
        + json.dumps(contract, ensure_ascii=False, indent=2)
    )
    return [
        Message(role="system", content=REFINE_SYSTEM_PROMPT),
        Message(role="user", content=user_content),
    ]
