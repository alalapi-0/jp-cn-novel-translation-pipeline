"""Entity index builder (FS-033, Level 1).

Extracts glossary-backed entities (person / place / org / skill / item / title)
with source→target mapping frequencies, conflict markers (同源多译 / 同译多源),
and a top-N list of high-frequency unlisted source candidates.

Patterns follow FS-015 ``glossary.usage_index`` (streaming per file/chapter,
incremental fingerprint buckets, no body text in output). Rule + glossary
heuristics only — no model API.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from glossary.models import GlossaryEntry
from glossary.usage_index import (
    DIVERGENT_RATIO_THRESHOLD,
    MAX_SAMPLE_SEGMENT_IDS,
    MIN_SOURCE_HITS_FOR_CONFLICT,
    detect_conflicts,
)

SCHEMA_VERSION = 1
DEFAULT_TOP_N_UNLISTED = 50
MIN_UNLISTED_HITS = 2

ENTITY_CATEGORIES: tuple[str, ...] = (
    "person_name",
    "place_name",
    "organization_name",
    "skill_name",
    "item_name",
    "title",
)

_KATAKANA_RE = re.compile(r"[ァ-ヴー]{3,}(?:[・ァ-ヴー]{0,3})?(?:[一-龯]{0,2})?")
_BRACKET_RE = re.compile(r"【([^】]{1,32})】")
_CJK_CHUNK_RE = re.compile(r"[\u4e00-\u9fff]{2,6}")
_KANA_CHARS = set(chr(c) for c in range(0x3040, 0x30a0))


def _contains_standalone_term(term: str, text: str) -> bool:
    """Match a term against `text` with Japanese-kana boundary protection.

    Avoid noisy hits like ``レア`` inside ``レアスキル`` / ``レアアイテム`` by
    requiring surrounding chars not to be kana for kana-heavy terms.
    """
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


def _fingerprint(path: Path, *, source_bytes: bytes | None = None) -> str:
    from consistency.manifest import file_fingerprint
    return file_fingerprint(path,source_bytes=source_bytes)


def _chapter_num(chapter_id: str | None) -> int | None:
    if not chapter_id:
        return None
    digits = "".join(c for c in str(chapter_id) if c.isdigit())
    return int(digits) if digits else None


def _empty_entity_stats() -> dict[str, Any]:
    return {
        "source_hits": 0,
        "target_hits": 0,
        "co_hits": 0,
        "divergent": 0,
        "chapters": {},
        "divergent_segment_ids": [],
        "mappings": {},
    }


def filter_entity_terms(terms: list[GlossaryEntry]) -> list[GlossaryEntry]:
    return [
        t
        for t in terms
        if not t.deleted and t.category in ENTITY_CATEGORIES
    ]


def _known_source_terms(terms: list[GlossaryEntry]) -> set[str]:
    known: set[str] = set()
    for entry in terms:
        known.add(entry.source_term)
        for alias in entry.aliases or []:
            if alias:
                known.add(str(alias))
    return known


def _is_known_fragment(candidate: str, known: set[str]) -> bool:
    return any(candidate in term for term in known)


def _cjk_noun_chunks(draft_text: str) -> list[str]:
    chunks: list[str] = []
    for piece in re.split(r"[の的、。，！？\s「」『』【】/／]+", draft_text):
        piece = piece.strip()
        if 2 <= len(piece) <= 6 and _CJK_CHUNK_RE.fullmatch(piece):
            chunks.append(piece)
    if chunks:
        return chunks
    return [m.group(0) for m in _CJK_CHUNK_RE.finditer(draft_text)]


def infer_target_variant(
    source_text: str,
    draft_text: str,
    *,
    source_term: str,
    canonical_target: str,
) -> str:
    """Heuristic target guess when canonical translation is absent in draft."""
    if canonical_target and canonical_target in draft_text:
        return canonical_target
    bracketed_target = f"【{canonical_target}】"
    if canonical_target and bracketed_target in draft_text:
        return canonical_target
    bracket = _BRACKET_RE.search(source_text)
    if bracket:
        draft_brackets = _BRACKET_RE.findall(draft_text)
        if draft_brackets:
            return f"【{draft_brackets[0]}】"
    source_hit = _contains_standalone_term(source_term, source_text)
    if source_hit and _contains_standalone_term(source_term, draft_text):
        return source_term
    chunks = [
        chunk for chunk in _cjk_noun_chunks(draft_text)
        if chunk != canonical_target and len(chunk) >= 2
    ]
    if not chunks:
        return ""
    return max(chunks, key=len)


def _empty_chapter_stats() -> dict[str, Any]:
    return {
        "source_hits": 0,
        "target_hits": 0,
        "co_hits": 0,
        "divergent": 0,
        "mappings": {},
    }


def _record_mapping(
    stats: dict[str, Any],
    chapter_stats: dict[str, Any],
    target: str,
    *,
    kind: str,
) -> None:
    if not target:
        return
    for bucket in (stats["mappings"], chapter_stats["mappings"]):
        mapping = bucket.setdefault(target, {"count": 0, "kind": kind})
        mapping["count"] += 1
        if mapping["kind"] != "canonical" and kind == "canonical":
            mapping["kind"] = "canonical"


def scan_entity_file(
    path: Path,
    terms: list[GlossaryEntry],
    *,
    chapter_min: int | None = None,
    chapter_max: int | None = None,
    all_terms: list[GlossaryEntry] | None = None,
    source_bytes: bytes | None = None,
) -> dict[str, Any]:
    """Stream one segments.json; returns entity + unlisted buckets (no text)."""
    doc = json.loads(source_bytes if source_bytes is not None else path.read_bytes())
    chapters = doc.get("chapters") or []
    entity_bucket: dict[str, Any] = {}
    unlisted_bucket: dict[str, Any] = {}
    known = _known_source_terms(all_terms or terms)

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
                target_hit = False
                if bool(entry.target_term):
                    target_hit = _contains_standalone_term(entry.target_term, draft_text)
                    if not target_hit:
                        target_hit = (
                            f"【{entry.target_term}】" in draft_text
                            or f"《{entry.target_term}》" in draft_text
                        )
                tgt_hit = bool(entry.target_term) and target_hit
                if not src_hit and not tgt_hit:
                    continue
                stats = entity_bucket.setdefault(entry.source_term, _empty_entity_stats())
                stats["category"] = entry.category
                stats["canonical_target"] = entry.target_term
                ch = stats["chapters"].setdefault(chapter_id, _empty_chapter_stats())
                if src_hit:
                    stats["source_hits"] += 1
                    ch["source_hits"] += 1
                if tgt_hit:
                    stats["target_hits"] += 1
                    ch["target_hits"] += 1
                if src_hit and tgt_hit:
                    stats["co_hits"] += 1
                    ch["co_hits"] += 1
                    _record_mapping(stats, ch, entry.target_term, kind="canonical")
                if src_hit and not tgt_hit:
                    stats["divergent"] += 1
                    ch["divergent"] += 1
                    inferred = infer_target_variant(
                        source_text,
                        draft_text,
                        source_term=entry.source_term,
                        canonical_target=entry.target_term,
                    )
                    _record_mapping(stats, ch, inferred, kind="inferred")
                    if len(stats["divergent_segment_ids"]) < MAX_SAMPLE_SEGMENT_IDS:
                        stats["divergent_segment_ids"].append(segment_id)

            for candidate in _extract_unlisted_candidates(source_text):
                if candidate in known or _is_known_fragment(candidate, known):
                    continue
                ustats = unlisted_bucket.setdefault(
                    candidate,
                    {
                        "source_hits": 0,
                        "chapters": {},
                        "inferred_targets": {},
                        "sample_segment_ids": [],
                    },
                )
                ustats["source_hits"] += 1
                ustats["chapters"][chapter_id] = ustats["chapters"].get(chapter_id, 0) + 1
                chunks = _cjk_noun_chunks(draft_text)
                inferred = chunks[-1] if chunks else ""
                if inferred:
                    ustats["inferred_targets"][inferred] = (
                        ustats["inferred_targets"].get(inferred, 0) + 1
                    )
                if len(ustats["sample_segment_ids"]) < MAX_SAMPLE_SEGMENT_IDS:
                    ustats["sample_segment_ids"].append(segment_id)

    return {"entities": entity_bucket, "unlisted": unlisted_bucket}


def _extract_unlisted_candidates(source_text: str) -> set[str]:
    found: set[str] = set()
    for match in _KATAKANA_RE.findall(source_text):
        found.add(match)
    for inner in _BRACKET_RE.findall(source_text):
        label = inner.strip()
        if label:
            found.add(f"【{label}】")
    return found


def _merge_mapping_counts(target: dict[str, Any], source: dict[str, Any]) -> None:
    for tgt, mstats in (source or {}).items():
        entry = target.setdefault(tgt, {"count": 0, "kind": mstats.get("kind", "inferred")})
        entry["count"] += int(mstats.get("count") or 0)
        if mstats.get("kind") == "canonical":
            entry["kind"] = "canonical"


def _merge_entity_buckets(
    buckets: Iterable[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    """Merge per-file entity buckets; newest file wins per chapter."""
    owner: dict[str, str] = {}
    ordered = list(buckets)
    for file_key, bucket in ordered:
        for stats in bucket.values():
            for chapter_id in stats.get("chapters") or {}:
                owner[chapter_id] = file_key

    merged: dict[str, Any] = {}
    for file_key, bucket in ordered:
        for term, stats in bucket.items():
            target = merged.setdefault(term, _empty_entity_stats())
            for chapter_id, ch_stats in (stats.get("chapters") or {}).items():
                if owner.get(chapter_id) != file_key:
                    continue
                target["chapters"][chapter_id] = dict(ch_stats)
                _merge_mapping_counts(target["mappings"], ch_stats.get("mappings"))
            for seg_id in stats.get("divergent_segment_ids") or []:
                ch_prefix = "-".join(seg_id.split("-")[:2])
                if owner.get(ch_prefix, file_key) == file_key:
                    if len(target["divergent_segment_ids"]) < MAX_SAMPLE_SEGMENT_IDS:
                        target["divergent_segment_ids"].append(seg_id)

    for stats in merged.values():
        for key in ("source_hits", "target_hits", "co_hits", "divergent"):
            stats[key] = sum(ch[key] for ch in stats["chapters"].values())
    return merged


def _merge_unlisted_buckets(
    buckets: Iterable[tuple[str, dict[str, Any]]],
) -> dict[str, Any]:
    """Merge unlisted stats with newest-file-wins chapter ownership."""
    owner: dict[str, str] = {}
    ordered = list(buckets)
    for file_key, bucket in ordered:
        for stats in bucket.values():
            for chapter_id in stats.get("chapters") or {}:
                owner[chapter_id] = file_key

    merged: dict[str, Any] = {}
    for file_key, bucket in ordered:
        for term, stats in bucket.items():
            target = merged.setdefault(
                term,
                {
                    "source_hits": 0,
                    "chapters": {},
                    "inferred_targets": {},
                    "sample_segment_ids": [],
                },
            )
            owned_chapters: dict[str, int] = {}
            owned_targets: dict[str, int] = {}
            for chapter_id, count in (stats.get("chapters") or {}).items():
                if owner.get(chapter_id) == file_key:
                    owned_chapters[chapter_id] = count
            if not owned_chapters:
                continue
            for chapter_id, count in owned_chapters.items():
                target["chapters"][chapter_id] = (
                    target["chapters"].get(chapter_id, 0) + count
                )
            for tgt, count in (stats.get("inferred_targets") or {}).items():
                owned_targets[tgt] = owned_targets.get(tgt, 0) + count
            for tgt, count in owned_targets.items():
                target["inferred_targets"][tgt] = (
                    target["inferred_targets"].get(tgt, 0) + count
                )
            for seg_id in stats.get("sample_segment_ids") or []:
                ch_prefix = "-".join(seg_id.split("-")[:2])
                if owner.get(ch_prefix, file_key) == file_key:
                    if len(target["sample_segment_ids"]) < MAX_SAMPLE_SEGMENT_IDS:
                        if seg_id not in target["sample_segment_ids"]:
                            target["sample_segment_ids"].append(seg_id)

    for stats in merged.values():
        stats["source_hits"] = sum(stats["chapters"].values())
    return merged


def rank_unlisted_high_freq(
    unlisted: dict[str, Any],
    *,
    top_n: int = DEFAULT_TOP_N_UNLISTED,
    min_hits: int = MIN_UNLISTED_HITS,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for source_term, stats in unlisted.items():
        hits = int(stats.get("source_hits") or 0)
        if hits < min_hits:
            continue
        rows.append(
            {
                "source_term": source_term,
                "source_hits": hits,
                "chapters": sorted(stats.get("chapters") or {}),
                "inferred_targets": dict(
                    sorted(
                        (stats.get("inferred_targets") or {}).items(),
                        key=lambda kv: (-kv[1], kv[0]),
                    )
                ),
                "sample_segment_ids": list(stats.get("sample_segment_ids") or []),
            }
        )
    rows.sort(key=lambda r: (-r["source_hits"], r["source_term"]))
    return rows[:top_n]


def _file_term_dependencies(raw, terms, glossary_all, chapter_min, chapter_max):
    """Compute the exact term subset consulted for this file's observable scan.

    A new source/target hit or a known-fragment rule joins the digest, including
    absent->present transitions. Unrelated glossary edits leave the file reusable.
    """
    from translation.source_versions import value_sha
    doc=json.loads(raw);sources=[];targets=[]
    for ch in doc.get('chapters') or []:
        num=_chapter_num(str(ch.get('chapter_id') or ''))
        if chapter_min is not None and (num is None or num<chapter_min): continue
        if chapter_max is not None and (num is None or num>chapter_max): continue
        for row in ch.get('segments') or []:
            sources.append(row.get('source_text') or '');targets.append(row.get('draft_text') or '')
    candidates={c for text in sources for c in _extract_unlisted_candidates(text)}
    relevant=[term.to_dict() for term in terms if
        any(_contains_standalone_term(term.source_term,t) for t in sources) or
        (term.target_term and any(_contains_standalone_term(term.target_term,t)
         or f'【{term.target_term}】' in t or f'《{term.target_term}》' in t for t in targets))]
    known=_known_source_terms(glossary_all or terms)
    fragments=sorted(k for k in known if any(c==k or c in k for c in candidates))
    return value_sha({'algorithm':'entity-file-terms/3','terms':relevant,'known_fragments':fragments,
                      'chapter_filter':[chapter_min,chapter_max]})


def build_entity_index(
    terms: list[GlossaryEntry],
    segments_files: list[Path],
    *,
    previous_index: dict[str, Any] | None = None,
    chapter_min: int | None = None,
    chapter_max: int | None = None,
    top_n_unlisted: int = DEFAULT_TOP_N_UNLISTED,
    all_terms: list[GlossaryEntry] | None = None,
) -> dict[str, Any]:
    """Build (incrementally) the entity index document."""
    entity_terms = filter_entity_terms(terms)
    glossary_all = all_terms if all_terms is not None else terms
    from translation.source_versions import value_sha
    dependency_sha256=value_sha({'algorithm':'entity-index-content/2',
        'terms':[term.to_dict() for term in terms],'all_terms':[term.to_dict() for term in glossary_all]})

    prev_files: dict[str, Any] = (previous_index or {}).get("files") or {}
    prev_filter = (previous_index or {}).get("chapter_filter")
    current_filter = [chapter_min, chapter_max]

    files_section: dict[str, Any] = {}
    reused = 0
    scanned = 0
    ordered_paths = sorted(segments_files, key=lambda p: p.stat().st_mtime)

    entity_file_buckets: list[tuple[str, dict[str, Any]]] = []
    unlisted_file_buckets: list[tuple[str, dict[str, Any]]] = []

    for path in ordered_paths:
        key = str(path)
        raw=path.read_bytes();fp = _fingerprint(path,source_bytes=raw)
        local_dependency=_file_term_dependencies(raw,entity_terms,glossary_all,chapter_min,chapter_max)
        prev = prev_files.get(key)
        if (prev and prev.get("fingerprint") == fp and prev_filter == current_filter
                and prev.get('dependency_sha256')==local_dependency):
            files_section[key] = prev
            reused += 1
            entity_file_buckets.append((key, prev.get("entities") or {}))
            unlisted_file_buckets.append((key, prev.get("unlisted") or {}))
            continue
        scan = scan_entity_file(
            path,
            entity_terms,
            chapter_min=chapter_min,
            chapter_max=chapter_max,
            all_terms=glossary_all,
            source_bytes=raw,
        )
        files_section[key] = {
            "dependency_sha256": local_dependency,
            "fingerprint": fp,
            "entities": scan["entities"],
            "unlisted": scan["unlisted"],
        }
        scanned += 1
        entity_file_buckets.append((key, scan["entities"]))
        unlisted_file_buckets.append((key, scan["unlisted"]))

    merged_entities = _merge_entity_buckets(
        sorted(
            entity_file_buckets,
            key=lambda item: Path(item[0]).stat().st_mtime if Path(item[0]).exists() else 0,
        )
    )
    for entry in entity_terms:
        if entry.source_term in merged_entities:
            merged_entities[entry.source_term]["category"] = entry.category
            merged_entities[entry.source_term]["canonical_target"] = entry.target_term

    unlisted_merged = _merge_unlisted_buckets(
        sorted(
            unlisted_file_buckets,
            key=lambda item: Path(item[0]).stat().st_mtime if Path(item[0]).exists() else 0,
        )
    )
    unlisted_high_freq = rank_unlisted_high_freq(unlisted_merged, top_n=top_n_unlisted)

    conflicts = detect_conflicts(entity_terms, merged_entities)
    by_category: dict[str, list[str]] = {cat: [] for cat in ENTITY_CATEGORIES}
    for entry in entity_terms:
        if entry.source_term in merged_entities:
            by_category.setdefault(entry.category, []).append(entry.source_term)
    for cat in by_category:
        by_category[cat] = sorted(by_category[cat])

    chapters_covered = sorted(
        {ch for stats in merged_entities.values() for ch in stats.get("chapters") or {}}
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "chapter_filter": current_filter,
        "entity_categories": list(ENTITY_CATEGORIES),
        "dependency_sha256": dependency_sha256,
        "files": files_section,
        "stats": {
            "files_total": len(files_section),
            "files_scanned": scanned,
            "files_reused": reused,
            "entities_indexed": len(entity_terms),
            "entities_with_hits": len(merged_entities),
            "chapters_covered": len(chapters_covered),
            "conflict_count": len(conflicts),
            "unlisted_candidate_count": len(unlisted_merged),
            "unlisted_high_freq_count": len(unlisted_high_freq),
        },
        "by_category": by_category,
        "entities": merged_entities,
        "conflicts": conflicts,
        "unlisted_high_freq": unlisted_high_freq,
        "thresholds": {
            "divergent_ratio": DIVERGENT_RATIO_THRESHOLD,
            "min_source_hits": MIN_SOURCE_HITS_FOR_CONFLICT,
            "unlisted_min_hits": MIN_UNLISTED_HITS,
            "top_n_unlisted": top_n_unlisted,
        },
    }


def entity_index_digest(index: dict[str, Any]) -> str:
    """Identify semantic index content; this is not an authenticity signature."""
    payload = {key: value for key, value in index.items() if key != "generated_at"}
    if type(payload.get("stats")) is dict:
        payload["stats"] = {key: value for key, value in payload["stats"].items()
                            if key not in {"files_scanned", "files_reused"}}
    detached = json.loads(json.dumps(payload, ensure_ascii=False, allow_nan=False))
    raw = json.dumps(detached, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def index_summary(index: dict[str, Any]) -> dict[str, Any]:
    stats = index.get("stats") or {}
    return {
        "status": "PASS",
        "entities_indexed": stats.get("entities_indexed"),
        "entities_with_hits": stats.get("entities_with_hits"),
        "chapters_covered": stats.get("chapters_covered"),
        "conflict_count": stats.get("conflict_count"),
        "unlisted_high_freq_count": stats.get("unlisted_high_freq_count"),
        "files_scanned": stats.get("files_scanned"),
        "files_reused": stats.get("files_reused"),
    }
