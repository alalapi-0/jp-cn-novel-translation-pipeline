"""Conservative, source-conditioned alignment of revised translation segments.

The aligner deliberately prefers a manual decision over a plausible ordinal match.
It never mutates the supplied canonical or revision records.
"""

from __future__ import annotations

import copy
import re
import unicodedata
from difflib import SequenceMatcher
from typing import Any, Mapping, Sequence

_SPACE_RE = re.compile(r"\s+")


def normalize_text(value: Any) -> str:
    """Normalize Unicode and insignificant whitespace for anchor comparison."""
    text = unicodedata.normalize("NFKC", str(value or ""))
    return _SPACE_RE.sub("", text).strip()


def _target(record: Mapping[str, Any]) -> str:
    for key in ("target_text", "revised_text", "translation", "text"):
        if key in record:
            return str(record.get(key) or "")
    return ""


def _source(record: Mapping[str, Any]) -> str:
    return str(record.get("source_text") or "")


def _chapter(record: Mapping[str, Any]) -> str | None:
    value = record.get("chapter_id")
    if value:
        return str(value)
    segment_id = str(record.get("segment_id") or "")
    match = re.match(r"^(ch[-_]?\d+)", segment_id, flags=re.IGNORECASE)
    return match.group(1).replace("_", "-").lower() if match else None


def _manual(kind: str, *, revision_index: int | None = None,
            canonical_index: int | None = None, candidates: Sequence[str] = ()) -> dict[str, Any]:
    item: dict[str, Any] = {
        "kind": kind,
        "reason": "structural_or_ambiguous_change_requires_human_alignment",
        "candidate_segment_ids": list(candidates),
    }
    if revision_index is not None:
        item["revision_index"] = revision_index
    if canonical_index is not None:
        item["canonical_segment_id"] = ""  # filled by caller
        item["canonical_index"] = canonical_index
    return item


