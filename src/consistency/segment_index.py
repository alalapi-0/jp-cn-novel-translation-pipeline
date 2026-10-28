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

SCHEMA_VERSION = 4

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
    from translation.source_versions import validate_source_binding, review_dependencies, value_sha
    binding = segment.get('source_binding')
    if binding is not None: binding=validate_source_binding(binding,source_text)
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
        "source_sha256": hashlib.sha256(source_text.encode()).hexdigest(),
        "target_sha256": hashlib.sha256(draft_text.encode()).hexdigest(),
        "source_binding_sha256": binding['binding_sha256'] if binding else None,
        "dependency_sha256": value_sha(review_dependencies(segment,source_text)),
        "logical_id": binding['logical_id'] if binding else None,
        "source_revision": binding['source_revision'] if binding else None,
        "source_spans": binding['source_spans'] if binding else None,
        "source_binding_status": 'bound_metadata' if binding else 'legacy_unknown',
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
    ambiguous_ids: set[str] = set()

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
            ambiguous_ids.add(segment_id)
            by_id.pop(segment_id, None)
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

        if segment_id not in ambiguous_ids:
            by_id[segment_id] = _segment_entry(
                segment,
                chapter_id=chapter_id,
                chapter_number=chapter_number,
                position=position,
                run_id=run_id,
            )

    indices = sorted(
        parsed[1]
        for sid in seen_ids
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


def iter_chapter_scans(path: Path, *, run_id: str, source_bytes: bytes | None = None) -> Iterator[tuple[int | None, dict[str, Any]]]:
    """Stream chapters from one segments.json without retaining body text."""
    doc = json.loads(source_bytes if source_bytes is not None else path.read_bytes())
    input_chapters=doc.get('chapters')
    if input_chapters is None:input_chapters=[]
    if not isinstance(input_chapters,list):raise ValueError('chapter list required')
    if not input_chapters:
        yield None, {'issue_type':'no_chapters_in_file','chapter_id':'','chapter_number':None,
                     'source_run_id':run_id,'input_segment_count':0}
    for position, chapter in enumerate(input_chapters, start=1):
        if not isinstance(chapter,dict) or not isinstance(chapter.get('segments'),list):
            raise ValueError('chapter segment list required')
        chapter_id = str(chapter.get("chapter_id") or "")
        chapter_number = chapter_number_from_id(chapter_id)
        if chapter_number is None:
            # The unparseable value is untrusted input, not safe index metadata.
            yield None, {'issue_type':'unparseable_chapter_id','chapter_id':'',
                'chapter_number':None,'source_run_id':run_id,'position_in_input':position,
                'input_segment_count':len(chapter['segments'])}
            continue
        segments = list(chapter['segments'])
        by_id, missing, misalignments = _detect_chapter_issues(
            chapter_id,
            chapter_number,
            segments,
            run_id=run_id,
        )
        if not segments:
            misalignments.append({'issue_type':'empty_chapter','chapter_id':chapter_id,
                                  'chapter_number':chapter_number,'source_run_id':run_id})
        yield chapter_number, {
            "chapter_id": chapter_id,
            "chapter_number": chapter_number,
            "source_path": str(chapter.get("source_path") or ""),
            "segment_count": len(segments),
            "segments": by_id,
            "missing_segments": missing,
            "misalignments": misalignments,
        }


def scan_segments_file(path: Path, *, run_id: str, source_bytes: bytes | None = None,
                       unresolved_inputs: list[dict[str, Any]] | None = None) -> dict[int, dict[str, Any]]:
    """Extract per-chapter segment metadata from one segments.json (no text in output)."""
    buckets: dict[int, dict[str, Any]] = {}
    for num, entry in iter_chapter_scans(path, run_id=run_id,source_bytes=source_bytes):
        if num is None:
            if unresolved_inputs is None:
                raise ValueError('unresolved chapter input requires explicit issue collection')
            unresolved_inputs.append(entry)
            continue
        if num not in buckets:
            buckets[num]=entry
            continue
        previous=buckets[num]
        issue=next((row for row in previous['misalignments']
                    if row.get('issue_type')=='duplicate_chapter_number'),None)
        if issue is None:
            issue={'issue_type':'duplicate_chapter_number','chapter_id':previous['chapter_id'],
                   'chapter_number':num,'source_run_id':run_id,'occurrences':1,
                   'input_segment_count':previous['segment_count']}
            previous['misalignments'].append(issue)
        ambiguous=set(previous.get('ambiguous_segment_ids') or previous['segments'])
        ambiguous.update(entry['segments'])
        ambiguous.update(row['segment_id'] for bucket in (previous,entry)
                         for row in bucket['misalignments']
                         if row.get('issue_type')=='duplicate_segment_id' and row.get('segment_id'))
        previous['ambiguous_segment_ids']=sorted(ambiguous)
        previous['segments']={}
        previous['source_path']=''
        previous['segment_count']+=entry['segment_count']
        previous['missing_segments'].extend(entry['missing_segments'])
        previous['misalignments'].extend(entry['misalignments'])
        issue['occurrences']+=1
        issue['input_segment_count']=previous['segment_count']
    return buckets


def _normalize_chapter_bucket(raw: dict[Any, Any]) -> dict[int, dict[str, Any]]:
    out: dict[int, dict[str, Any]] = {}
    for key, value in raw.items():
        num = int(key) if not isinstance(key, int) else key
        out[num] = value
    return out


def _cache_digest(fingerprint: str, chapters: dict[int, dict[str, Any]],
                  unresolved: list[dict[str, Any]]) -> str:
    """Detect accidental cache drift; this is not an authenticity signature."""
    payload={'fingerprint':fingerprint,'chapters':{str(k):v for k,v in chapters.items()},
             'unresolved_inputs':unresolved}
    data=json.dumps(payload,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
    return hashlib.sha256(data.encode('utf-8')).hexdigest()


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
        f"{sid}:{meta.get('status')}:{meta.get('source_sha256')}:{meta.get('target_sha256')}:{meta.get('source_binding_sha256')}:{meta.get('dependency_sha256')}"
        for sid, meta in sorted(segments.items())
    ]
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:16]


