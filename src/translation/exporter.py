"""Export draft artifacts to workspace run directory."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .baseline_guard import assert_baseline_writable, guarded_mkdir, guarded_write_text
from .chapter_parser import ParsedChapter


def export_chapter_markdown(
    chapter: ParsedChapter,
    out_dir: Path,
    *,
    repo_root: Path | None = None,
) -> Path:
    assert_baseline_writable(out_dir, repo_root)
    guarded_mkdir(out_dir, repo_root, parents=True, exist_ok=True)
    path = out_dir / f"{chapter.chapter_id}_draft_zh.md"
    lines = [f"# {chapter.chapter_label}", ""]
    for seg in chapter.segments:
        lines.extend([f"<!-- {seg.segment_id} -->", seg.draft_text or "", ""])
    guarded_write_text(path, "\n".join(lines).strip() + "\n", repo_root=repo_root)
    return path


def export_segments_doc(
    chapters: list[ParsedChapter],
    path: Path,
    *,
    repo_root: Path | None = None,
) -> None:
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
    assert_baseline_writable(path, repo_root)
    guarded_mkdir(path.parent, repo_root, parents=True, exist_ok=True)
    guarded_write_text(path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n", repo_root=repo_root)
