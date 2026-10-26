"""Stage C controlled refinement — supervised micro-round runner (FS-041)."""

from __future__ import annotations

import json
import os
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from providers.controlled_run import ControlledRunConfig, ControlledRunManager
from providers.cost_guard import CostGuard, CostGuardConfig, CostGuardError
from providers.dry_run_provider import DryRunProvider
from providers.types import GenerateOptions
from translation.draft_runner import RunBudget
from translation.pipeline_events import classify_error, emit_event
from translation.refine_prompt_builder import build_refine_batch_messages
from translation.response_extractor import extract_translations
from translation.run_progress import atomic_write_json, init_run_metadata, write_run_progress
from translation.stop_control import StopRequested, check_stop_or_raise

REPO_SCRIPTS = Path(__file__).resolve().parent.parent.parent / "scripts"
if str(REPO_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(REPO_SCRIPTS))

STAGE_C_MAX_SEGMENTS = int(os.environ.get("STAGE_C_MAX_SEGMENTS", "500"))
REFINE_BATCH_MAX_SEGMENTS = int(os.environ.get("REFINE_BATCH_MAX_SEGMENTS", "8"))
REFINE_BATCH_MAX_CHARS = int(os.environ.get("REFINE_BATCH_MAX_CHARS", "6000"))
MAX_API_RETRIES = 3


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class RefineRunSummary:
    run_id: str
    provider_mode: str
    model_name: str
    refined_segments: int = 0
    skipped_human_edited: int = 0
    skipped_already_refined: int = 0
    api_calls: int = 0
    spent_usd: float = 0.0
    spent_tokens: int = 0
    aborted: bool = False
    abort_reason: str = ""
    tick_paused: bool = False
    diffs: list[dict[str, Any]] = field(default_factory=list)


class RefineRunTickExit(Exception):
    """Supervised micro-round budget exhausted; checkpoint saved for resume."""

    def __init__(self, summary: RefineRunSummary, run_root: Path) -> None:
        self.summary = summary
        self.run_root = run_root
        super().__init__("refine_run_tick_exit")


_CHAPTER_FROM_SEG = re.compile(r"^(ch-\d+)")


