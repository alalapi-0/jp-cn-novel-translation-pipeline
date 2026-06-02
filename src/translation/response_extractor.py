"""Extract structured translations from model raw output."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ExtractedItem:
    segment_id: str
    translation: str
    notes: str = ""


@dataclass
class ExtractionResult:
    parse_status: str
    items: list[ExtractedItem] = field(default_factory=list)
    parse_errors: list[str] = field(default_factory=list)


def _try_json_load(text: str) -> Any | None:
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if fence:
        try:
            return json.loads(fence.group(1).strip())
        except json.JSONDecodeError:
            pass
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            pass
    return None


def _normalize_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    if isinstance(data, dict):
        if "items" in data and isinstance(data["items"], list):
            return [x for x in data["items"] if isinstance(x, dict)]
        if "translations" in data and isinstance(data["translations"], list):
            return [x for x in data["translations"] if isinstance(x, dict)]
        if "segment_id" in data and "translation" in data:
            return [data]
    return []


def extract_translations(raw_output: str, expected_segment_ids: list[str]) -> ExtractionResult:
    errors: list[str] = []
    data = _try_json_load(raw_output)
    if data is None:
        return ExtractionResult(
            parse_status="failed",
            parse_errors=["json_parse_failed"],
        )

    rows = _normalize_items(data)
    if not rows:
        return ExtractionResult(
            parse_status="failed",
            parse_errors=["no_items_in_payload"],
        )

    items: list[ExtractedItem] = []
    seen: set[str] = set()
    for row in rows:
        sid = str(row.get("segment_id", "")).strip()
        trans = str(row.get("translation", row.get("target_text", ""))).strip()
        if not sid:
            errors.append("missing_segment_id")
            continue
        if sid in seen:
            errors.append(f"duplicate_segment_id:{sid}")
            continue
        seen.add(sid)
        items.append(
            ExtractedItem(
                segment_id=sid,
                translation=trans,
                notes=str(row.get("notes", "")),
            )
        )

    missing = [sid for sid in expected_segment_ids if sid not in seen]
    if missing:
        errors.append(f"missing_segments:{len(missing)}")

    status = "ok" if not missing and not errors else ("partial" if items else "failed")
    return ExtractionResult(parse_status=status, items=items, parse_errors=errors)
