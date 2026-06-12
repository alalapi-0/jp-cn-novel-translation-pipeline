"""Baseline vs refined segment diff and structured change_log (FS-042)."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from difflib import SequenceMatcher, unified_diff
from pathlib import Path
from statistics import median
from typing import Any

SCHEMA_VERSION = "1.0"
RATIO_PRECISION = 6

MODIFICATION_UNCHANGED = "unchanged"
MODIFICATION_PUNCTUATION = "punctuation_only"
MODIFICATION_MINOR_WORDING = "minor_wording"
MODIFICATION_SUBSTANTIAL = "substantial_edit"
MODIFICATION_LENGTH_EXPANSION = "length_expansion"
MODIFICATION_LENGTH_REDUCTION = "length_reduction"
MODIFICATION_SKIPPED_HUMAN = "skipped_human_edited"
MODIFICATION_PENDING = "pending_refine"

ALL_MODIFICATION_TYPES = (
    MODIFICATION_UNCHANGED,
    MODIFICATION_PUNCTUATION,
    MODIFICATION_MINOR_WORDING,
    MODIFICATION_SUBSTANTIAL,
    MODIFICATION_LENGTH_EXPANSION,
    MODIFICATION_LENGTH_REDUCTION,
    MODIFICATION_SKIPPED_HUMAN,
    MODIFICATION_PENDING,
)

_LENGTH_EXPANSION_THRESHOLD = 1.15
_LENGTH_REDUCTION_THRESHOLD = 0.85
_MINOR_WORDING_SIMILARITY = 0.85
_PUNCT_ONLY_SIMILARITY = 0.99

_WHITESPACE_RE = re.compile(r"\s+")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _round_ratio(value: float) -> float:
    return round(value, RATIO_PRECISION)


def _content_fingerprint(baseline: str, refined: str) -> str:
    payload = f"{baseline}\x1e{refined}".encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _strip_punctuation_and_space(text: str) -> str:
    out: list[str] = []
    for ch in text:
        if ch.isspace():
            continue
        cat = unicodedata.category(ch)
        if cat.startswith("P") or cat.startswith("S"):
            continue
        out.append(ch)
    return "".join(out)


def _similarity(baseline: str, refined: str) -> float:
    if baseline == refined:
        return 1.0
    if not baseline and not refined:
        return 1.0
    return SequenceMatcher(None, baseline, refined).ratio()


def classify_modification(
    *,
    baseline: str,
    refined: str,
    human_edited: bool = False,
    has_refined: bool = True,
) -> str:
    """Return per-segment modification category."""
    if human_edited and not has_refined:
        return MODIFICATION_SKIPPED_HUMAN
    if not has_refined:
        return MODIFICATION_PENDING
    if baseline == refined:
        return MODIFICATION_UNCHANGED

    similarity = _similarity(baseline, refined)
    if _strip_punctuation_and_space(baseline) == _strip_punctuation_and_space(refined):
        return MODIFICATION_PUNCTUATION
    if similarity >= _PUNCT_ONLY_SIMILARITY and _WHITESPACE_RE.sub("", baseline) == _WHITESPACE_RE.sub(
        "", refined
    ):
        return MODIFICATION_PUNCTUATION

    draft_len = len(baseline)
    refined_len = len(refined)
    length_ratio = (refined_len / draft_len) if draft_len else 0.0

    if length_ratio >= _LENGTH_EXPANSION_THRESHOLD and similarity < _MINOR_WORDING_SIMILARITY:
        return MODIFICATION_LENGTH_EXPANSION
    if length_ratio <= _LENGTH_REDUCTION_THRESHOLD and similarity < _MINOR_WORDING_SIMILARITY:
        return MODIFICATION_LENGTH_REDUCTION
    if similarity >= _MINOR_WORDING_SIMILARITY:
        return MODIFICATION_MINOR_WORDING
    return MODIFICATION_SUBSTANTIAL


def compute_segment_metrics(
    *,
    baseline: str,
    refined: str,
    human_edited: bool = False,
    has_refined: bool = True,
) -> dict[str, Any]:
    """Compute reproducible diff metrics for one segment."""
    baseline = baseline or ""
    refined = refined or ""
    modification_type = classify_modification(
        baseline=baseline,
        refined=refined,
        human_edited=human_edited,
        has_refined=has_refined,
    )
    similarity = _similarity(baseline, refined) if has_refined else 0.0
    diff_ratio = _round_ratio(max(0.0, 1.0 - similarity)) if has_refined else 0.0
    draft_len = len(baseline)
    refined_len = len(refined) if has_refined else 0
    length_ratio: float | None
    if draft_len and has_refined:
        length_ratio = _round_ratio(refined_len / draft_len)
    else:
        length_ratio = None

    return {
        "modification_type": modification_type,
        "similarity_ratio": _round_ratio(similarity),
        "diff_ratio": diff_ratio,
        "length_ratio": length_ratio,
        "draft_char_count": draft_len,
        "refined_char_count": refined_len,
        "char_delta": refined_len - draft_len if has_refined else 0,
        "changed": modification_type
        not in {MODIFICATION_UNCHANGED, MODIFICATION_SKIPPED_HUMAN, MODIFICATION_PENDING},
        "content_fingerprint": _content_fingerprint(baseline, refined if has_refined else ""),
    }


def _unified_diff_lines(baseline: str, refined: str, segment_id: str) -> list[str]:
    return list(
        unified_diff(
            baseline.splitlines(keepends=True),
            refined.splitlines(keepends=True),
            fromfile=f"{segment_id}:baseline",
            tofile=f"{segment_id}:refined",
            lineterm="",
        )
    )


def iter_segment_records(doc: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for chapter in doc.get("chapters", []):
        chapter_id = str(chapter.get("chapter_id") or "")
        for seg in chapter.get("segments", []):
            baseline = (seg.get("draft_text") or "").strip()
            refined = (seg.get("refined_text") or "").strip()
            human_edited = bool(seg.get("human_edited"))
            has_refined = bool(refined)
            metrics = compute_segment_metrics(
                baseline=baseline,
                refined=refined,
                human_edited=human_edited,
                has_refined=has_refined,
            )
            records.append(
                {
                    "segment_id": str(seg.get("segment_id") or ""),
                    "chapter_id": chapter_id,
                    "human_edited": human_edited,
                    "baseline_text": baseline,
                    "refined_text": refined if has_refined else "",
                    **metrics,
                }
            )
    return records


def _aggregate_stats(records: list[dict[str, Any]]) -> dict[str, Any]:
    category_counts = {key: 0 for key in ALL_MODIFICATION_TYPES}
    diff_ratios: list[float] = []
    changed = 0
    refined_count = 0

    for rec in records:
        mod_type = rec["modification_type"]
        category_counts[mod_type] = category_counts.get(mod_type, 0) + 1
        if rec["modification_type"] == MODIFICATION_PENDING:
            continue
        if rec["modification_type"] == MODIFICATION_SKIPPED_HUMAN:
            continue
        refined_count += 1
        diff_ratios.append(float(rec["diff_ratio"]))
        if rec["changed"]:
            changed += 1

    avg_diff = _round_ratio(sum(diff_ratios) / len(diff_ratios)) if diff_ratios else 0.0
    med_diff = _round_ratio(median(diff_ratios)) if diff_ratios else 0.0
    max_diff = _round_ratio(max(diff_ratios)) if diff_ratios else 0.0

    return {
        "total_segments": len(records),
        "refined_segments": refined_count,
        "changed_segments": changed,
        "unchanged_segments": category_counts.get(MODIFICATION_UNCHANGED, 0),
        "pending_segments": category_counts.get(MODIFICATION_PENDING, 0),
        "skipped_human_edited_segments": category_counts.get(MODIFICATION_SKIPPED_HUMAN, 0),
        "category_counts": category_counts,
        "avg_diff_ratio": avg_diff,
        "median_diff_ratio": med_diff,
        "max_diff_ratio": max_diff,
        "changed_ratio": _round_ratio(changed / len(records)) if records else 0.0,
    }


def build_refine_diff(
    doc: dict[str, Any],
    *,
    run_id: str = "",
    generated_at: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Build draft_vs_refined diff doc and structured change_log."""
    records = iter_segment_records(doc)
    stats = _aggregate_stats(records)
    ts = generated_at or _utc_now()
    resolved_run_id = run_id or str(doc.get("run_id") or "")

    diff_segments: list[dict[str, Any]] = []
    change_segments: list[dict[str, Any]] = []

    for rec in records:
        unified = []
        if rec["changed"] and rec["baseline_text"] and rec["refined_text"]:
            unified = _unified_diff_lines(
                rec["baseline_text"],
                rec["refined_text"],
                rec["segment_id"],
            )

        diff_segments.append(
            {
                "segment_id": rec["segment_id"],
                "chapter_id": rec["chapter_id"],
                "human_edited": rec["human_edited"],
                "baseline_text": rec["baseline_text"],
                "refined_text": rec["refined_text"],
                "modification_type": rec["modification_type"],
                "similarity_ratio": rec["similarity_ratio"],
                "diff_ratio": rec["diff_ratio"],
                "length_ratio": rec["length_ratio"],
                "draft_char_count": rec["draft_char_count"],
                "refined_char_count": rec["refined_char_count"],
                "char_delta": rec["char_delta"],
                "content_fingerprint": rec["content_fingerprint"],
                "unified_diff": unified,
            }
        )
        change_segments.append(
            {
                "segment_id": rec["segment_id"],
                "chapter_id": rec["chapter_id"],
                "human_edited": rec["human_edited"],
                "modification_type": rec["modification_type"],
                "similarity_ratio": rec["similarity_ratio"],
                "diff_ratio": rec["diff_ratio"],
                "length_ratio": rec["length_ratio"],
                "draft_char_count": rec["draft_char_count"],
                "refined_char_count": rec["refined_char_count"],
                "char_delta": rec["char_delta"],
                "changed": rec["changed"],
                "content_fingerprint": rec["content_fingerprint"],
            }
        )

    diff_doc = {
        "schema_version": SCHEMA_VERSION,
        "artifact": "draft_vs_refined_diff",
        "run_id": resolved_run_id,
        "generated_at": ts,
        "summary": stats,
        "segments": diff_segments,
    }
    change_log = {
        "schema_version": SCHEMA_VERSION,
        "artifact": "refine_change_log",
        "run_id": resolved_run_id,
        "generated_at": ts,
        "summary": stats,
        "segments": change_segments,
    }
    return diff_doc, change_log


