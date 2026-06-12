"""Aggregate local scheduler status (FS-002, spec §9.2).

Collects the 13 status fields required by docs/product_final_state_spec.md
§9.2 from metadata/progress files only — never from chapter body text:

- pause / lock state          -> scheduler.control
- worker counts               -> scripts/pipeline_worker_registry.py
- draft / refinement progress -> run_metadata.json + run_progress.json
                                 (workspace/runs + workspace/archived_runs)
- tick history                -> workspace/control/scheduler_tick_state.json
                                 (written by local_scheduler_tick, FS-003)
- D-MR queue mapping          -> workspace/control/scheduler_queue.json
                                 (optional override of roadmap defaults)
"""

from __future__ import annotations

import importlib.util
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from scheduler.control import is_paused, lock_status
from translation.chapter_parser import count_source_chapters

TICK_STATE_REL = "workspace/control/scheduler_tick_state.json"
QUEUE_CONFIG_REL = "workspace/control/scheduler_queue.json"
REGISTRY_STATE_REL = "workspace/pipeline_state.json"

# Production D-MR anchor per docs/translation_recovery_3ch_roadmap.md:
# D-MR-001 covers chapters 203-205, 3 chapters per micro round.
DEFAULT_DMR_ANCHOR_CHAPTER = 203
DEFAULT_CHAPTERS_PER_ROUND = 3

_CHAPTER_NUM_RE = re.compile(r"^(\d+)-")