def _selected_projection(
    draft_buckets: list[tuple[str, dict[int, dict[str, Any]]]],
    unresolved_inputs: list[dict[str, Any]],
) -> dict[str, Any]:
    """Derive the trusted top-level view from ordered, verified file buckets."""
    chapters_by_number = _merge_chapter_buckets(draft_buckets)

    segments: dict[str, dict[str, Any]] = {}
    chapters: dict[str, dict[str, Any]] = {}
    missing_segments: list[dict[str, Any]] = []
    misalignments: list[dict[str, Any]] = list(unresolved_inputs)
    if not draft_buckets:
        misalignments.append({'issue_type':'no_segment_files','chapter_id':'','source_run_id':''})
    ambiguous_ids = {sid for ch in chapters_by_number.values()
                     for sid in ch.get('ambiguous_segment_ids',[])}
    ambiguous_ids.update(row['segment_id'] for ch in chapters_by_number.values()
                         for row in ch.get('misalignments',[])
                         if row.get('issue_type')=='duplicate_segment_id' and row.get('segment_id'))
    cross_chapter_issues: dict[str, dict[str, Any]] = {}

    for num in sorted(chapters_by_number):
        ch = chapters_by_number[num]
        chapter_id = str(ch.get("chapter_id") or f"ch-{num:03d}")
        ch_segments = dict(ch.get("segments") or {})
        ch_missing = list(ch.get("missing_segments") or [])
        ch_mis = list(ch.get("misalignments") or [])

        for sid, meta in ch_segments.items():
            if sid in ambiguous_ids:
                if sid in cross_chapter_issues:
                    cross_chapter_issues[sid]['occurrences']+=1
                continue
            if sid in segments:
                first=segments.pop(sid)
                ambiguous_ids.add(sid)
                issue={'issue_type':'duplicate_segment_across_chapters','segment_id':sid,
                    'chapter_id':chapter_id,'chapter_number':num,'source_run_id':meta['source_run_id'],
                    'first_chapter_id':first['chapter_id'],'occurrences':2}
                ch_mis.append(issue);cross_chapter_issues[sid]=issue
            else:
                segments[sid]=meta
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

    selected_by_chapter: dict[str, dict[str, dict[str, Any]]] = {}
    for sid,meta in segments.items():
        selected_by_chapter.setdefault(meta['chapter_id'],{})[sid]=meta
    for chapter_id, chapter in chapters.items():
        selected=selected_by_chapter.get(chapter_id,{})
        chapter['indexed_segment_count']=len(selected)
        chapter['content_hash']=_content_hash(selected)

    return {
        "stats": {
            "segments_indexed": len(segments),
            "selected_input_segments": sum(ch['segment_count'] for ch in chapters.values()),
            "unresolved_input_segments": sum(row['input_segment_count'] for row in unresolved_inputs),
            "unparseable_chapters_count": sum(row['issue_type']=='unparseable_chapter_id' for row in unresolved_inputs),
            "chapters_covered": len(chapters),
            "missing_segments_count": len(missing_segments),
            "misalignment_count": len(misalignments),
            "clean": not missing_segments and not misalignments,
        },
        "segments": segments,
        "chapters": chapters,
        "issues": {"missing_segments": missing_segments, "misalignments": misalignments},
    }


