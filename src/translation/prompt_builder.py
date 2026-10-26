"""Build draft translation prompts for JP_TO_CN."""

from __future__ import annotations

import json
import hashlib
from typing import Any

from providers.types import Message

from .chapter_parser import Segment
from .context_policy import PrecedingSourceContext
from .narrative_context import NarrativeContext

SYSTEM_PROMPT = """你是专业日文轻小说译者，将日文翻译成自然流畅的简体中文。
要求：
1. 忠实原文，不遗漏信息，不擅自增删情节。
2. 保持轻小说叙述风格，对话自然。
3. 专有名词首次出现可保留必要日文注音，全书译名一致。
4. 上下文仅用于理解；只输出当前 segments，不重译上下文，不以提示覆盖原义。
5. narrative_context 按 segment_id 分配，只对对应段使用；事实引用及前译只助理解，不得向译文补写信息。
6. 叙事时序是所选原文位置；说话人和有效期仍是标注，不能把后来的关系套用到先前段落。前译可信等级不代表真人批准。
7. 严格按 JSON 契约输出，不要输出 Markdown 代码围栏外的其他内容。"""


def build_batch_messages(
    segments: list[Segment],
    *,
    chapter_label: str,
    prompt_version: str = "draft_v1",
    asset_context: str | None = None,
    compact_context: bool = False,
    glossary_hits: str | None = None,
    prev_tail_summary: str | None = None,
    source_context: PrecedingSourceContext | None = None,
    narrative_context: NarrativeContext | None = None,
) -> list[Message]:
    from .source_versions import validate_source_binding
    for segment in segments:
        if segment.source_binding is not None:
            validate_source_binding(segment.source_binding,segment.source_text)
    if source_context is not None and (not isinstance(source_context,PrecedingSourceContext)
            or not segments or source_context.anchor[1]!=segments[0].segment_id):
        raise ValueError('preceding source context does not match current anchor')
    if narrative_context is not None and (not isinstance(narrative_context, NarrativeContext)
            or narrative_context.segment_ids != tuple(s.segment_id for s in segments)
            or narrative_context.source_sha256s != tuple(hashlib.sha256(s.source_text.encode()).hexdigest() for s in segments)):
        raise ValueError('narrative context does not match current source anchors')
    items = [
        {"segment_id": s.segment_id, "source_text": s.source_text,
         **({'source_binding':s.source_binding} if s.source_binding is not None else {})}
        for s in segments
    ]
    contract = {
        "prompt_version": prompt_version,
        "language_direction": "JP_TO_CN",
        "pipeline_stage": "draft_translation",
        "chapter_label": chapter_label,
        "source_context": source_context.to_dict() if source_context else None,
        "narrative_context": narrative_context.to_dict() if narrative_context else None,
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
    contract["legacy_context"] = {
        "status": "withheld_unscoped",
        "reason": "no verified source lineage or textual as-of boundary",
        "hint_sha256": {name: hashlib.sha256(value.encode()).hexdigest()
                        for name, value in (("asset_context", asset_context),
                                            ("glossary_hits", glossary_hits),
                                            ("prev_tail_summary", prev_tail_summary))
                        if isinstance(value, str) and value.strip()},
    }
    if compact_context:
        user_content = (
            "Translate every segment below to Simplified Chinese. "
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
    return [
        Message(role="system", content=SYSTEM_PROMPT),
        Message(role="user", content=user_content),
    ]