# Run ids that never contribute to production progress (mirrors
# translation.run_progress.is_diagnostic_run_id, kept local to stay
# importable from fixtures without the full translation package).
_DIAGNOSTIC_PREFIXES = (
    "draft-a-",
    "micro_validate",
    "fixture_",
    "asset-context",
    "round_50_e2e",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


_REGISTRY_CACHE: Any = None


def _load_registry() -> Any:
    """Load the worker registry module from the source tree (code, not data —
    always resolved against the real repo even when repo_root points at a
    test fixture)."""
    global _REGISTRY_CACHE
    if _REGISTRY_CACHE is not None:
        return _REGISTRY_CACHE
    spec = importlib.util.spec_from_file_location(
        "pipeline_worker_registry",
        _repo_root() / "scripts" / "pipeline_worker_registry.py",
    )
    if spec is None or spec.loader is None:  # pragma: no cover - repo layout broken
        raise RuntimeError("pipeline_worker_registry.py not found")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _REGISTRY_CACHE = module
    return module


def _safe_load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return doc if isinstance(doc, dict) else None


def _is_diagnostic_run(run_id: str) -> bool:
    return any(run_id.startswith(prefix) for prefix in _DIAGNOSTIC_PREFIXES)


def _chapter_numbers(chapter_files: list[Any]) -> set[int]:
    out: set[int] = set()
    for entry in chapter_files:
        name = Path(str(entry)).name
        match = _CHAPTER_NUM_RE.match(name)
        if match:
            out.add(int(match.group(1)))
    return out


def _iter_run_roots(repo_root: Path) -> list[Path]:
    roots: list[Path] = []
    for base in ("workspace/runs", "workspace/archived_runs"):
        base_path = repo_root / base
        if not base_path.is_dir():
            continue
        for meta in base_path.glob("*/run_metadata.json"):
            roots.append(meta.parent)
    return sorted(roots)


def _run_fully_completed(run_root: Path, meta: dict[str, Any]) -> bool:
    """A run counts when its segment counters show full completion.

    Prefers run_progress.json (live-updated). Older runs predate that file;
    for them fall back to run_metadata.json summary counters (final writeback),
    rejecting aborted runs.
    """
    progress = _safe_load_json(run_root / "run_progress.json")
    if progress is not None:
        total = int(progress.get("total_segments") or 0)
        completed = int(progress.get("completed_segments") or 0)
        return total > 0 and completed >= total
    summary = meta.get("summary") or {}
    if summary.get("aborted"):
        return False
    total = int(summary.get("total_segments") or 0)
    translated = int(summary.get("translated_segments") or 0)
    return total > 0 and translated >= total


def _completed_chapters_by_phase(repo_root: Path) -> dict[str, set[int]]:
    """Union of chapter numbers covered by runs whose segments all completed.

    Metadata-only: run_metadata.json (chapter file names) + run_progress.json /
    metadata summary (segment counters). Chapter body text is never read.
    """
    done: dict[str, set[int]] = {"draft": set(), "refine": set()}
    for run_root in _iter_run_roots(repo_root):
        if _is_diagnostic_run(run_root.name):
            continue
        meta = _safe_load_json(run_root / "run_metadata.json") or {}
        phase = str(meta.get("phase") or "")
        if phase not in done:
            continue
        if not _run_fully_completed(run_root, meta):
            continue
        done[phase] |= _chapter_numbers(meta.get("chapter_files") or [])
    return done


def _count_total_chapters(repo_root: Path) -> int:
    return count_source_chapters(repo_root)


def _queue_config(repo_root: Path) -> dict[str, int]:
    doc = _safe_load_json(repo_root / QUEUE_CONFIG_REL) or {}
    anchor = int(doc.get("dmr_anchor_chapter") or DEFAULT_DMR_ANCHOR_CHAPTER)
    per_round = int(doc.get("chapters_per_round") or DEFAULT_CHAPTERS_PER_ROUND)
    return {"anchor": anchor, "per_round": max(1, per_round)}


def _next_draft_target(
    completed: set[int],
    total: int,
    anchor: int,
    per_round: int,
) -> dict[str, Any]:
    """Locate the first missing chapter and map it onto the D-MR queue."""
    missing = [ch for ch in range(1, total + 1) if ch not in completed]
    if not missing:
        return {
            "draft_complete": True,
            "next_round_id": None,
            "next_chapter_range": None,
            "missing_chapter_count": 0,
        }
    next_chapter = missing[0]
    if next_chapter < anchor:
        # Legacy gap below the micro-round anchor: needs backfill, not a D-MR id.
        end = next_chapter
        while end + 1 <= total and (end + 1) in set(missing) and end + 1 < anchor:
            end += 1
        return {
            "draft_complete": False,
            "next_round_id": None,
            "next_chapter_range": f"{next_chapter}-{end}",
            "missing_chapter_count": len(missing),
            "gap_below_anchor": True,
        }
    index = (next_chapter - anchor) // per_round + 1
    start = anchor + (index - 1) * per_round
    end = min(start + per_round - 1, total)
    return {
        "draft_complete": False,
        "next_round_id": f"D-MR-{index:03d}",
        "next_chapter_range": f"{start}-{end}",
        "missing_chapter_count": len(missing),
    }


def _progress_dict(completed: int, total: int) -> dict[str, Any]:
    percent = round(100.0 * completed / total, 2) if total else 0.0
    return {"completed_chapters": completed, "total_chapters": total, "percent": percent}


def collect_status(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or _repo_root()

    paused = is_paused(root)
    lock = lock_status(root)
    if not lock["exists"]:
        lock_state = "absent"
    elif lock["alive"]:
        lock_state = "held"
    else:
        lock_state = "stale"

    registry = _load_registry()
    registry_state = root / REGISTRY_STATE_REL
    active_workers = registry.find_active_workers(state_path=registry_state)
    orphan_workers = registry.find_orphan_api_workers(state_path=registry_state)

    total_chapters = _count_total_chapters(root)
    done = _completed_chapters_by_phase(root)
    draft_done = {ch for ch in done["draft"] if 1 <= ch <= total_chapters}
    refine_done = {ch for ch in done["refine"] if 1 <= ch <= total_chapters}

    queue = _queue_config(root)
    target = _next_draft_target(draft_done, total_chapters, queue["anchor"], queue["per_round"])

    if paused:
        next_task = "paused"
    elif not target["draft_complete"]:
        next_task = "draft_gap_backfill" if target.get("gap_below_anchor") else "draft_micro_round"
    else:
        next_task = "draft_consistency_audit"  # Phase B entry; planner lands in FS-004

    current_phase = "draft" if not target["draft_complete"] else "consistency"

    tick_state = _safe_load_json(root / TICK_STATE_REL) or {}

    blocked_reasons: list[str] = []
    if paused:
        blocked_reasons.append("paused")
    if lock_state == "held":
        blocked_reasons.append("lock_held")
    elif lock_state == "stale":
        blocked_reasons.append("stale_lock")
    if orphan_workers:
        blocked_reasons.append("orphan_workers")
    if active_workers:
        blocked_reasons.append("active_workers")

    return {
        "current_phase": current_phase,
        "next_task": next_task,
        "next_round_id": target["next_round_id"],
        "next_chapter_range": target["next_chapter_range"],
        "active_worker_count": len(active_workers),
        "orphan_worker_count": len(orphan_workers),
        "scheduler_lock_status": lock_state,
        "paused": paused,
        "last_successful_tick": tick_state.get("last_successful_tick"),
        "last_blocked_reason": tick_state.get("last_blocked_reason"),
        "draft_progress": _progress_dict(len(draft_done), total_chapters),
        "refinement_progress": _progress_dict(len(refine_done), total_chapters),
        "safe_to_run": not blocked_reasons,
        "detail": {
            "generated_at": _utc_now(),
            "blocked_reasons": blocked_reasons,
            "missing_draft_chapters": target["missing_chapter_count"],
            "dmr_anchor_chapter": queue["anchor"],
            "chapters_per_round": queue["per_round"],
            "lock_holder": lock["holder"],
        },
    }
