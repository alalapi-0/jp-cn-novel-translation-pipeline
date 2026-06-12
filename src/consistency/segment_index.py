"""Segment index builder (FS-032, Level 0-1).

Builds a metadata-only segment-level index: segment_id ↔ chapter / paragraph
mapping, source/draft lengths, status. Detects missing segments and
misalignment. Never writes source_text or draft_text into the index document.

Streaming: processes one segments.json file and one chapter at a time; text
fields are read only to compute lengths and are not retained in output.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

from consistency.manifest import (
    chapter_number_from_id,
    file_fingerprint,
    find_segments_files,
)

SCHEMA_VERSION = 1

_SEGMENT_ID_RE = re.compile(r"^ch-(\d+)-seg-(\d+)$", re.IGNORECASE)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_segment_id(segment_id: str) -> tuple[int, int] | None:
    """Parse ``ch-{n}-seg-{m}`` into (chapter_number, segment_index)."""
    match = _SEGMENT_ID_RE.match(str(segment_id or "").strip())
    if not match:
        return None
    return int(match.group(1)), int(match.group(2))


def expected_segment_id(chapter_number: int, segment_index: int) -> str:
    return f"ch-{chapter_number:03d}-seg-{segment_index:03d}"


def _segment_entry(
    segment: dict[str, Any],
    *,
    chapter_id: str,
    chapter_number: int,
    position: int,
    run_id: str,
) -> dict[str, Any]:
    segment_id = str(segment.get("segment_id") or "")
    source_text = segment.get("source_text") or ""
    draft_text = segment.get("draft_text") or ""
    parsed = parse_segment_id(segment_id)
    return {
        "segment_id": segment_id,
        "chapter_id": chapter_id,
        "chapter_number": chapter_number,
        "paragraph_index": parsed[1] if parsed else position,
        "segment_index": parsed[1] if parsed else position,
        "position_in_chapter": position,
        "source_run_id": run_id,
        "source_length": len(source_text),
        "draft_length": len(draft_text),
        "status": str(segment.get("status") or ""),
        "has_draft": bool(str(draft_text).strip()),
        "has_source": bool(str(source_text).strip()),
    }


def _detect_chapter_issues(
    chapter_id: str,
    chapter_number: int,
    segments: list[dict[str, Any]],
    *,
    run_id: str,
) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """Return (segments_by_id, missing_segments, misalignments) for one chapter."""
    by_id: dict[str, dict[str, Any]] = {}
    misalignments: list[dict[str, Any]] = []
    seen_ids: dict[str, int] = {}

    for position, segment in enumerate(segments, start=1):
        segment_id = str(segment.get("segment_id") or "")
        if not segment_id:
            misalignments.append(
                {
                    "issue_type": "empty_segment_id",
                    "chapter_id": chapter_id,
                    "chapter_number": chapter_number,
                    "position_in_chapter": position,
                    "segment_id": "",
                    "source_run_id": run_id,
                }
            )
            continue

        if segment_id in seen_ids:
            misalignments.append(
                {
                    "issue_type": "duplicate_segment_id",
                    "chapter_id": chapter_id,
                    "chapter_number": chapter_number,
                    "segment_id": segment_id,
                    "first_position": seen_ids[segment_id],
                    "duplicate_position": position,
                    "source_run_id": run_id,
                }
            )
        else:
            seen_ids[segment_id] = position

        parsed = parse_segment_id(segment_id)
        if parsed is None:
            misalignments.append(
                {
                    "issue_type": "unparseable_segment_id",
                    "chapter_id": chapter_id,
                    "chapter_number": chapter_number,
                    "segment_id": segment_id,
                    "position_in_chapter": position,
                    "source_run_id": run_id,
                }
            )
        elif parsed[0] != chapter_number:
            misalignments.append(
                {
                    "issue_type": "chapter_mismatch",
                    "chapter_id": chapter_id,
                    "chapter_number": chapter_number,
                    "segment_id": segment_id,
                    "parsed_chapter_number": parsed[0],
                    "position_in_chapter": position,
                    "source_run_id": run_id,
                }
            )
        elif parsed[1] != position:
            misalignments.append(
                {
                    "issue_type": "index_order_mismatch",
                    "chapter_id": chapter_id,
                    "chapter_number": chapter_number,
                    "segment_id": segment_id,
                    "expected_index": position,
                    "parsed_index": parsed[1],
                    "source_run_id": run_id,
                }
            )

        by_id[segment_id] = _segment_entry(
            segment,
            chapter_id=chapter_id,
            chapter_number=chapter_number,
            position=position,
            run_id=run_id,
        )

    indices = sorted(
        parsed[1]
        for sid in by_id
        if (parsed := parse_segment_id(sid)) is not None
    )
    missing_segments: list[dict[str, Any]] = []
    if indices:
        expected = set(range(1, indices[-1] + 1))
        actual = set(indices)
        for missing_idx in sorted(expected - actual):
            missing_segments.append(
                {
                    "issue_type": "missing_segment",
                    "chapter_id": chapter_id,
                    "chapter_number": chapter_number,
                    "segment_index": missing_idx,
                    "expected_segment_id": expected_segment_id(chapter_number, missing_idx),
                    "source_run_id": run_id,
                }
            )

    return by_id, missing_segments, misalignments


def iter_chapter_scans(path: Path, *, run_id: str) -> Iterator[tuple[int, dict[str, Any]]]:
    """Stream chapters from one segments.json without retaining body text."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    for chapter in doc.get("chapters") or []:
        chapter_id = str(chapter.get("chapter_id") or "")
        chapter_number = chapter_number_from_id(chapter_id)
        if chapter_number is None:
            continue
        segments = list(chapter.get("segments") or [])
        by_id, missing, misalignments = _detect_chapter_issues(
            chapter_id,
            chapter_number,
            segments,
            run_id=run_id,
        )
        yield chapter_number, {
            "chapter_id": chapter_id,
            "chapter_number": chapter_number,
            "source_path": str(chapter.get("source_path") or ""),
            "segment_count": len(segments),
            "segments": by_id,
            "missing_segments": missing,
            "misalignments": misalignments,
        }