def align_revisions(
    canonical_segments: Sequence[Mapping[str, Any]],
    revised_segments: Sequence[Mapping[str, Any]],
    *,
    similarity_threshold: float = 0.92,
    ambiguity_margin: float = 0.08,
) -> dict[str, Any]:
    """Align revisions without forcing insertions, deletions, merges, or splits.

    Precedence is explicit unique ``segment_id``, unique normalized target anchor,
    then a monotonic high-confidence match conditioned by source text. Any
    uncertain or structural case is emitted for manual review.
    """
    canonical = copy.deepcopy(list(canonical_segments))
    revised = copy.deepcopy(list(revised_segments))
    canonical_ids = [str(item.get("segment_id") or "") for item in canonical]
    if any(not value for value in canonical_ids) or len(set(canonical_ids)) != len(canonical_ids):
        raise ValueError("canonical segment_id values must be non-empty and unique")

    matches: dict[int, tuple[int, str, float]] = {}
    used_canonical: set[int] = set()
    manual: list[dict[str, Any]] = []

    id_to_index = {value: index for index, value in enumerate(canonical_ids)}
    revised_id_counts: dict[str, int] = {}
    for item in revised:
        seg_id = str(item.get("segment_id") or "")
        if seg_id:
            revised_id_counts[seg_id] = revised_id_counts.get(seg_id, 0) + 1

    # Pass 1: only unique explicit IDs are authoritative.
    for revision_index, item in enumerate(revised):
        seg_id = str(item.get("segment_id") or "")
        if not seg_id or revised_id_counts.get(seg_id) != 1:
            continue
        canonical_index = id_to_index.get(seg_id)
        if canonical_index is not None:
            matches[revision_index] = (canonical_index, "explicit_segment_id", 1.0)
            used_canonical.add(canonical_index)

    # Pass 2: exact normalized target anchors must be unique on both sides.
    canonical_targets: dict[tuple[str | None, str], list[int]] = {}
    revision_targets: dict[tuple[str | None, str], list[int]] = {}
    for index, item in enumerate(canonical):
        if index not in used_canonical:
            canonical_targets.setdefault((_chapter(item), normalize_text(_target(item))), []).append(index)
    for index, item in enumerate(revised):
        if index not in matches:
            revision_targets.setdefault((_chapter(item), normalize_text(_target(item))), []).append(index)
    for chapter_anchor, revision_indexes in revision_targets.items():
        chapter, anchor = chapter_anchor
        candidates = canonical_targets.get(chapter_anchor, [])
        if anchor and len(revision_indexes) == 1 and len(candidates) == 1:
            ri, ci = revision_indexes[0], candidates[0]
            matches[ri] = (ci, "exact_normalized_target", 1.0)
            used_canonical.add(ci)

    # Pass 3: conservative monotonic matching inside bounds established above.
    for revision_index, item in enumerate(revised):
        if revision_index in matches:
            continue
        prior = [ci for ri, (ci, _, _) in matches.items() if ri < revision_index]
        following = [ci for ri, (ci, _, _) in matches.items() if ri > revision_index]
        low = max(prior, default=-1)
        high = min(following, default=len(canonical))
        candidates: list[tuple[float, int]] = []
        revised_source = normalize_text(_source(item))
        revised_target = normalize_text(_target(item))
        for canonical_index, candidate in enumerate(canonical):
            if canonical_index in used_canonical or not (low < canonical_index < high):
                continue
            if _chapter(item) and _chapter(candidate) and _chapter(item) != _chapter(candidate):
                continue
            source_ratio = SequenceMatcher(None, revised_source, normalize_text(_source(candidate))).ratio() if revised_source else 0.0
            target_ratio = SequenceMatcher(None, revised_target, normalize_text(_target(candidate))).ratio() if revised_target else 0.0
            source_exact = bool(revised_source) and source_ratio == 1.0
            # Source identity is strongest; otherwise both source and target must agree.
            score = (0.72 * source_ratio + 0.28 * target_ratio) if revised_source else target_ratio
            if revised_source:
                eligible = (source_exact and target_ratio >= 0.35) or (
                    source_ratio >= 0.90 and target_ratio >= 0.82 and score >= similarity_threshold
                )
            else:
                # Actual forum revisions omit source text. Permit only a very close,
                # same-chapter target match; ordering bounds and margin still apply.
                eligible = (
                    bool(_chapter(item))
                    and _chapter(candidate) == _chapter(item)
                    and target_ratio >= max(0.94, similarity_threshold)
                )
            if eligible:
                candidates.append((score, canonical_index))
        candidates.sort(reverse=True)
        if candidates:
            best_score, best_index = candidates[0]
            runner_up = candidates[1][0] if len(candidates) > 1 else 0.0
            if best_score >= similarity_threshold and best_score - runner_up >= ambiguity_margin:
                matches[revision_index] = (best_index, "monotonic_high_confidence", round(best_score, 6))
                used_canonical.add(best_index)

    aligned: list[dict[str, Any]] = []
    for revision_index, (canonical_index, method, confidence) in sorted(matches.items()):
        old_text = _target(canonical[canonical_index])
        new_text = _target(revised[revision_index])
        aligned.append(
            {
                "segment_id": canonical_ids[canonical_index],
                "chapter_id": _chapter(canonical[canonical_index]) or _chapter(revised[revision_index]) or "unknown",
                "canonical_index": canonical_index,
                "revision_index": revision_index,
                "alignment_method": method,
                "confidence": confidence,
                "change_type": "unchanged" if normalize_text(old_text) == normalize_text(new_text) else "modified",
                "before_text": old_text,
                "after_text": new_text,
                "source_text": _source(canonical[canonical_index]),
            }
        )

    for revision_index, item in enumerate(revised):
        if revision_index not in matches:
            same_target = [
                canonical_ids[index] for index, candidate in enumerate(canonical)
                if index not in used_canonical
                and _chapter(candidate) == _chapter(item)
                and normalize_text(_target(candidate)) == normalize_text(_target(item))
            ]
            manual.append(_manual("unmatched_revision", revision_index=revision_index, candidates=same_target))
    for canonical_index, item in enumerate(canonical):
        if canonical_index not in used_canonical:
            entry = _manual("unmatched_canonical", canonical_index=canonical_index)
            entry["canonical_segment_id"] = canonical_ids[canonical_index]
            manual.append(entry)

    return {
        "aligned_segments": aligned,
        "manual_queue": manual,
        "summary": {
            "canonical_segment_count": len(canonical),
            "revision_segment_count": len(revised),
            "aligned_segment_count": len(aligned),
            "unchanged_segment_count": sum(item["change_type"] == "unchanged" for item in aligned),
            "modified_segment_count": sum(item["change_type"] == "modified" for item in aligned),
            "manual_item_count": len(manual),
            "complete_alignment": len(aligned) == len(canonical) == len(revised) and not manual,
        },
    }
