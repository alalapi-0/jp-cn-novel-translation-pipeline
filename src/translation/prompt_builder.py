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


def _prev_tail_summary(segments: list[Segment], *, max_chars: int = 180) -> str:
    if not segments:
        return ""
    first = segments[0].source_text.strip()
    if not first:
        return ""
    return first[:max_chars]


def build_batch_messages(
    segments: list[Segment],
    *,
    chapter_label: str,
    prompt_version: str = "draft_v1",
    asset_context: str | None = None,
    compact_context: bool = False,
    glossary_hits: str | None = None,
    prev_tail_summary: str | None = None,
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
    }
    context_lines: list[str] = []
    if compact_context:
        context_lines.append(f"Chapter: {chapter_label}")
        tail = (prev_tail_summary or _prev_tail_summary(segments)).strip()
        if tail:
            context_lines.append(f"Batch opening context (style reference only): {tail}")
        hits = (glossary_hits or asset_context or "").strip()
        if hits:
            context_lines.append(hits)
        if context_lines:
            user_prefix = "\n".join(context_lines) + "\n\n"
        else:
            user_prefix = ""
        user_content = (
            user_prefix
            + "Translate every segment below to Simplified Chinese. "
            "Return one JSON object with key items (array); each item needs segment_id and translation.\n\n"
            + json.dumps({**contract, "segments": items}, ensure_ascii=False, indent=2)
        )
    else:
        contract["segments"] = items
        user_content = (
            "请将以下 segments 全部译为中文，返回单个 JSON 对象，键为 items（数组）。\n"
            "每个 item 必须包含 segment_id 与 translation。\n\n"
            + json.dumps(contract, ensure_ascii=False, indent=2)
        )
        if asset_context and asset_context.strip():
            user_content += (
                "\n\n以下是从过往已审核/已完成译文沉淀出的翻译记忆资产。"
                "仅在相关时用于术语、译名、短语和风格一致性；不得覆盖本次原文含义。\n"
                + asset_context.strip()
            )
    return [
        Message(role="system", content=SYSTEM_PROMPT),
        Message(role="user", content=user_content),
    ]