def scan_segments_file(path: Path, *, run_id: str) -> dict[int, dict[str, Any]]:
    """Extract per-chapter segment metadata from one segments.json (no text in output)."""
    return {num: bucket for num, bucket in iter_chapter_scans(path, run_id=run_id)}


def _normalize_chapter_bucket(raw: dict[Any, Any]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for key, value in raw.items():
        num = int(key) if not isinstance(key, int) else key
        out[num] = value
    return out


def _merge_chapter_buckets(
    buckets: list[tuple[str, dict[int, dict[str, Any]]]],
) -> dict[int, dict[str, Any]]:
    owner: dict[int, str] = {}
    for file_key, bucket in buckets:
        for num in bucket:
            owner[num] = file_key
    merged: dict[int, dict[str, Any]] = {}
    for file_key, bucket in buckets:
        for num, entry in bucket.items():
            if owner.get(num) == file_key:
                merged[num] = dict(entry)
    return merged


def _content_hash(segments: dict[str, dict[str, Any]]) -> str:
    parts = [
        f"{sid}:{meta.get('status')}:{meta.get('source_length')}:{meta.get('draft_length')}"
        for sid, meta in sorted(segments.items())
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def build_segment_index(
    repo_root: Path,
    *,
    previous_index: dict[str, Any] | None = None,
    run_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Build (incrementally) the segment index document."""
    prev_files: dict[str, Any] = (previous_index or {}).get("segment_files") or {}
    segments_paths = find_segments_files(repo_root, run_dirs)

    segment_files_section: dict[str, Any] = {}
    reused = 0
    scanned = 0
    draft_buckets: list[tuple[str, dict[int, dict[str, Any]]]] = []

    for path in segments_paths:
        key = str(path)
        fp = file_fingerprint(path)
        run_id = path.parent.name
        prev = prev_files.get(key)
        if prev and prev.get("fingerprint") == fp:
            bucket = _normalize_chapter_bucket(prev.get("chapters") or {})
            segment_files_section[key] = prev
            reused += 1
        else:
            bucket = scan_segments_file(path, run_id=run_id)
            segment_files_section[key] = {
                "fingerprint": fp,
                "run_id": run_id,
                "chapters": bucket,
            }
            scanned += 1
        draft_buckets.append((key, bucket))

    chapters_by_number = _merge_chapter_buckets(draft_buckets)

    segments: dict[str, dict[str, Any]] = {}
    chapters: dict[str, dict[str, Any]] = {}
    missing_segments: list[dict[str, Any]] = []
    misalignments: list[dict[str, Any]] = []

    for num in sorted(chapters_by_number):
        ch = chapters_by_number[num]
        chapter_id = str(ch.get("chapter_id") or f"ch-{num:03d}")
        ch_segments = dict(ch.get("segments") or {})
        ch_missing = list(ch.get("missing_segments") or [])
        ch_mis = list(ch.get("misalignments") or [])

        segments.update(ch_segments)
        missing_segments.extend(ch_missing)
        misalignments.extend(ch_mis)

        chapters[chapter_id] = {
            "chapter_id": chapter_id,
            "chapter_number": num,
            "source_path": ch.get("source_path") or "",
            "segment_count": int(ch.get("segment_count") or 0),
            "indexed_segment_count": len(ch_segments),
            "missing_segment_ids": [m["expected_segment_id"] for m in ch_missing],
            "misalignment_count": len(ch_mis),
            "content_hash": _content_hash(ch_segments),
        }

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "segment_files": segment_files_section,
        "stats": {
            "files_total": len(segment_files_section),
            "files_scanned": scanned,
            "files_reused": reused,
            "segments_indexed": len(segments),
            "chapters_covered": len(chapters),
            "missing_segments_count": len(missing_segments),
            "misalignment_count": len(misalignments),
            "clean": not missing_segments and not misalignments,
        },
        "segments": segments,
        "chapters": chapters,
        "issues": {
            "missing_segments": missing_segments,
            "misalignments": misalignments,
        },
    }


def index_summary(index: dict[str, Any]) -> dict[str, Any]:
    stats = index.get("stats") or {}
    return {
        "status": "PASS" if stats.get("clean") else "WARN",
        "segments_indexed": stats.get("segments_indexed"),
        "chapters_covered": stats.get("chapters_covered"),
        "missing_segments_count": stats.get("missing_segments_count"),
        "misalignment_count": stats.get("misalignment_count"),
        "files_scanned": stats.get("files_scanned"),
        "files_reused": stats.get("files_reused"),
        "clean": stats.get("clean"),
    }