def load_segments_doc(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def save_segments_doc(doc: dict[str, Any], path: Path) -> None:
    doc["pipeline_stage"] = "refinement"
    doc["updated_at"] = _utc_now()
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def iter_refine_candidates(
    doc: dict[str, Any],
    *,
    limit: int,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    """Return (chapter, segment) pairs eligible for refine, capped by limit."""
    out: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for chapter in doc.get("chapters", []):
        for seg in chapter.get("segments", []):
            if len(out) >= limit:
                return out
            if seg.get("human_edited"):
                continue
            draft = (seg.get("draft_text") or "").strip()
            if not draft:
                continue
            if (seg.get("refined_text") or "").strip():
                continue
            out.append((chapter, seg))
    return out


def _extract_refined(raw_output: str, expected_ids: list[str]) -> tuple[bool, str, dict[str, str]]:
    result = extract_translations(raw_output, expected_ids)
    if result.parse_status == "failed" and not result.items:
        return False, ";".join(result.parse_errors) or "extract_failed", {}
    mapping = {item.segment_id: item.translation for item in result.items}
    if result.parse_status != "ok":
        return False, ";".join(result.parse_errors) or "partial_extract", mapping
    return True, "ok", mapping


def _dynamic_batches(segs: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    char_count = 0
    for seg in segs:
        seg_len = len((seg.get("draft_text") or "") + (seg.get("source_text") or ""))
        if current and (
            len(current) >= REFINE_BATCH_MAX_SEGMENTS
            or char_count + seg_len > REFINE_BATCH_MAX_CHARS
        ):
            batches.append(current)
            current = []
            char_count = 0
        current.append(seg)
        char_count += seg_len
    if current:
        batches.append(current)
    return batches


def _count_refine_totals(doc: dict[str, Any]) -> tuple[int, int]:
    total = refined = 0
    for chapter in doc.get("chapters", []):
        for seg in chapter.get("segments", []):
            if (seg.get("draft_text") or "").strip():
                total += 1
            if (seg.get("refined_text") or "").strip() or seg.get("human_edited"):
                refined += 1
    return total, refined


def _chapter_id_from_segment(segment_id: str) -> str:
    match = _CHAPTER_FROM_SEG.match(segment_id)
    return match.group(1) if match else "ch-unknown"


def _segments_doc_from_baseline(
    segments: list[Any],
    *,
    chapter_start: int,
    chapter_end: int,
) -> dict[str, Any]:
    by_chapter: dict[str, list[dict[str, Any]]] = {}
    for seg in segments:
        sid = seg.segment_id
        cid = _chapter_id_from_segment(sid)
        by_chapter.setdefault(cid, []).append(
            {
                "segment_id": sid,
                "source_text": (seg.source_text or "").strip(),
                "draft_text": (seg.draft_text or "").strip(),
                "status": "baseline_draft",
            }
        )
    chapters = []
    for num in range(chapter_start, chapter_end + 1):
        cid = f"ch-{num:03d}"
        segs = by_chapter.get(cid, [])
        if segs:
            chapters.append(
                {
                    "chapter_id": cid,
                    "chapter_label": f"Chapter {num}",
                    "segments": segs,
                }
            )
    return {
        "language_direction": "JP_TO_CN",
        "pipeline_stage": "refinement",
        "input_source": "draft_full_baseline",
        "chapters": chapters,
    }


def bootstrap_refine_run_from_baseline(
    repo_root: Path,
    *,
    run_id: str,
    chapter_start: int,
    chapter_end: int,
    chapter_offset: int,
) -> Path:
    """Initialize a refine run from locked baseline (read-only; never writes baseline)."""
    from plan_refine_micro_rounds import segments_from_baseline_range  # noqa: WPS433

    run_root = repo_root / "workspace" / "runs" / run_id
    segments_path = run_root / "segments.json"
    if segments_path.is_file():
        return run_root

    segments, missing = segments_from_baseline_range(repo_root, chapter_start, chapter_end)
    if missing:
        raise FileNotFoundError(
            f"missing baseline chapters for refine bootstrap: {missing[:5]}"
            f"{'...' if len(missing) > 5 else ''}"
        )
    if not segments:
        raise FileNotFoundError(
            f"no baseline segments for chapters {chapter_start}-{chapter_end}"
        )

    run_root.mkdir(parents=True, exist_ok=True)
    doc = _segments_doc_from_baseline(
        segments,
        chapter_start=chapter_start,
        chapter_end=chapter_end,
    )
    segments_path.write_text(
        json.dumps(doc, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    init_run_metadata(
        run_root,
        run_id=run_id,
        phase="refine",
        stage="refine_stage_c",
        scope="refine_micro_round",
        chapter_offset=chapter_offset,
        provider_mode="pending",
        extra={"input_source": "draft_full_baseline"},
    )
    (run_root / "draft_quality_report.json").write_text(
        json.dumps({"stage_c_eligible": True, "passed": True}, ensure_ascii=False, indent=2)
        + "\n",
        encoding="utf-8",
    )
    atomic_write_json(
        run_root / "input_provenance.json",
        {
            "input_source": "draft_full_baseline",
            "chapter_range": f"{chapter_start}-{chapter_end}",
            "baseline_read_only": True,
            "created_at": _utc_now(),
        },
    )
    total = sum(len(ch["segments"]) for ch in doc["chapters"])
    write_run_progress(
        run_root,
        run_id=run_id,
        phase="refine",
        stage="refine_stage_c",
        chapter_offset=chapter_offset,
        status="pending",
        total_segments=total,
        completed_segments=0,
        pending_segments=total,
    )
    return run_root


def _write_compact_refine_progress(
    run_root: Path,
    *,
    run_id: str,
    round_id: str,
    summary: RefineRunSummary,
    total_expected: int,
    completed: int,
    run_budget: RunBudget | None,
    status: str = "in_progress",
) -> None:
    payload: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "round_id": round_id,
        "status": status,
        "progress": f"{completed}/{total_expected}",
        "api_calls": summary.api_calls,
        "cost_usd": round(summary.spent_usd, 6),
        "segments_per_call": round(completed / summary.api_calls, 2) if summary.api_calls else 0,
        "updated_at": _utc_now(),
    }
    if run_budget:
        payload["budget"] = {
            "max_api_calls": run_budget.max_api_calls,
            "max_segments": run_budget.max_segments,
            "api_calls_used": run_budget.api_calls_used,
            "segments_used": run_budget.segments_used,
        }
    path = run_root / "micro_round_progress.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _apply_dry_run_passthrough(
    batch: list[dict[str, Any]],
    diffs: list[dict[str, Any]],
) -> None:
    for seg in batch:
        draft = (seg.get("draft_text") or "").strip()
        seg["refined_text"] = draft
        seg["refine_status"] = "dry_run_passthrough"
        diffs.append(
            {
                "segment_id": seg["segment_id"],
                "skipped": False,
                "mode": "dry_run_passthrough",
                "before": draft[:120],
                "after": draft[:120],
            }
        )


def _budget_tick_exit(
    *,
    summary: RefineRunSummary,
    run_root: Path,
    controlled: ControlledRunManager,
    guard: CostGuard,
) -> None:
    if guard:
        summary.spent_usd = guard.spent_usd
        summary.spent_tokens = guard.spent_tokens
    controlled.checkpoint.status = "in_progress"
    controlled.save()
    raise RefineRunTickExit(summary, run_root)


def run_refine_controlled(
    *,
    repo_root: Path,
    run_id: str,
    limit_segments: int,
    provider_factory: Callable[[CostGuard], Any] | None = None,
    force_dry_run: bool = False,
    max_batches: int | None = None,
    max_retry_per_batch: int | None = None,
    heartbeat_cb: Callable[[], None] | None = None,
    run_budget: RunBudget | None = None,
    round_id: str = "",
    worker_id: str = "",
) -> tuple[RefineRunSummary, Path]:
    """Deprecated unconditional refinement has no executable production route."""
    raise RuntimeError("legacy_refinement_disabled: use evidence-bound localized correction")


def run_refine_pilot(
    *,
    repo_root: Path,
    run_id: str,
    limit_segments: int,
    provider_factory: Callable[[CostGuard], Any] | None = None,
    force_dry_run: bool = False,
) -> tuple[RefineRunSummary, Path]:
    """Backward-compatible alias for controlled refine runner."""
    return run_refine_controlled(
        repo_root=repo_root,
        run_id=run_id,
        limit_segments=limit_segments,
        provider_factory=provider_factory,
        force_dry_run=force_dry_run,
    )


def run_refine_micro_round(
    *,
    repo_root: Path,
    run_id: str,
    chapter_start: int,
    chapter_end: int,
    chapter_offset: int,
    provider_factory: Callable[[CostGuard], Any] | None = None,
    force_dry_run: bool = False,
    heartbeat_cb: Callable[[], None] | None = None,
    worker_id: str = "",
    run_budget: RunBudget | None = None,
    round_id: str = "",
) -> tuple[RefineRunSummary, Path]:
    """Deprecated unconditional refinement has no executable production route."""
    raise RuntimeError("legacy_refinement_disabled: use evidence-bound localized correction")


def _write_refine_artifacts(run_root: Path, summary: RefineRunSummary) -> None:
    diff_path = run_root / "refine_diff.json"
    diff_path.write_text(
        json.dumps(
            {
                "run_id": summary.run_id,
                "generated_at": _utc_now(),
                "provider_mode": summary.provider_mode,
                "model_name": summary.model_name,
                "diffs": summary.diffs,
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    report = {
        "run_id": summary.run_id,
        "phase": "refine",
        "stage": "refine_stage_c",
        "refined_segments": summary.refined_segments,
        "api_calls": summary.api_calls,
        "cost_usd": summary.spent_usd,
        "provider_mode": summary.provider_mode,
        "model_name": summary.model_name,
        "aborted": summary.aborted,
        "abort_reason": summary.abort_reason,
        "generated_at": _utc_now(),
    }
    (run_root / "refine_quality_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
