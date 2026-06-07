#!/usr/bin/env python3
"""Token-budget batch planner for draft translation API calls."""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from micro_round_plan import resolve_round_plan  # noqa: E402
from translation.chapter_parser import (  # noqa: E402
    Segment,
    list_chapter_files,
    parse_chapter_file,
)
from translation.run_progress import safe_load_json  # noqa: E402

# Segment length classes (source char count, JP prose).
SHORT_MAX_CHARS = 80
MEDIUM_MAX_CHARS = 200
LONG_MAX_CHARS = 500

TARGET_SEGMENTS_BY_CLASS = {
    "short": 32,
    "medium": 20,
    "long": 8,
    "extra_long": 1,
}

MIN_SEGMENTS_PER_CALL = 15
DEFAULT_TOKEN_BUDGET = 12_000
DEFAULT_MAX_SEGMENTS = 30
PROMPT_OVERHEAD_TOKENS = 900
OUTPUT_TOKENS_PER_SEGMENT = 120


@dataclass
class PlannedBatch:
    batch_index: int
    segment_ids: list[str]
    segment_count: int
    estimated_input_tokens: int
    length_class: str
    source_char_total: int


@dataclass
class BatchPlan:
    batches: list[PlannedBatch] = field(default_factory=list)
    total_segments: int = 0
    token_budget: int = DEFAULT_TOKEN_BUDGET
    max_segments_per_call: int = DEFAULT_MAX_SEGMENTS

    def to_dict(self, *, segments: Sequence[Segment] | None = None) -> dict[str, Any]:
        counts = [b.segment_count for b in self.batches]
        overlong = 0
        if segments is not None:
            overlong = sum(
                1 for s in segments if classify_segment_length(s.source_text) == "extra_long"
            )
        return {
            "token_budget": self.token_budget,
            "max_segments_per_call": self.max_segments_per_call,
            "total_segments": self.total_segments,
            "batch_count": len(self.batches),
            "avg_segments_per_batch": round(
                self.total_segments / len(self.batches), 2
            )
            if self.batches
            else 0,
            "max_segments_per_batch": max(counts) if counts else 0,
            "estimated_tokens": sum(b.estimated_input_tokens for b in self.batches),
            "overlong_segments": overlong,
            "batches": [
                {
                    "batch_index": b.batch_index,
                    "segment_count": b.segment_count,
                    "segment_ids": b.segment_ids,
                    "estimated_input_tokens": b.estimated_input_tokens,
                    "length_class": b.length_class,
                    "source_char_total": b.source_char_total,
                }
                for b in self.batches
            ],
        }


def classify_segment_length(source_text: str) -> str:
    n = len(source_text)
    if n > LONG_MAX_CHARS:
        return "extra_long"
    if n > MEDIUM_MAX_CHARS:
        return "long"
    if n > SHORT_MAX_CHARS:
        return "medium"
    return "short"


def estimate_segment_tokens(source_text: str) -> int:
    """Conservative JP→CN draft request token estimate (input side)."""
    return max(24, int(len(source_text) * 0.55) + 32)


def _batch_class(segments: Sequence[Segment]) -> str:
    classes = [classify_segment_length(s.source_text) for s in segments]
    if "extra_long" in classes:
        return "extra_long"
    if "long" in classes:
        return "long"
    if "medium" in classes:
        return "medium"
    return "short"


def _target_for_class(length_class: str, *, max_segments: int) -> int:
    base = TARGET_SEGMENTS_BY_CLASS.get(length_class, DEFAULT_MAX_SEGMENTS)
    if length_class == "extra_long":
        return 1
    return min(max_segments, max(MIN_SEGMENTS_PER_CALL, base))


def _would_exceed_budget(
    current: list[Segment],
    nxt: Segment,
    *,
    token_budget: int,
) -> bool:
    texts = [s.source_text for s in current] + [nxt.source_text]
    est = PROMPT_OVERHEAD_TOKENS + sum(estimate_segment_tokens(t) for t in texts)
    est += len(current) * OUTPUT_TOKENS_PER_SEGMENT
    return est > token_budget


