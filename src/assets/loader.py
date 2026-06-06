"""Read-only loader for translation run segments."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass
class LoadedSegment:
    segment_id: str
    chapter_id: str
    source_text: str
    draft_text: str
    refined_text: str


@dataclass
class LoadedChapter:
    chapter_id: str
    chapter_label: str
    segments: list[LoadedSegment]


def _parse_chapter_range(spec: str) -> tuple[int, int] | None:
    m = re.match(r"^(\d+)\s*-\s*(\d+)$", spec.strip())
    if not m:
        return None
    start, end = int(m.group(1)), int(m.group(2))
    if start > end:
        start, end = end, start
    return start, end


def _chapter_number(chapter_id: str) -> int | None:
    m = re.search(r"(\d+)", chapter_id)
    return int(m.group(1)) if m else None


def resolve_source_run_root(repo_root: Path, source_run: str) -> Path:
    candidate = repo_root / source_run
    if candidate.is_dir() and (candidate / "segments.json").is_file():
        return candidate
    runs = repo_root / "workspace" / "runs" / source_run
    if runs.is_dir():
        return runs
    diag = (
        repo_root
        / "workspace"
        / "diagnostics"
        / "real_api_runs"
        / source_run
        / "workspace"
        / "runs"
        / source_run
    )
    if diag.is_dir():
        return diag
    raise FileNotFoundError(f"source run not found: {source_run}")


def load_segments_doc(run_root: Path) -> dict[str, Any]:
    path = run_root / "segments.json"
    if not path.is_file():
        raise FileNotFoundError(f"missing segments.json in {run_root}")
    return json.loads(path.read_text(encoding="utf-8"))


def select_chapters(
    doc: dict[str, Any],
    *,
    chapters_spec: str | None = None,
    max_chapters: int = 5,
) -> list[LoadedChapter]:
    raw_chapters = doc.get("chapters") or []
    chapter_range = _parse_chapter_range(chapters_spec) if chapters_spec else None

    loaded: list[LoadedChapter] = []
    for ch in raw_chapters:
        chapter_id = str(ch.get("chapter_id", ""))
        if chapter_range:
            num = _chapter_number(chapter_id)
            if num is None or num < chapter_range[0] or num > chapter_range[1]:
                continue
        segments: list[LoadedSegment] = []
        for seg in ch.get("segments") or []:
            segments.append(
                LoadedSegment(
                    segment_id=str(seg.get("segment_id", "")),
                    chapter_id=chapter_id,
                    source_text=str(seg.get("source_text", "")),
                    draft_text=str(seg.get("draft_text", "")),
                    refined_text=str(seg.get("refined_text", "")),
                )
            )
        loaded.append(
            LoadedChapter(
                chapter_id=chapter_id,
                chapter_label=str(ch.get("chapter_label", chapter_id)),
                segments=segments,
            )
        )
        if len(loaded) >= max_chapters:
            break
    return loaded


def collect_source_corpus(chapters: list[LoadedChapter]) -> str:
    parts: list[str] = []
    for ch in chapters:
        for seg in ch.segments:
            parts.append(seg.source_text)
            parts.append(seg.draft_text)
            parts.append(seg.refined_text)
    return "\n".join(p for p in parts if p.strip())


def apply_segment_limit(
    chapters: list[LoadedChapter], max_segments: int
) -> list[LoadedChapter]:
    if max_segments <= 0:
        return chapters
    remaining = max_segments
    trimmed: list[LoadedChapter] = []
    for ch in chapters:
        if remaining <= 0:
            break
        segs = ch.segments[:remaining]
        remaining -= len(segs)
        trimmed.append(
            LoadedChapter(
                chapter_id=ch.chapter_id,
                chapter_label=ch.chapter_label,
                segments=segs,
            )
        )
    return trimmed
