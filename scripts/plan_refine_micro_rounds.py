#!/usr/bin/env python3
"""Plan R-MR refinement micro-rounds from locked baseline (FS-040).

Reads ``draft_full_baseline/`` read-only, enumerates R-MR-001..148, and
packs segment batches for one round using the same sizing rules as
``refine_runner`` (max segments / char budget per API call).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from micro_round_plan import (  # noqa: E402
    FIRST_REFINE_MR_CHAPTER,
    TOTAL_CHAPTERS,
    build_refine_mr_queue,
    refine_mr_plan,
)
from translation.baseline_guard import baseline_dir, is_baseline_locked  # noqa: E402
from translation.chapter_parser import Segment, count_source_chapters  # noqa: E402

SEGMENT_ID_RE = re.compile(r"^<!--\s*(ch-\d+-seg-\d+)\s*-->")
REFINE_BATCH_MAX_SEGMENTS = 8
REFINE_BATCH_MAX_CHARS = 6000
QUEUE_CONFIG_REL = "workspace/control/scheduler_queue.json"


@dataclass
class RefinePlannedBatch:
    batch_index: int
    segment_ids: list[str]
    segment_count: int
    draft_char_total: int


@dataclass
class RefineBatchPlan:
    batches: list[RefinePlannedBatch] = field(default_factory=list)
    total_segments: int = 0

    def to_dict(self) -> dict[str, Any]:
        counts = [b.segment_count for b in self.batches]
        return {
            "total_segments": self.total_segments,
            "batch_count": len(self.batches),
            "avg_segments_per_batch": round(self.total_segments / len(self.batches), 2)
            if self.batches
            else 0,
            "max_segments_per_batch": max(counts) if counts else 0,
            "batches": [
                {
                    "batch_index": b.batch_index,
                    "segment_count": b.segment_count,
                    "segment_ids": b.segment_ids,
                    "draft_char_total": b.draft_char_total,
                }
                for b in self.batches
            ],
        }


def _load_queue_config(repo_root: Path) -> dict[str, int]:
    path = repo_root / QUEUE_CONFIG_REL
    doc: dict[str, Any] = {}
    if path.is_file():
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            doc = {}
    return {
        "rmr_anchor_chapter": int(doc.get("rmr_anchor_chapter") or FIRST_REFINE_MR_CHAPTER),
        "chapters_per_round": max(1, int(doc.get("chapters_per_round") or 3)),
        "total_chapters": count_source_chapters(repo_root) or TOTAL_CHAPTERS,
    }


def parse_baseline_chapter(path: Path) -> list[Segment]:
    """Parse baseline markdown (segment markers + draft text) into segments."""
    segments: list[Segment] = []
    current_id: str | None = None
    buf: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("# "):
            continue
        match = SEGMENT_ID_RE.match(line.strip())
        if match:
            if current_id and buf:
                text = "\n".join(buf).strip()
                if text:
                    segments.append(
                        Segment(segment_id=current_id, source_text="", draft_text=text)
                    )
            current_id = match.group(1)
            buf = []
        elif current_id is not None:
            buf.append(line)
    if current_id and buf:
        text = "\n".join(buf).strip()
        if text:
            segments.append(Segment(segment_id=current_id, source_text="", draft_text=text))
    return segments


def baseline_chapter_path(repo_root: Path, chapter_num: int) -> Path:
    return baseline_dir(repo_root) / f"chapter_{chapter_num:03d}_draft_zh.md"


def segments_from_baseline_range(
    repo_root: Path,
    chapter_start: int,
    chapter_end: int,
) -> tuple[list[Segment], list[int]]:
    """Load refine segments from baseline; return (segments, missing chapter nums)."""
    segments: list[Segment] = []
    missing: list[int] = []
    for num in range(chapter_start, chapter_end + 1):
        path = baseline_chapter_path(repo_root, num)
        if not path.is_file():
            missing.append(num)
            continue
        segments.extend(parse_baseline_chapter(path))
    return segments, missing


def plan_refine_batches(
    segments: Sequence[Segment],
    *,
    max_segments: int = REFINE_BATCH_MAX_SEGMENTS,
    max_chars: int = REFINE_BATCH_MAX_CHARS,
) -> RefineBatchPlan:
    """Pack baseline draft segments using refine_runner sizing rules."""
    plan = RefineBatchPlan(total_segments=len(segments))
    if not segments:
        return plan

    current: list[Segment] = []
    char_count = 0
    batch_index = 0

    def flush() -> None:
        nonlocal batch_index, current, char_count
        if not current:
            return
        plan.batches.append(
            RefinePlannedBatch(
                batch_index=batch_index,
                segment_ids=[s.segment_id for s in current],
                segment_count=len(current),
                draft_char_total=sum(len(s.draft_text) for s in current),
            )
        )
        batch_index += 1
        current = []
        char_count = 0

    for seg in segments:
        seg_len = len(seg.draft_text)
        if current and (len(current) >= max_segments or char_count + seg_len > max_chars):
            flush()
        current.append(seg)
        char_count += seg_len
    flush()
    return plan


def build_queue_stats(repo_root: Path) -> dict[str, Any]:
    """Summarize the full R-MR queue against locked baseline chapters."""
    cfg = _load_queue_config(repo_root)
    anchor = cfg["rmr_anchor_chapter"]
    per_round = cfg["chapters_per_round"]
    total = cfg["total_chapters"]
    queue = build_refine_mr_queue(
        anchor_chapter=anchor,
        total_chapters=total,
        round_size=per_round,
    )
    baseline_root = baseline_dir(repo_root)
    baseline_nums = set()
    if baseline_root.is_dir():
        for path in baseline_root.glob("chapter_*_draft_zh.md"):
            m = re.match(r"^chapter_(\d+)_draft_zh\.md$", path.name)
            if m:
                baseline_nums.add(int(m.group(1)))

    queue_chapters = list(range(anchor, total + 1))
    missing_in_baseline = sorted(ch for ch in queue_chapters if ch not in baseline_nums)

    return {
        "rmr_anchor_chapter": anchor,
        "chapters_per_round": per_round,
        "total_chapters": total,
        "total_rounds": len(queue),
        "chapters_to_refine": len(queue_chapters),
        "baseline_locked": is_baseline_locked(repo_root),
        "baseline_chapter_count": len(baseline_nums),
        "baseline_chapters_in_queue": len(queue_chapters) - len(missing_in_baseline),
        "missing_baseline_chapters": missing_in_baseline,
        "first_round": queue[0] if queue else None,
        "last_round": queue[-1] if queue else None,
        "round_ids": [item["round_id"] for item in queue],
    }


def plan_round(
    repo_root: Path,
    *,
    round_id: str,
    chapter_range: str = "",
) -> dict[str, Any]:
    """Build a batch plan for one R-MR round from baseline (read-only)."""
    cfg = _load_queue_config(repo_root)
    mr = refine_mr_plan(
        round_id,
        round_size=cfg["chapters_per_round"],
        anchor_chapter=cfg["rmr_anchor_chapter"],
        total_chapters=cfg["total_chapters"],
    )
    if mr is None:
        raise ValueError(f"unknown or out-of-range round_id={round_id!r}")

    ch_start = int(mr["chapter_start"])
    ch_end = int(mr["chapter_end"])
    if chapter_range:
        m = re.match(r"^(\d+)-(\d+)$", chapter_range.strip())
        if not m:
            raise ValueError(f"invalid chapter range: {chapter_range!r}")
        ch_start, ch_end = int(m.group(1)), int(m.group(2))

    segments, missing = segments_from_baseline_range(repo_root, ch_start, ch_end)
    batch_plan = plan_refine_batches(segments)
    return {
        "round_id": round_id,
        "phase": "refine",
        "chapter_range": f"{ch_start}-{ch_end}",
        "chapter_start": ch_start,
        "chapter_end": ch_end,
        "model_profile": mr["model_profile"],
        "input_source": mr["input_source"],
        "baseline_locked": is_baseline_locked(repo_root),
        "missing_baseline_chapters": missing,
        **batch_plan.to_dict(),
    }


def main() -> int:
    if os.environ.get("ALLOW_LEGACY_REFINEMENT") != "1":
        print(
            "plan_refine_micro_rounds: legacy refinement/R-MR route is disabled. "
            "Use docs/translation_production_protocol.md and singleton final export. "
            "Set ALLOW_LEGACY_REFINEMENT=1 only for historical diagnostics."
        )
        return 2
    parser = argparse.ArgumentParser(description="Plan R-MR refinement micro-rounds (FS-040)")
    parser.add_argument("--round-id", default="", help="R-MR-NNN round id")
    parser.add_argument("--chapter-range", default="", help="Override chapter range e.g. 171-173")
    parser.add_argument("--queue-stats", action="store_true", help="Print full R-MR queue stats")
    parser.add_argument("--dry-run", action="store_true", help="Plan only; no side effects")
    parser.add_argument("--json", action="store_true", help="Print JSON to stdout")
    args = parser.parse_args()

    repo_root = REPO_ROOT
    payload: dict[str, Any] = {"dry_run": bool(args.dry_run)}

    if args.queue_stats or not args.round_id:
        payload["queue"] = build_queue_stats(repo_root)

    if args.round_id:
        payload["plan"] = plan_round(
            repo_root,
            round_id=args.round_id.strip(),
            chapter_range=args.chapter_range.strip(),
        )
    elif not args.queue_stats:
        parser.error("provide --round-id or --queue-stats")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if "queue" in payload:
            q = payload["queue"]
            print(
                f"rounds={q['total_rounds']} "
                f"chapters_to_refine={q['chapters_to_refine']} "
                f"baseline_locked={q['baseline_locked']}"
            )
        if "plan" in payload:
            p = payload["plan"]
            print(
                f"{p['round_id']} {p['chapter_range']} "
                f"batches={p['batch_count']} segments={p['total_segments']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