def plan_batches(
    segments: Sequence[Segment],
    *,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    max_segments_per_call: int = DEFAULT_MAX_SEGMENTS,
    min_segments_per_call: int = MIN_SEGMENTS_PER_CALL,
) -> BatchPlan:
    """Pack segments in order under token budget; respect length-class targets."""
    if max_segments_per_call < min_segments_per_call:
        min_segments_per_call = max(1, max_segments_per_call)

    plan = BatchPlan(
        token_budget=token_budget,
        max_segments_per_call=max_segments_per_call,
        total_segments=len(segments),
    )
    if not segments:
        return plan

    current: list[Segment] = []
    batch_index = 0

    def flush() -> None:
        nonlocal batch_index, current
        if not current:
            return
        est = PROMPT_OVERHEAD_TOKENS + sum(
            estimate_segment_tokens(s.source_text) for s in current
        )
        plan.batches.append(
            PlannedBatch(
                batch_index=batch_index,
                segment_ids=[s.segment_id for s in current],
                segment_count=len(current),
                estimated_input_tokens=est,
                length_class=_batch_class(current),
                source_char_total=sum(len(s.source_text) for s in current),
            )
        )
        batch_index += 1
        current = []

    for seg in segments:
        length_class = classify_segment_length(seg.source_text)
        if length_class == "extra_long":
            flush()
            current = [seg]
            flush()
            continue

        if not current:
            current.append(seg)
            continue

        batch_class = _batch_class(current)
        target = _target_for_class(batch_class, max_segments=max_segments_per_call)
        over_count = len(current) >= max_segments_per_call
        over_target = len(current) >= target
        over_budget = _would_exceed_budget(current, seg, token_budget=token_budget)

        if over_count or over_budget or (over_target and len(current) >= min_segments_per_call):
            flush()
            current = [seg]
        else:
            current.append(seg)

    flush()
    return plan


def split_failed_batch(batch: Sequence[Segment]) -> list[list[Segment]]:
    """Split one failed batch in half (preserve order) for retry."""
    items = list(batch)
    if len(items) <= 1:
        return [items]
    mid = len(items) // 2
    return [items[:mid], items[mid:]]


def plan_batches_for_chapter(
    chapter_segments: Sequence[Segment],
    **kwargs: Any,
) -> BatchPlan:
    return plan_batches(chapter_segments, **kwargs)


def segments_from_chapter_file(path: Path) -> list[Segment]:
    return parse_chapter_file(path).segments


def _parse_chapter_range(chapter_range: str) -> tuple[int, int]:
    m = re.match(r"^(\d+)-(\d+)$", chapter_range.strip())
    if not m:
        raise ValueError(f"invalid chapter range: {chapter_range!r}")
    start, end = int(m.group(1)), int(m.group(2))
    if start > end:
        raise ValueError(f"chapter range start > end: {chapter_range}")
    return start, end


def segments_from_chapter_range(
    input_dir: Path,
    chapter_start: int,
    chapter_end: int,
) -> list[Segment]:
    offset = chapter_start - 1
    limit = chapter_end - chapter_start + 1
    paths = list_chapter_files(input_dir, limit, offset=offset)
    segments: list[Segment] = []
    for path in paths:
        segments.extend(segments_from_chapter_file(path))
    return segments


def pending_segments_from_run(run_id: str, segments: Sequence[Segment]) -> list[Segment]:
    """Keep only segments without draft_text in run segments.json (if present)."""
    run_root = REPO_ROOT / "workspace" / "runs" / run_id
    doc = safe_load_json(run_root / "segments.json") or {}
    done: set[str] = set()
    for ch in doc.get("chapters", []):
        for seg in ch.get("segments", []):
            sid = str(seg.get("segment_id") or "")
            if sid and (seg.get("draft_text") or "").strip():
                done.add(sid)
    if not done:
        return list(segments)
    return [s for s in segments if s.segment_id not in done]


