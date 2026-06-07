#!/usr/bin/env python3
"""Token-budget batch planner for draft translation API calls."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from translation.chapter_parser import Segment, parse_chapter_file  # noqa: E402

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

    def to_dict(self) -> dict[str, Any]:
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Plan draft translation API batches")
    parser.add_argument("--chapter-file", type=Path, help="Single chapter markdown file")
    parser.add_argument(
        "--segments-json",
        type=Path,
        help="JSON file with [{segment_id, source_text}, ...]",
    )
    parser.add_argument("--token-budget", type=int, default=DEFAULT_TOKEN_BUDGET)
    parser.add_argument("--max-segments-per-call", type=int, default=DEFAULT_MAX_SEGMENTS)
    parser.add_argument("--min-segments-per-call", type=int, default=MIN_SEGMENTS_PER_CALL)
    parser.add_argument("--json", action="store_true", help="Print JSON plan to stdout")
    args = parser.parse_args()

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
    else:
        parser.error("provide --chapter-file or --segments-json")

    plan = plan_batches(
        segments,
        token_budget=args.token_budget,
        max_segments_per_call=args.max_segments_per_call,
        min_segments_per_call=args.min_segments_per_call,
    )
    payload = plan.to_dict()
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(
            f"batches={payload['batch_count']} "
            f"segments={payload['total_segments']} "
            f"avg={payload['avg_segments_per_batch']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
