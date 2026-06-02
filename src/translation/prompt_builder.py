"""Build draft translation prompts for JP_TO_CN."""

from __future__ import annotations

import json
from typing import Any

from providers.types import Message

from .chapter_parser import Segment

SYSTEM_PROMPT = """你是专业日文轻小说译者，将日文翻译成自然流畅的简体中文。
要求：
1. 忠实原文，不遗漏信息，不擅自增删情节。
2. 保持轻小说叙述风格，对话自然。
3. 专有名词首次出现可保留必要日文注音，全书译名一致。
4. 严格按 JSON 契约输出，不要输出 Markdown 代码围栏外的其他内容。"""


def build_batch_messages(
    segments: list[Segment],
    *,
    chapter_label: str,
    prompt_version: str = "draft_v1",
) -> list[Message]:
    items = [
        {"segment_id": s.segment_id, "source_text": s.source_text}
        for s in segments
    ]
    contract = {
        "prompt_version": prompt_version,
        "language_direction": "JP_TO_CN",
        "pipeline_stage": "draft_translation",
        "chapter_label": chapter_label,
        "output_contract": {
            "format": "json",
            "schema": {
                "items": [
                    {
                        "segment_id": "string",
                        "translation": "string",
                        "notes": "string (optional)",
                    }
                ]
            },
        },
        "segments": items,
    }
    user_content = (
        "请将以下 segments 全部译为中文，返回单个 JSON 对象，键为 items（数组）。\n"
        "每个 item 必须包含 segment_id 与 translation。\n\n"
        + json.dumps(contract, ensure_ascii=False, indent=2)
    )
    return [
        Message(role="system", content=SYSTEM_PROMPT),
        Message(role="user", content=user_content),
    ]
