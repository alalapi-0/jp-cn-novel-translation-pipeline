"""Export draft artifacts to workspace run directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .chapter_parser import ParsedChapter


def export_chapter_markdown(chapter: ParsedChapter, out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{chapter.chapter_id}_draft_zh.md"
    lines = [f"# {chapter.chapter_label}", ""]
    for seg in chapter.segments:
        lines.extend([f"<!-- {seg.segment_id} -->", seg.draft_text or "", ""])
    path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return path


def export_segments_doc(chapters: list[ParsedChapter], path: Path) -> None:
    doc: dict[str, Any] = {
        "language_direction": "JP_TO_CN",
        "pipeline_stage": "draft",
        "chapters": [],
    }
    for ch in chapters:
        doc["chapters"].append(
            {
                "chapter_id": ch.chapter_id,
                "chapter_label": ch.chapter_label,
                "source_path": ch.source_path,
                "segments": [
                    {
                        "segment_id": s.segment_id,
                        "source_text": s.source_text,
                        "draft_text": s.draft_text,
                        "status": s.status,
                    }
                    for s in ch.segments
                ],
            }
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