def resolve_plan_segments(
    *,
    run_id: str = "",
    round_id: str = "",
    chapter_range: str = "",
    pending_only: bool = False,
) -> tuple[list[Segment], dict[str, Any]]:
    meta: dict[str, Any] = {}
    if chapter_range:
        ch_start, ch_end = _parse_chapter_range(chapter_range)
        meta["chapter_range"] = f"{ch_start}-{ch_end}"
        segments = segments_from_chapter_range(REPO_ROOT / "input_jp", ch_start, ch_end)
    elif round_id:
        plan = resolve_round_plan(round_id, run_id=run_id, chapter_range=chapter_range)
        if plan is None:
            raise ValueError(f"unknown round_id={round_id}")
        meta["round_id"] = round_id
        meta["chapter_range"] = f"{plan['chapter_start']}-{plan['chapter_end']}"
        segments = segments_from_chapter_range(
            REPO_ROOT / "input_jp",
            int(plan["chapter_start"]),
            int(plan["chapter_end"]),
        )
    else:
        raise ValueError("provide --chapter-range or --round-id")

    if run_id:
        meta["run_id"] = run_id
    if pending_only and run_id:
        before = len(segments)
        segments = pending_segments_from_run(run_id, segments)
        meta["pending_only"] = True
        meta["pending_segments"] = len(segments)
        meta["total_source_segments"] = before
    return segments, meta


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan draft translation API batches")
    parser.add_argument("--chapter-file", type=Path, help="Single chapter markdown file")
    parser.add_argument(
        "--segments-json",
        type=Path,
        help="JSON file with [{segment_id, source_text}, ...]",
    )
    parser.add_argument("--run-id", default="", help="Optional run id for pending filter")
    parser.add_argument("--round-id", default="", help="D-MR-XXX round id")
    parser.add_argument("--chapter-range", default="", help="Chapter range e.g. 209-211")
    parser.add_argument(
        "--batch-token-budget",
        type=int,
        default=0,
        help="Alias for --token-budget (default 12000)",
    )
    parser.add_argument("--token-budget", type=int, default=0)
    parser.add_argument("--max-segments-per-call", type=int, default=DEFAULT_MAX_SEGMENTS)
    parser.add_argument("--min-segments-per-call", type=int, default=MIN_SEGMENTS_PER_CALL)
    parser.add_argument("--pending-only", action="store_true", help="Only plan pending segments")
    parser.add_argument("--dry-run", action="store_true", help="Plan only; no side effects")
    parser.add_argument("--json", action="store_true", help="Print JSON plan to stdout")
    args = parser.parse_args()

    token_budget = args.batch_token_budget or args.token_budget or DEFAULT_TOKEN_BUDGET
    meta: dict[str, Any] = {"dry_run": bool(args.dry_run)}

    segments: list[Segment] = []
    if args.chapter_file:
        segments = segments_from_chapter_file(args.chapter_file)
    elif args.segments_json:
        raw = json.loads(args.segments_json.read_text(encoding="utf-8"))
        for row in raw:
            segments.append(
                Segment(
                    segment_id=str(row["segment_id"]),
                    source_text=str(row.get("source_text") or row.get("text") or ""),
                )
            )
    elif args.chapter_range or args.round_id:
        segments, plan_meta = resolve_plan_segments(
            run_id=args.run_id.strip(),
            round_id=args.round_id.strip(),
            chapter_range=args.chapter_range.strip(),
            pending_only=args.pending_only,
        )
        meta.update(plan_meta)
    else:
        parser.error("provide --chapter-file, --segments-json, --chapter-range, or --round-id")

    plan = plan_batches(
        segments,
        token_budget=token_budget,
        max_segments_per_call=args.max_segments_per_call,
        min_segments_per_call=args.min_segments_per_call,
    )
    payload = plan.to_dict(segments=segments)
    payload.update(meta)
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"batches={payload['batch_count']} "
            f"segments={payload['total_segments']} "
            f"avg={payload['avg_segments_per_batch']} "
            f"max={payload['max_segments_per_batch']} "
            f"overlong={payload['overlong_segments']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