def build_segment_index(
    repo_root: Path,
    *,
    previous_index: dict[str, Any] | None = None,
    run_dirs: list[Path] | None = None,
) -> dict[str, Any]:
    """Build (incrementally) the segment index document."""
    prior = previous_index if (previous_index or {}).get('schema_version')==SCHEMA_VERSION else {}
    prev_files: dict[str, Any] = (prior or {}).get("segment_files") or {}
    segments_paths = find_segments_files(repo_root, run_dirs)

    segment_files_section: dict[str, Any] = {}
    reused = 0
    scanned = 0
    draft_buckets: list[tuple[str, dict[int, dict[str, Any]]]] = []
    unresolved_inputs: list[dict[str, Any]] = []

    for path in segments_paths:
        key = str(path)
        raw=path.read_bytes()
        fp = file_fingerprint(path,source_bytes=raw)
        run_id = path.parent.name
        prev = prev_files.get(key)
        reusable=False
        if (isinstance(prev,dict) and prev.get('fingerprint')==fp
                and isinstance(prev.get('chapters'),dict) and isinstance(prev.get('unresolved_inputs'),list)):
            try:
                bucket=_normalize_chapter_bucket(prev['chapters'])
                unresolved=list(prev['unresolved_inputs'])
                reusable=prev.get('metadata_sha256')==_cache_digest(fp,bucket,unresolved)
            except (TypeError,ValueError,OverflowError):
                reusable=False
        if reusable:
            segment_files_section[key] = prev
            reused += 1
        else:
            unresolved = []
            bucket = scan_segments_file(path, run_id=run_id,source_bytes=raw,unresolved_inputs=unresolved)
            segment_files_section[key] = {
                "fingerprint": fp,
                "run_id": run_id,
                "chapters": bucket,
                "unresolved_inputs": unresolved,
                "metadata_sha256": _cache_digest(fp,bucket,unresolved),
            }
            scanned += 1
        draft_buckets.append((key, bucket))
        unresolved_inputs.extend(unresolved)

    projection=_selected_projection(draft_buckets,unresolved_inputs)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at": utc_now_iso(),
        "file_order": [key for key, _ in draft_buckets],
        "segment_files": segment_files_section,
        "stats": {"files_total":len(segment_files_section),"files_scanned":scanned,
                  "files_reused":reused,**projection['stats']},
        "segments":projection['segments'],"chapters":projection['chapters'],"issues":projection['issues'],
    }


