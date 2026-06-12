"""Chapter manifest builder (FS-031, Level 0).

Builds a metadata-only index of numbered source chapters and their draft
coverage. Never writes source_text or draft_text into the manifest document.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from translation.chapter_parser import (
    _CHAPTER_FILE_NUM_RE,
    chapter_id_from_path,
    chapter_numbers_in_input_dir,
    count_source_chapters,
)
from translation.run_progress import safe_load_json

SCHEMA_VERSION = 1

_CHAPTER_NUM_RE = re.compile(r"(\d+)")

_DIAGNOSTIC_PREFIXES = (
    "draft-a-",
    "micro_validate",
    "fixture_",
    "asset-context",
    "round_50_e2e",
)

_DEFAULT_RUN_DIRS = ("workspace/runs", "workspace/archived_runs")
_INPUT_DIRS = ("input_jp", "input_zh")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def file_fingerprint(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_size}:{int(stat.st_mtime)}"


def chapter_number_from_id(chapter_id: str | None) -> int | None:
    if not chapter_id:
        return None
    match = _CHAPTER_NUM_RE.search(str(chapter_id))
    return int(match.group(1)) if match else None


def _is_diagnostic_run(run_id: str) -> bool:
    return any(run_id.startswith(prefix) for prefix in _DIAGNOSTIC_PREFIXES)


def _run_fully_completed(run_root: Path) -> bool:
    progress = safe_load_json(run_root / "run_progress.json")
    if progress is not None:
        total = int(progress.get("total_segments") or 0)
        completed = int(progress.get("completed_segments") or 0)
        return total > 0 and completed >= total
    meta = safe_load_json(run_root / "run_metadata.json") or {}
    summary = meta.get("summary") or {}
    if summary.get("aborted"):
        return False
    total = int(summary.get("total_segments") or 0)
    translated = int(summary.get("translated_segments") or 0)
    return total > 0 and translated >= total


def read_source_title(path: Path, *, max_header_lines: int = 30) -> str:
    """Read markdown headers only; never returns body paragraphs."""
    title = ""
    subtitle = ""
    for idx, line in enumerate(path.read_text(encoding="utf-8").splitlines()):
        if idx >= max_header_lines:
            break
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        elif line.startswith("## ") and not subtitle:
            subtitle = line[3:].strip()
        elif line.strip() and not line.startswith("#"):
            break
    return f"{title} / {subtitle}".strip(" /") or path.stem


def discover_source_files(repo_root: Path) -> dict[int, list[dict[str, Any]]]:
    """Map chapter number -> source file records (duplicate numbers explicit)."""
    by_number: dict[int, list[dict[str, Any]]] = {}
    for dirname in _INPUT_DIRS:
        input_dir = repo_root / dirname
        if not input_dir.is_dir():
            continue
        for path in sorted(input_dir.iterdir()):
            if not path.is_file() or path.suffix.lower() not in (".md", ".txt"):
                continue
            if path.name == "README.md":
                continue
            match = _CHAPTER_FILE_NUM_RE.match(path.name)
            if not match:
                continue
            num = int(match.group(1))
            rel = f"{dirname}/{path.name}"
            entry = {
                "chapter_number": num,
                "chapter_id": chapter_id_from_path(path),
                "source_path": rel,
                "source_fingerprint": file_fingerprint(path),
                "title": read_source_title(path),
            }
            by_number.setdefault(num, []).append(entry)
    return by_number


def _segment_metadata_hash(segments: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for seg in segments:
        sid = str(seg.get("segment_id") or "")
        status = str(seg.get("status") or "")
        has_draft = bool((seg.get("draft_text") or "").strip())
        parts.append(f"{sid}:{status}:{int(has_draft)}")
    payload = "|".join(parts)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _draft_status_from_segments(segments: list[dict[str, Any]]) -> tuple[str, int, int]:
    if not segments:
        return "missing", 0, 0
    with_draft = 0
    completed = 0
    for seg in segments:
        if (seg.get("draft_text") or "").strip():
            with_draft += 1
        status = str(seg.get("status") or "")
        if status in {"completed", "machine_translated", "translated"}:
            completed += 1
    total = len(segments)
    if with_draft >= total and completed >= total:
        return "complete", completed, with_draft
    if with_draft > 0 or completed > 0:
        return "partial", completed, with_draft
    return "missing", completed, with_draft


def scan_segments_file(path: Path, *, run_id: str) -> dict[int, dict[str, Any]]:
    """Extract per-chapter draft metadata from one segments.json (no text in output)."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    out: dict[int, dict[str, Any]] = {}
    for chapter in doc.get("chapters") or []:
        chapter_id = str(chapter.get("chapter_id") or "")
        num = chapter_number_from_id(chapter_id)
        if num is None:
            continue
        segments = list(chapter.get("segments") or [])
        draft_status, completed, with_draft = _draft_status_from_segments(segments)
        out[num] = {
            "chapter_id": chapter_id,
            "title": str(chapter.get("chapter_label") or chapter_id),
            "source_path": str(chapter.get("source_path") or ""),
            "segment_count": len(segments),
            "paragraph_count": len(segments),
            "segments_completed": completed,
            "segments_with_draft": with_draft,
            "draft_status": draft_status,
            "source_run_id": run_id,
            "segments_fingerprint": _segment_metadata_hash(segments),
            "segments_file": str(path),
        }
    return out


