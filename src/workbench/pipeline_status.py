"""Production pipeline status for Workbench (no secrets, read-only workspace)."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from translation.run_progress import (
    PRODUCTION_STAGE_STATE_REL,
    is_diagnostic_run_id,
    production_stage_state_path,
    safe_load_json,
)

_CHAPTER_NUM_RE = re.compile(r"^ch-(\d+)-")


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _chapter_num(chapter_id: str) -> int | None:
    m = re.match(r"^ch-(\d+)$", chapter_id or "")
    return int(m.group(1)) if m else None


def resolve_workbench_mode(repo_root: Path) -> str:
    """Return production | pilot | quickstart for top-bar mode indicator."""
    prod_path = production_stage_state_path(repo_root)
    prod = safe_load_json(prod_path) or {}
    if prod.get("run_id") and not is_diagnostic_run_id(str(prod.get("run_id") or "")):
        return "production"
    pilot_log = repo_root / "workspace" / "pilot_batch_chain.log"
    if pilot_log.is_file() and pilot_log.stat().st_size > 0:
        return "pilot"
    return "quickstart"


def resolve_segment_progress(
    repo_root: Path,
    run_id: str,
    *,
    run_root: Path | None = None,
) -> dict[str, Any]:
    """Unified segment progress: max(checkpoint count, run_progress completed_segments)."""
    root = run_root or (repo_root / "workspace" / "runs" / run_id)
    progress = safe_load_json(root / "run_progress.json") or {}
    checkpoint = safe_load_json(repo_root / "workspace" / "checkpoints" / f"{run_id}.json") or {}
    segments_doc = safe_load_json(root / "segments.json") or {}

    total_segments = progress.get("total_segments")
    if total_segments is None and segments_doc:
        total_segments = sum(len(ch.get("segments") or []) for ch in segments_doc.get("chapters") or [])

    progress_done = progress.get("completed_segments")
    checkpoint_done = len((checkpoint or {}).get("completed_segments") or [])
    if progress_done is None:
        completed_segments = checkpoint_done
    elif checkpoint_done:
        completed_segments = max(int(progress_done), checkpoint_done)
    else:
        completed_segments = int(progress_done)

    label = None
    if completed_segments is not None and total_segments is not None:
        label = f"{completed_segments}/{total_segments}"

    return {
        "total_segments": total_segments,
        "completed_segments": completed_segments,
        "checkpoint_completed": checkpoint_done,
        "progress_completed": progress_done,
        "segment_progress_label": label,
        "status": progress.get("status") or (checkpoint or {}).get("status"),
        "heartbeat_at": progress.get("heartbeat_at") or progress.get("updated_at"),
        "checkpoint_status": (checkpoint or {}).get("status"),
    }


def _resume_command(run_id: str, chapter_offset: int | None, limit_chapters: int | None) -> str:
    off = int(chapter_offset or 0)
    batch = int(limit_chapters or 50)
    return (
        f"python3 scripts/resume_production.py --run-id {run_id} "
        f"--chapter-offset {off} --target-new-chapters {batch} --hydrate-apply"
    )


def _task_label(phase: str | None) -> str:
    if phase == "refine":
        return "精修 Stage C"
    if phase == "draft":
        return "初译 Stage B"
    return "生产任务"


def _build_run_card(
    repo_root: Path,
    run_id: str,
    *,
    is_default: bool = False,
    phase: str | None = None,
    stage_state: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    run_root = repo_root / "workspace" / "runs" / run_id
    if not run_root.is_dir():
        return None
    meta = safe_load_json(run_root / "run_metadata.json") or {}
    segments_doc = safe_load_json(run_root / "segments.json") or {}
    seg = resolve_segment_progress(repo_root, run_id, run_root=run_root)

    chapter_offset = meta.get("chapter_offset")
    if chapter_offset is None:
        chapter_offset = (safe_load_json(run_root / "run_progress.json") or {}).get("chapter_offset")
    limit_chapters = meta.get("limit_chapters")

    effective_phase = phase
    if effective_phase is None and stage_state and str(stage_state.get("run_id") or "") == run_id:
        effective_phase = str(stage_state.get("phase") or "draft")

    status = seg.get("status")
    if is_default and stage_state:
        status = stage_state.get("status") or status

    return {
        "run_id": run_id,
        "is_default": is_default,
        "phase": effective_phase or "draft",
        "task_label": _task_label(effective_phase),
        "chapter_offset": chapter_offset,
        "limit_chapters": limit_chapters,
        "chapter_range_label": _chapter_range_label(chapter_offset, limit_chapters, segments_doc),
        "status": status,
        "total_segments": seg.get("total_segments"),
        "completed_segments": seg.get("completed_segments"),
        "segment_progress_label": seg.get("segment_progress_label"),
        "last_heartbeat": seg.get("heartbeat_at"),
        "checkpoint_status": seg.get("checkpoint_status"),
        "resume_command": _resume_command(run_id, chapter_offset, limit_chapters),
        "review_url": f"/review.html?production_run={run_id}",
    }


def list_production_runs(repo_root: Path) -> list[dict[str, Any]]:
    """List Stage B draft runs under workspace/runs (newest mtime first)."""
    runs_root = repo_root / "workspace" / "runs"
    if not runs_root.is_dir():
        return []
    prod = safe_load_json(production_stage_state_path(repo_root)) or {}
    default_run_id = str(prod.get("run_id") or "").strip()

    rows: list[dict[str, Any]] = []
    for run_dir in runs_root.iterdir():
        if not run_dir.is_dir():
            continue
        run_id = run_dir.name
        if not run_id.startswith("run_") or "_draft_stage_b" not in run_id:
            continue
        if is_diagnostic_run_id(run_id):
            continue
        meta = safe_load_json(run_dir / "run_metadata.json") or {}
        seg = resolve_segment_progress(repo_root, run_id, run_root=run_dir)
        rows.append(
            {
                "run_id": run_id,
                "chapter_offset": meta.get("chapter_offset"),
                "limit_chapters": meta.get("limit_chapters"),
                "status": seg.get("status") or meta.get("summary", {}).get("abort_reason"),
                "total_segments": seg.get("total_segments"),
                "completed_segments": seg.get("completed_segments"),
                "segment_progress_label": seg.get("segment_progress_label"),
                "checkpoint_completed": seg.get("checkpoint_completed"),
                "heartbeat_at": seg.get("heartbeat_at"),
                "is_default": run_id == default_run_id,
            }
        )
    rows.sort(key=lambda r: (not r.get("is_default"), r.get("run_id") or ""), reverse=False)
    rows.sort(key=lambda r: r.get("is_default", False), reverse=True)
    return rows


def _chapter_range_label(offset: int | None, limit: int | None, segments_doc: dict | None) -> str:
    if segments_doc and segments_doc.get("chapters"):
        nums = []
        for ch in segments_doc["chapters"]:
            n = _chapter_num(str(ch.get("chapter_id") or ""))
            if n is not None:
                nums.append(n)
        if nums:
            return f"第 {min(nums)}–{max(nums)} 章"
    if offset is not None and limit is not None:
        return f"第 {int(offset) + 1}–{int(offset) + int(limit)} 章"
    if offset is not None:
        return f"从第 {int(offset) + 1} 章起"
    return "—"


def _collect_active_run_cards(
    repo_root: Path,
    *,
    stage: dict[str, Any],
    default_run_id: str,
) -> list[dict[str, Any]]:
    """Return progress cards for all in-progress production runs (parallel refine + draft)."""
    cards: list[dict[str, Any]] = []
    seen: set[str] = set()

    if default_run_id:
        card = _build_run_card(
            repo_root,
            default_run_id,
            is_default=True,
            phase=str(stage.get("phase") or "draft"),
            stage_state=stage,
        )
        if card and str(card.get("status") or "") in {"in_progress", "blocked"}:
            cards.append(card)
            seen.add(default_run_id)

    for row in list_production_runs(repo_root):
        run_id = str(row.get("run_id") or "")
        if not run_id or run_id in seen:
            continue
        if str(row.get("status") or "") != "in_progress":
            continue
        card = _build_run_card(repo_root, run_id, is_default=row.get("is_default", False))
        if card:
            cards.append(card)
            seen.add(run_id)

    return cards


def build_pipeline_status(repo_root: Path) -> dict[str, Any]:
    """Summarize production resume state for homepage card and /api/runtime/pipeline-status."""
    prod_path = production_stage_state_path(repo_root)
    stage = safe_load_json(prod_path) or {}
    run_id = str(stage.get("run_id") or "").strip()
    run_root = repo_root / "workspace" / "runs" / run_id if run_id else None

    meta = safe_load_json(run_root / "run_metadata.json") if run_root else None
    segments_doc = safe_load_json(run_root / "segments.json") if run_root else None
    seg = resolve_segment_progress(repo_root, run_id) if run_id else {}

    chapter_offset = (meta or {}).get("chapter_offset")
    if chapter_offset is None and seg:
        progress_doc = safe_load_json(run_root / "run_progress.json") if run_root else None
        chapter_offset = (progress_doc or {}).get("chapter_offset")
    limit_chapters = (meta or {}).get("limit_chapters")

    resume_cmd = _resume_command(run_id, chapter_offset, limit_chapters) if run_id else ""

    active_run_cards = _collect_active_run_cards(repo_root, stage=stage, default_run_id=run_id)

    return {
        "workbench_mode": resolve_workbench_mode(repo_root),
        "stage_state_path": PRODUCTION_STAGE_STATE_REL,
        "run_id": run_id or None,
        "phase": stage.get("phase"),
        "stage": stage.get("stage"),
        "status": stage.get("status") or seg.get("status"),
        "chapter_offset": chapter_offset,
        "limit_chapters": limit_chapters,
        "chapter_range_label": _chapter_range_label(chapter_offset, limit_chapters, segments_doc),
        "total_segments": seg.get("total_segments"),
        "completed_segments": seg.get("completed_segments"),
        "segment_progress_label": seg.get("segment_progress_label"),
        "last_heartbeat": seg.get("heartbeat_at"),
        "checkpoint_status": seg.get("checkpoint_status"),
        "resume_command": resume_cmd,
        "refine_blocked": bool(stage.get("refine_blocked")),
        "checked_at": _utc_now(),
        "has_production_run": bool(run_id and run_root and run_root.is_dir()),
        "production_runs": list_production_runs(repo_root),
        "active_run_cards": active_run_cards,
    }


def production_run_segments_for_review(
    repo_root: Path,
    *,
    run_id: str,
    chapter: int | None = None,
) -> dict[str, Any]:
    """Load production run segments as Workbench review-compatible rows."""
    run_root = repo_root / "workspace" / "runs" / run_id
    seg_path = run_root / "segments.json"
    if not seg_path.is_file():
        raise FileNotFoundError(f"segments.json not found for run_id={run_id}")
    doc = safe_load_json(seg_path) or {}
    chapters = doc.get("chapters") or []
    if chapter is not None:
        chapters = [
            ch
            for ch in chapters
            if _chapter_num(str(ch.get("chapter_id") or "")) == chapter
        ]

    segments: list[dict[str, Any]] = []
    for ch in chapters:
        ch_id = str(ch.get("chapter_id") or "")
        ch_num = _chapter_num(ch_id)
        for seg in ch.get("segments") or []:
            sid = str(seg.get("segment_id") or "")
            draft = (seg.get("refined_text") or seg.get("draft_text") or "").strip()
            source = (seg.get("source_text") or "").strip()
            if not sid:
                continue
            segments.append(
                {
                    "id": sid,
                    "segment_id": sid,
                    "chapter": ch_num,
                    "chapter_id": ch_id,
                    "source": source,
                    "draft": draft,
                    "status": seg.get("status") or ("machine_translated" if draft else "pending"),
                    "generated_by": "production_run",
                }
            )

    chapter_nums = sorted(
        {_chapter_num(str(ch.get("chapter_id") or "")) for ch in doc.get("chapters") or []}
        - {None}
    )
    return {
        "run_id": run_id,
        "source": "production_run",
        "chapter_filter": chapter,
        "chapters_available": chapter_nums,
        "segments": segments,
    }