def index_shape_consistent(index: dict[str, Any]) -> bool:
    """Check the ordered cached projection; this does not prove source freshness."""
    if type(index) is not dict or index.get('schema_version')!=SCHEMA_VERSION:
        return False
    stats=index.get('stats');files=index.get('segment_files');order=index.get('file_order')
    if (type(stats) is not dict or type(files) is not dict or type(order) is not list
            or any(type(key) is not str for key in order)
            or len(order)!=len(files) or len(set(order))!=len(order) or set(order)!=set(files)):
        return False
    if (type(stats.get('files_total')) is not int or stats['files_total']!=len(files)
            or any(type(stats.get(key)) is not int or stats[key]<0
                   for key in ('files_scanned','files_reused'))
            or stats['files_scanned']+stats['files_reused']!=len(files)):
        return False
    buckets=[];unresolved=[]
    try:
        for key in order:
            entry=files[key]
            if (type(entry) is not dict or type(entry.get('fingerprint')) is not str
                    or type(entry.get('chapters')) is not dict
                    or type(entry.get('unresolved_inputs')) is not list):
                return False
            bucket=_normalize_chapter_bucket(entry['chapters']);rows=entry['unresolved_inputs']
            if (len(bucket)!=len(entry['chapters'])
                    or entry.get('metadata_sha256')!=_cache_digest(entry['fingerprint'],bucket,rows)
                    or any(type(row) is not dict or type(row.get('input_segment_count')) is not int
                           or row['input_segment_count']<0 or type(row.get('issue_type')) is not str
                           for row in rows)):
                return False
            buckets.append((key,bucket));unresolved.extend(rows)
        expected=_selected_projection(buckets,unresolved)
    except (AttributeError,IndexError,KeyError,OverflowError,TypeError,ValueError):
        return False
    return (all(type(index.get(key)) is dict and index[key]==expected[key]
                for key in ('segments','chapters','issues'))
            and all(type(stats.get(key)) is type(value) and stats[key]==value
                    for key,value in expected['stats'].items()))


def segment_index_digest(index: dict[str, Any]) -> str:
    """Bind semantic index content without volatile generation or cache counters."""
    payload={key:index.get(key) for key in ('schema_version','file_order','segment_files','segments','chapters','issues')}
    detached=json.loads(json.dumps(payload,ensure_ascii=False,allow_nan=False))
    raw=json.dumps(detached,ensure_ascii=False,sort_keys=True,separators=(',',':'),allow_nan=False)
    return hashlib.sha256(raw.encode('utf-8')).hexdigest()


def index_summary(index: dict[str, Any]) -> dict[str, Any]:
    if type(index) is not dict:index={}
    stats = index.get('stats') if type(index.get('stats')) is dict else {}
    schema_current = type(index.get('schema_version')) is int and index['schema_version']==SCHEMA_VERSION
    shape_consistent=index_shape_consistent(index)
    clean = shape_consistent and stats.get('clean') is True
    return {
        "status": "PASS" if clean else "WARN",
        "schema_current": schema_current,
        "shape_consistent": shape_consistent,
        "source_freshness_status": "UNVERIFIED",
        "segments_indexed": stats.get("segments_indexed"),
        "selected_input_segments": stats.get("selected_input_segments"),
        "unresolved_input_segments": stats.get("unresolved_input_segments"),
        "unparseable_chapters_count": stats.get("unparseable_chapters_count"),
        "chapters_covered": stats.get("chapters_covered"),
        "missing_segments_count": stats.get("missing_segments_count"),
        "misalignment_count": stats.get("misalignment_count"),
        "files_scanned": stats.get("files_scanned"),
        "files_reused": stats.get("files_reused"),
        "clean": clean,
    }
