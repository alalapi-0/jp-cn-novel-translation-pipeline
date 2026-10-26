"""Dry-run / fake segment generation for Workbench quickstart (no API)."""

from __future__ import annotations

import re
from typing import Any


def _split_paragraphs(text: str) -> list[str]:
    chunks = [p.strip() for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    if chunks:
        return chunks
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    return lines or [text.strip()] if text.strip() else []


def fake_draft(source: str, *, direction: str) -> str:
    if direction.upper().startswith("CN"):
        return f"（dry-run 日译占位）{source[:120]}"
    return f"（dry-run 中译占位）{source[:120]}"


def source_segments_from_sample(sample_text: str) -> list[dict[str, Any]]:
    """All imported source paragraphs; no model output or preview truncation."""
    return [{"id": f"seg-{i:03d}", "segment_id": f"seg-{i:03d}", "chapter": 1, "source": para}
            for i, para in enumerate(_split_paragraphs(sample_text), start=1)]


def generate_segments_from_sample(
    *,
    sample_text: str,
    language_direction: str = "JP_TO_CN",
) -> list[dict[str, Any]]:
    return [{**row, "draft": fake_draft(row["source"], direction=language_direction), "status": "pending"}
            for row in source_segments_from_sample(sample_text)]