def write_refine_diff_artifacts(
    run_root: Path,
    diff_doc: dict[str, Any],
    change_log: dict[str, Any],
) -> dict[str, Path]:
    """Write diff + change_log JSON into a run directory (gitignored workspace/runs)."""
    run_root.mkdir(parents=True, exist_ok=True)
    diff_path = run_root / "draft_vs_refined_diff.json"
    change_path = run_root / "change_log.json"
    diff_path.write_text(json.dumps(diff_doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    change_path.write_text(json.dumps(change_log, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"diff": diff_path, "change_log": change_path}


def build_refine_diff_for_run(
    run_root: Path,
    *,
    segments_path: Path | None = None,
) -> dict[str, Any]:
    """Load segments.json from run dir, build artifacts, return summary."""
    run_root = run_root.resolve()
    seg_path = segments_path or (run_root / "segments.json")
    if not seg_path.is_file():
        raise FileNotFoundError(f"segments.json not found: {seg_path}")

    doc = json.loads(seg_path.read_text(encoding="utf-8"))
    meta_path = run_root / "run_metadata.json"
    run_id = run_root.name
    if meta_path.is_file():
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        run_id = str(meta.get("run_id") or run_id)

    diff_doc, change_log = build_refine_diff(doc, run_id=run_id)
    paths = write_refine_diff_artifacts(run_root, diff_doc, change_log)
    stats = diff_doc["summary"]
    return {
        "run_id": run_id,
        "run_root": str(run_root),
        "diff_path": str(paths["diff"]),
        "change_log_path": str(paths["change_log"]),
        **stats,
    }


def load_segments_doc(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))
