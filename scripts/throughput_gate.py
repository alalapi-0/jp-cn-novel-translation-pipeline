#!/usr/bin/env python3
"""Throughput safety gate — read-only checks before production resume."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from translation.run_progress import (  # noqa: E402
    classify_run_recovery,
    safe_load_json,
)

# Import registry from scripts
import importlib.util

_registry_spec = importlib.util.spec_from_file_location(
    "pipeline_worker_registry",
    REPO_ROOT / "scripts" / "pipeline_worker_registry.py",
)
assert _registry_spec and _registry_spec.loader
_registry = importlib.util.module_from_spec(_registry_spec)
_registry_spec.loader.exec_module(_registry)


WORKSPACE = REPO_ROOT / "workspace"
DECISION_ALLOW = "ALLOW"
DECISION_WARN = "WARN"
DECISION_BLOCK = "BLOCK"


def _pid_alive(pid: int) -> bool:
    return _registry.pid_alive(pid)


def _read_lock_pid(lock_path: Path) -> int | None:
    if not lock_path.is_file():
        return None
    try:
        return int(lock_path.read_text(encoding="utf-8").strip().splitlines()[0])
    except (ValueError, IndexError, OSError):
        return None


def _count_exportable_chapters() -> int:
    runs_root = WORKSPACE / "runs"
    if not runs_root.is_dir():
        return 0
    exportable = 0
    for meta_path in sorted(runs_root.glob("run_*_draft_stage_b_50ch/run_metadata.json")):
        run_root = meta_path.parent
        seg_path = run_root / "segments.json"
        if not seg_path.is_file():
            continue
        doc = json.loads(seg_path.read_text(encoding="utf-8"))
        for ch in doc.get("chapters", []):
            segs = ch.get("segments", [])
            if not segs:
                continue
            skip = False
            for s in segs:
                status = str(s.get("status") or s.get("refine_status") or "")
                if status in {"validation_failed", "failed", "retry_pending"}:
                    skip = True
                    break
                draft = (s.get("draft_text") or "").strip()
                refined = (s.get("refined_text") or "").strip()
                if not draft or not refined:
                    skip = True
                    break
            if not skip:
                exportable += 1
    return exportable


def _checkpoint_run_ids() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    cp_dir = WORKSPACE / "checkpoints"
    if not cp_dir.is_dir():
        return out
    for path in cp_dir.glob("*.json"):
        data = safe_load_json(path) or {}
        out[path.stem] = data
    return out


def _analyze_runs() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    checkpoints = _checkpoint_run_ids()
    runs_root = WORKSPACE / "runs"
    if not runs_root.is_dir():
        return rows
    for run_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        run_id = run_dir.name
        cp = checkpoints.get(run_id, {})
        progress = safe_load_json(run_dir / "run_progress.json") or {}
        meta = safe_load_json(run_dir / "run_metadata.json")
        segments = safe_load_json(run_dir / "segments.json")
        recovery = classify_run_recovery(
            run_id=run_id,
            checkpoint_status=str(cp.get("status") or ""),
            has_run_metadata=meta is not None,
            has_segments=segments is not None,
            has_progress=bool(progress),
            progress_status=str(progress.get("status") or ""),
        )
        rows.append(
            {
                "run_id": run_id,
                "checkpoint_status": cp.get("status"),
                "progress_status": progress.get("status"),
                "recovery_label": recovery,
                "chapter_offset": (meta or {}).get("chapter_offset"),
            }
        )
    return rows


def evaluate_gate(*, allow_diagnostic: bool = False) -> dict[str, Any]:
    warnings: list[str] = []
    blocks: list[str] = []

    registry = _registry.summarize_registry()
    active_workers = registry.get("active_workers") or []
    if len(active_workers) > 1:
        blocks.append(f"duplicate_worker: {len(active_workers)} active workers")
    elif len(active_workers) == 1:
        w = active_workers[0]
        warnings.append(
            f"active_worker: pid={w.get('pid')} task={w.get('task_type')} run_id={w.get('run_id')}"
        )

    run_rows = _analyze_runs()
    conflicts = [r for r in run_rows if r["recovery_label"] == "state_conflict"]
    missing = [r for r in run_rows if r["recovery_label"] == "recoverable_missing_artifacts"]
    in_progress = [r for r in run_rows if r["recovery_label"] == "recoverable_in_progress"]

    for row in conflicts:
        blocks.append(f"state_conflict: run_id={row['run_id']}")
    for row in missing:
        warnings.append(f"recoverable_missing_artifacts: run_id={row['run_id']}")
    for row in in_progress:
        cp = row.get("checkpoint_status") or ""
        if str(cp).startswith("in_progress"):
            warnings.append(f"recoverable_in_progress: run_id={row['run_id']}")

    stage_state = safe_load_json(WORKSPACE / "stage_state.json") or {}
    if stage_state.get("status") == "in_progress":
        ss_run = str(stage_state.get("run_id") or "")
        active_run_ids = {w.get("run_id") for w in active_workers}
        if ss_run and ss_run not in active_run_ids and not active_workers:
            warnings.append(f"stage_state_stale: points to {ss_run} without active worker")

    lock_dir = WORKSPACE / ".locks"
    if lock_dir.is_dir():
        for lock in lock_dir.glob("*.lock"):
            pid = _read_lock_pid(lock)
            if pid is not None and not _pid_alive(pid):
                warnings.append(f"stale_lock: {lock.name} pid={pid}")

    # Completed run missing artifacts
    checkpoints = _checkpoint_run_ids()
    for run_id, cp in checkpoints.items():
        if str(cp.get("status") or "").split(":")[0] != "completed":
            continue
        run_root = WORKSPACE / "runs" / run_id
        if not (run_root / "segments.json").is_file():
            blocks.append(f"completed_run_missing_artifacts: {run_id}")

    # Offset ordering: in_progress at lower offset while higher offset started
    offsets_in_progress = sorted(
        int(r["chapter_offset"])
        for r in run_rows
        if r.get("chapter_offset") is not None
        and r["recovery_label"] in {"recoverable_in_progress", "state_conflict"}
        and str(r.get("checkpoint_status") or "").startswith("in_progress")
    )
    all_offsets = sorted(
        int(r["chapter_offset"])
        for r in run_rows
        if r.get("chapter_offset") is not None
    )
    if offsets_in_progress and all_offsets:
        min_in_prog = min(offsets_in_progress)
        higher = [o for o in all_offsets if o > min_in_prog]
        if higher:
            blocks.append(
                f"offset_skip: in_progress offset={min_in_prog} but higher offsets exist"
            )

    # Cost guard presence
    if os.environ.get("MAX_TEST_COST_USD", "0") == "0":
        warnings.append("cost_guard: MAX_TEST_COST_USD=0 may block real API")

    exportable = _count_exportable_chapters()

    if blocks:
        decision = DECISION_BLOCK
        exit_code = 2
    elif warnings:
        decision = DECISION_WARN
        exit_code = 1
    else:
        decision = DECISION_ALLOW
        exit_code = 0

    if allow_diagnostic and decision == DECISION_BLOCK and not any(
        "duplicate_worker" in b for b in blocks
    ):
        warnings.append("diagnostic_override: isolated real API may proceed with caution")
        decision = DECISION_WARN
        exit_code = 1

    return {
        "decision": decision,
        "exit_code": exit_code,
        "warnings": warnings,
        "blocks": blocks,
        "active_workers": active_workers,
        "active_worker_count": len(active_workers),
        "run_analysis": run_rows,
        "exportable_chapters": exportable,
        "stage_state_status": stage_state.get("status"),
        "stage_state_run_id": stage_state.get("run_id"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Throughput safety gate")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--allow-diagnostic", action="store_true")
    args = parser.parse_args()
    result = evaluate_gate(allow_diagnostic=args.allow_diagnostic)
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"throughput_gate: {result['decision']} (exit {result['exit_code']})")
        for w in result["warnings"]:
            print(f"  WARN: {w}")
        for b in result["blocks"]:
            print(f"  BLOCK: {b}")
        print(f"  exportable_chapters={result['exportable_chapters']}")
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
