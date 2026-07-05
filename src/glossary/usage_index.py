"""Term usage index over draft runs (FS-015).

Builds, per glossary term, hit statistics across chapters/segments:
- source_hits: segments whose source_text contains source_term;
- target_hits: segments whose draft_text contains target_term;
- co_hits:     segments hitting both;
- divergent:   segments hitting source but NOT target (signal for
               "same source, different translation").

Conflict marking:
- divergent_translation: divergent/source ratio >= threshold (同源多译);
- shared_target: multiple glossary source terms share one target (同译多源).

Constraints honored:
- streaming: files processed one by one, chapters one by one - the full book
  is never concatenated into a single context;
- outputs carry only segment_ids and counts, never source/draft text;
- incremental: per-file buckets keyed by (size, mtime) fingerprint; unchanged
  files are reused from the previous index document.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from .models import GlossaryEntry

SCHEMA_VERSION = 1
DIVERGENT_RATIO_THRESHOLD = 0.3
MIN_SOURCE_HITS_FOR_CONFLICT = 2
MAX_SAMPLE_SEGMENT_IDS = 20
_KANA_CHARS = set(chr(c) for c in range(0x3040, 0x30a0))


def _contains_standalone_term(term: str, text: str) -> bool:
    """Match with kana-boundary protection for katakana-heavy terms."""
    if not term:
        return False
    if not any(ch in _KANA_CHARS for ch in term):
        return term in text
    start = 0
    while True:
        idx = text.find(term, start)
        if idx == -1:
            return False
        before = text[idx - 1] if idx > 0 else ""
        after = text[idx + len(term)] if idx + len(term) < len(text) else ""
        if before not in _KANA_CHARS and after not in _KANA_CHARS:
            return True
        start = idx + len(term)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _fingerprint(path: Path) -> str:
    stat = path.stat()
    return f"{stat.st_size}:{int(stat.st_mtime)}"


def _chapter_num(chapter_id: str | None) -> int | None:
    """Extract a numeric chapter from ids like 'ch-260' / 'ch-007'."""
    if not chapter_id:
        return None
    digits = "".join(c for c in str(chapter_id) if c.isdigit())
    return int(digits) if digits else None


def _empty_term_stats() -> dict[str, Any]:
    return {
        "source_hits": 0,
        "target_hits": 0,
        "co_hits": 0,
        "divergent": 0,
        "chapters": {},
        "divergent_segment_ids": [],
    }


def scan_segments_file(
    path: Path,
    terms: list[GlossaryEntry],
    *,
    chapter_min: int | None = None,
    chapter_max: int | None = None,
) -> dict[str, Any]:
    """Stream one segments.json; returns {term_key: stats} for hit terms only."""
    doc = json.loads(path.read_text(encoding="utf-8"))
    chapters = doc.get("chapters") or []
    bucket: dict[str, Any] = {}
    for chapter in chapters:
        chapter_id = str(chapter.get("chapter_id") or "")
        num = _chapter_num(chapter_id)
        if chapter_min is not None and (num is None or num < chapter_min):
            continue
        if chapter_max is not None and (num is None or num > chapter_max):
            continue
        for segment in chapter.get("segments") or []:
            source_text = segment.get("source_text") or ""
            draft_text = segment.get("draft_text") or ""
            segment_id = str(segment.get("segment_id") or "")
            for entry in terms:
                src_hit = _contains_standalone_term(entry.source_term, source_text)
                tgt_hit = False
                if bool(entry.target_term):
                    tgt_hit = _contains_standalone_term(entry.target_term, draft_text)
                    if not tgt_hit:
                        tgt_hit = (
                            f"【{entry.target_term}】" in draft_text
                            or f"《{entry.target_term}》" in draft_text
                        )
                if not src_hit and not tgt_hit:
                    continue
                stats = bucket.setdefault(entry.source_term, _empty_term_stats())
                ch = stats["chapters"].setdefault(
                    chapter_id,
                    {"source_hits": 0, "target_hits": 0, "co_hits": 0, "divergent": 0},
                )
                if src_hit:
                    stats["source_hits"] += 1
                    ch["source_hits"] += 1
                if tgt_hit:
                    stats["target_hits"] += 1
                    ch["target_hits"] += 1
                if src_hit and tgt_hit:
                    stats["co_hits"] += 1
                    ch["co_hits"] += 1
                if src_hit and not tgt_hit:
                    stats["divergent"] += 1
                    ch["divergent"] += 1
                    if len(stats["divergent_segment_ids"]) < MAX_SAMPLE_SEGMENT_IDS:
                        stats["divergent_segment_ids"].append(segment_id)
    return bucket


def _merge_buckets(buckets: Iterable[tuple[str, dict[str, Any]]]) -> dict[str, Any]:
    """Merge per-file buckets; duplicate chapters resolved newest-file-first.

    buckets must be ordered oldest -> newest; a chapter claimed by a newer
    file replaces the older file's contribution for that chapter (re-runs of
    the same window supersede archived attempts).
    """
    # chapter ownership: chapter_id -> file_key (newest wins)
    owner: dict[str, str] = {}
    ordered = list(buckets)
    for file_key, bucket in ordered:
        for stats in bucket.values():
            for chapter_id in stats["chapters"]:
                owner[chapter_id] = file_key

    merged: dict[str, Any] = {}
    for file_key, bucket in ordered:
        for term, stats in bucket.items():
            target = merged.setdefault(term, _empty_term_stats())
            for chapter_id, ch_stats in stats["chapters"].items():
                if owner.get(chapter_id) != file_key:
                    continue  # superseded by a newer file
                target["chapters"][chapter_id] = dict(ch_stats)
            # sample ids are advisory; keep newest-file ones when owned
            for seg_id in stats["divergent_segment_ids"]:
                ch_prefix = "-".join(seg_id.split("-")[:2])  # "ch-260"
                if owner.get(ch_prefix, file_key) == file_key:
                    if len(target["divergent_segment_ids"]) < MAX_SAMPLE_SEGMENT_IDS:
                        target["divergent_segment_ids"].append(seg_id)
    # recompute totals from owned chapters
    for stats in merged.values():
        for key in ("source_hits", "target_hits", "co_hits", "divergent"):
            stats[key] = sum(ch[key] for ch in stats["chapters"].values())
    return merged


def detect_conflicts(
    terms: list[GlossaryEntry],
    merged: dict[str, Any],
    *,
    divergent_ratio_threshold: float = DIVERGENT_RATIO_THRESHOLD,
    min_source_hits: int = MIN_SOURCE_HITS_FOR_CONFLICT,
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []

    # 同源多译: high divergent ratio for a term with a defined target
    for entry in terms:
        stats = merged.get(entry.source_term)
        if not stats or not entry.target_term:
            continue
        src = stats["source_hits"]
        if src >= min_source_hits:
            ratio = stats["divergent"] / src
            if ratio >= divergent_ratio_threshold:
                conflicts.append(
                    {
                        "kind": "divergent_translation",
                        "source_term": entry.source_term,
                        "target_term": entry.target_term,
                        "source_hits": src,
                        "divergent": stats["divergent"],
                        "ratio": round(ratio, 3),
                        "sample_segment_ids": list(stats["divergent_segment_ids"]),
                    }
                )

    # 同译多源: one target shared by multiple source terms
    by_target: dict[str, list[str]] = {}
    for entry in terms:
        if entry.target_term:
            by_target.setdefault(entry.target_term, []).append(entry.source_term)
    for target, sources in sorted(by_target.items()):
        if len(sources) > 1:
            conflicts.append(
                {
                    "kind": "shared_target",
                    "target_term": target,
                    "source_terms": sorted(sources),
                }
            )
    return conflicts


def build_usage_index(
    terms: list[GlossaryEntry],
    segments_files: list[Path],
    *,
    previous_index: dict[str, Any] | None = None,
    chapter_min: int | None = None,
    chapter_max: int | None = None,
) -> dict[str, Any]:
    """Build (incrementally) the usage index document.

    previous_index: prior document; files whose fingerprint and chapter
    filter match are reused without re-scanning.
    """
    prev_files: dict[str, Any] = (previous_index or {}).get("files") or {}
    prev_filter = (previous_index or {}).get("chapter_filter")
    current_filter = [chapter_min, chapter_max]

    files_section: dict[str, Any] = {}
    reused = 0
    scanned = 0
    ordered_paths = sorted(segments_files, key=lambda p: p.stat().st_mtime)
    for path in ordered_paths:
        key = str(path)
        fp = _fingerprint(path)
        prev = prev_files.get(key)
        if prev and prev.get("fingerprint") == fp and prev_filter == current_filter:
            files_section[key] = prev
            reused += 1
            continue
        bucket = scan_segments_file(
            path, terms, chapter_min=chapter_min, chapter_max=chapter_max
        )
        files_section[key] = {"fingerprint": fp, "terms": bucket}
        scanned += 1

    merged = _merge_buckets(
        (key, files_section[key]["terms"]) for key in sorted(
            files_section, key=lambda k: Path(k).stat().st_mtime if Path(k).exists() else 0
        )
    )
    conflicts = detect_conflicts(terms, merged)

    chapters_covered = sorted(
        {ch for stats in merged.values() for ch in stats["chapters"]}
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "chapter_filter": current_filter,
        "files": files_section,
        "stats": {
            "files_total": len(files_section),
            "files_scanned": scanned,
            "files_reused": reused,
            "terms_indexed": len(terms),
            "terms_with_hits": len(merged),
            "chapters_covered": len(chapters_covered),
            "conflict_count": len(conflicts),
        },
        "terms": merged,
        "conflicts": conflicts,
    }
