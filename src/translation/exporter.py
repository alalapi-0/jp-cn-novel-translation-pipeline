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
    language_direction: str = "JP_TO_CN",
) -> None:
    if language_direction not in {'JP_TO_CN','CN_TO_JP'}:
        raise ValueError('unsupported source export direction')
    doc: dict[str, Any] = {
        "language_direction": language_direction,
        "pipeline_stage": "draft",
        "chapters": [],
    }
    for ch in chapters:
        from .source_versions import validate_source_binding
        for segment in ch.segments:
            if ch.source_revision and segment.source_binding is None:
                raise ValueError('versioned chapter has an unbound source segment')
            if segment.source_binding is not None:
                binding=validate_source_binding(segment.source_binding,segment.source_text)
                if binding['chapter_id']!=ch.chapter_id or binding['source_revision']!=ch.source_revision:
                    raise ValueError('segment source binding differs from exported chapter')
        doc["chapters"].append(
            {
                "chapter_id": ch.chapter_id,
                "chapter_label": ch.chapter_label,
                "source_path": ch.source_path,
                **({'source_revision':ch.source_revision,'parser_version':ch.parser_version} if ch.source_revision else {}),
                "segments": [
                    {
                        "segment_id": s.segment_id,
                        "source_text": s.source_text,
                        "draft_text": s.draft_text,
                        "status": s.status,
                        **({'source_binding':s.source_binding} if s.source_binding is not None else {}),
                    }
                    for s in ch.segments
                ],
            }
        )
    assert_baseline_writable(path, repo_root)
    guarded_mkdir(path.parent, repo_root, parents=True, exist_ok=True)
    guarded_write_text(path, json.dumps(doc, ensure_ascii=False, indent=2) + "\n", repo_root=repo_root)