def find_segments_files(repo_root: Path, run_dirs: list[Path] | None = None) -> list[Path]:
    paths: list[Path] = []
    dirs = run_dirs or [repo_root / rel for rel in _DEFAULT_RUN_DIRS]
    for run_dir in dirs:
        if not run_dir.is_dir():
            continue
        for run_root in sorted(run_dir.iterdir()):
            if not run_root.is_dir() or _is_diagnostic_run(run_root.name):
                continue
            meta = safe_load_json(run_root / "run_metadata.json") or {}
            if str(meta.get("phase") or "") != "draft":
                continue
            if not _run_fully_completed(run_root):
                continue
            seg_path = run_root / "segments.json"
            if seg_path.is_file():
                paths.append(seg_path)
    return sorted(paths, key=lambda p: p.stat().st_mtime)


def _pick_canonical_source(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return sorted(entries, key=lambda e: e["source_path"])[0]


def _normalize_chapter_bucket(raw: dict[Any, Any]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for key, value in raw.items():
        num = int(key) if not isinstance(key, int) else key
        out[num] = value
    return out


def _merge_draft_buckets(
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


def _coverage_issues(
    total_expected: int,
    source_by_number: dict[int, list[dict[str, Any]]],
    draft_by_number: dict[int, dict[str, Any]],
) -> dict[str, Any]:
    source_numbers = set(source_by_number)
    expected = set(range(1, total_expected + 1))
    missing_source = sorted(expected - source_numbers)
    extra_source = sorted(n for n in source_numbers if n < 1 or n > total_expected)
    duplicate_source = sorted(n for n, entries in source_by_number.items() if len(entries) > 1)
    duplicate_details = {
        str(n): [e["source_path"] for e in source_by_number[n]] for n in duplicate_source
    }
    missing_draft = sorted(n for n in expected if n in source_numbers and n not in draft_by_number)
    gaps_in_source = []
    if source_numbers:
        lo, hi = min(source_numbers), max(source_numbers)
        gaps_in_source = sorted(n for n in range(lo, hi + 1) if n not in source_numbers)
    return {
        "total_expected": total_expected,
        "source_chapters_found": len(source_numbers),
        "draft_chapters_found": len(draft_by_number),
        "missing_source_chapters": missing_source,
        "missing_draft_chapters": missing_draft,
        "extra_source_chapters": extra_source,
        "duplicate_source_chapters": duplicate_source,
        "duplicate_source_details": duplicate_details,
        "gaps_in_source_sequence": gaps_in_source,
        "full_coverage": not missing_source and not duplicate_source and not missing_draft,
    }


def build_chapter_manifest(
    repo_root: Path,
    *,
    previous_index: dict[str, Any] | None = None,
    total_expected: int | None = None,
    run_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Build (incrementally) the chapter manifest document."""
    if total_expected is not None:
        total = total_expected
    else:
        total = count_source_chapters(repo_root)
        if total <= 0:
            nums = chapter_numbers_in_input_dir(repo_root / "input_jp")
            total = max(nums) if nums else 0

    prev_files: dict[str, Any] = (previous_index or {}).get("segment_files") or {}
    source_by_number = discover_source_files(repo_root)

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

    draft_by_number = _merge_draft_buckets(draft_buckets)

    chapters: dict[str, Any] = {}
    for num in sorted(set(source_by_number) | set(draft_by_number)):
        source_entries = source_by_number.get(num, [])
        source = _pick_canonical_source(source_entries) if source_entries else None
        draft = draft_by_number.get(num)
        chapter_id = (
            (draft or {}).get("chapter_id")
            or (source or {}).get("chapter_id")
            or f"ch-{num}"
        )
        title = (draft or {}).get("title") or (source or {}).get("title") or chapter_id
        source_path = (draft or {}).get("source_path") or (source or {}).get("source_path") or ""
        segment_count = int((draft or {}).get("segment_count") or 0)
        paragraph_count = segment_count
        draft_status = (draft or {}).get("draft_status") or "missing"
        entry: dict[str, Any] = {
            "chapter_number": num,
            "chapter_id": chapter_id,
            "title": title,
            "source_path": source_path,
            "paragraph_count": paragraph_count,
            "segment_count": segment_count,
            "draft_status": draft_status,
            "segments_completed": int((draft or {}).get("segments_completed") or 0),
            "segments_with_draft": int((draft or {}).get("segments_with_draft") or 0),
            "source_run_id": (draft or {}).get("source_run_id") or "",
            "source_fingerprint": (source or {}).get("source_fingerprint") or "",
            "segments_fingerprint": (draft or {}).get("segments_fingerprint") or "",
            "content_hash": "",
            "duplicate_source_paths": (
                [e["source_path"] for e in source_entries] if len(source_entries) > 1 else []
            ),
        }
        entry["content_hash"] = hashlib.sha256(
            json.dumps(
                {
                    "chapter_id": entry["chapter_id"],
                    "source_path": entry["source_path"],
                    "source_fingerprint": entry["source_fingerprint"],
                    "segments_fingerprint": entry["segments_fingerprint"],
                    "draft_status": entry["draft_status"],
                    "segment_count": entry["segment_count"],
                    "source_run_id": entry["source_run_id"],
                },
                sort_keys=True,
                ensure_ascii=False,
            ).encode("utf-8")
        ).hexdigest()[:16]
        chapters[chapter_id] = entry

    coverage = _coverage_issues(total, source_by_number, draft_by_number)

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "total_expected_chapters": total,
        "segment_files": segment_files_section,
        "stats": {
            "segment_files_total": len(segment_files_section),
            "segment_files_scanned": scanned,
            "segment_files_reused": reused,
            "chapters_indexed": len(chapters),
            **coverage,
        },
        "chapters": chapters,
    }


def manifest_summary(manifest: dict[str, Any]) -> dict[str, Any]:
    stats = manifest.get("stats") or {}
    return {
        "status": "PASS" if stats.get("full_coverage") else "WARN",
        "total_expected_chapters": manifest.get("total_expected_chapters"),
        "chapters_indexed": stats.get("chapters_indexed"),
        "full_coverage": stats.get("full_coverage"),
        "missing_source_chapters": stats.get("missing_source_chapters"),
        "missing_draft_chapters": stats.get("missing_draft_chapters"),
        "duplicate_source_chapters": stats.get("duplicate_source_chapters"),
        "segment_files_scanned": stats.get("segment_files_scanned"),
        "segment_files_reused": stats.get("segment_files_reused"),
    }
