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
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from local_env import apply_local_env  # noqa: E402
from translation.run_progress import (  # noqa: E402
    classify_run_recovery,
    is_diagnostic_run_id,
    production_stage_state_path,
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


def _iter_stage_b_runs() -> list[Path]:
    runs_root = WORKSPACE / "runs"
    if not runs_root.is_dir():
        return []
    return sorted(p.parent for p in runs_root.glob("run_*_draft_stage_b_50ch/run_metadata.json"))


def _chapter_metrics_from_doc(doc: dict[str, Any]) -> tuple[int, int]:
    """Return (draft_completed_chapters, refined_exportable_chapters)."""
    draft_done = 0
    refined_exportable = 0
    for ch in doc.get("chapters", []):
        segs = ch.get("segments", [])
        if not segs:
            continue
        has_draft_fail = False
        has_refine_fail = False
        all_draft = True
        all_refined = True
        for s in segs:
            status = str(s.get("status") or s.get("refine_status") or "")
            if status in {"validation_failed", "failed", "retry_pending"}:
                has_draft_fail = True
                has_refine_fail = True
            draft = (s.get("draft_text") or "").strip()
            refined = (s.get("refined_text") or "").strip()
            if not draft:
                all_draft = False
            if not draft or not refined:
                all_refined = False
        if all_draft and not has_draft_fail:
            draft_done += 1
        if all_refined and not has_refine_fail:
            refined_exportable += 1
    return draft_done, refined_exportable


def _count_chapter_metrics() -> tuple[int, int]:
    draft_total = 0
    refined_total = 0
    for run_root in _iter_stage_b_runs():
        seg_path = run_root / "segments.json"
        if not seg_path.is_file():
            continue
        doc = json.loads(seg_path.read_text(encoding="utf-8"))
        draft_done, refined_exportable = _chapter_metrics_from_doc(doc)
        draft_total += draft_done
        refined_total += refined_exportable
    return draft_total, refined_total


def _count_exportable_chapters() -> int:
    _, refined = _count_chapter_metrics()
    return refined


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
        if is_diagnostic_run_id(run_id):
            continue
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


def _build_fix_paths(
    *,
    blocks: list[str],
    warnings: list[str],
    missing_runs: list[dict[str, Any]],
) -> list[str]:
    steps: list[str] = []
    if any("missing_api_key" in w or "cost_guard" in w for w in warnings + blocks):
        steps.append("在 .env 填入 OPENROUTER_API_KEY（非空），并设置 REAL_API_TESTS_ENABLED=true、MAX_TEST_COST_USD=2.0")
        steps.append("验证: python3 scripts/run_real_api_smoke.py --status-only --json")
    for row in missing_runs:
        rid = row.get("run_id")
        if rid:
            steps.append(
                f"恢复缺失产物: python3 scripts/hydrate_checkpoint.py --run-id {rid} --apply"
            )
            steps.append(
                f"续跑翻译: python3 scripts/resume_production.py --run-id {rid} --hydrate-apply"
            )
    if any("state_conflict" in b for b in blocks):
        steps.append(
            "诊断 run 冲突: 确认 workspace/stage_state.json 为测试状态；"
            "生产请用 workspace/stage_state_production.json（见 scripts/resume_production.py）"
        )
    if any("completed_run_missing_artifacts" in b for b in blocks):
        steps.append(
            "孤立 completed checkpoint（如 round_50_e2e）可移至 workspace/checkpoints/archive/ 或忽略（诊断 run）"
        )
    if any("orphan_api_worker" in w for w in warnings + blocks):
        steps.append(
            "停止 orphan worker: python3 scripts/pipeline_worker_registry.py "
            "--request-stop --run-id <run_id> --json"
        )
        steps.append(
            "受控续跑: python3 scripts/translation_autopilot_loop.py --round-id T-00X --supervised"
        )
    if any("stale_lock" in w for w in warnings):
        steps.append(
            "清理过期 worker 锁（推荐）：python3 scripts/pipeline_worker_registry.py --heal --json"
        )
        steps.append(
            "或手动删除 workspace/.locks/ 下对应 .lock（确认无活跃 translate/refine 进程后）"
        )
    if any("duplicate_worker" in w for w in warnings):
        steps.append(
            "检测到多个活跃 worker（保护性 WARN，非硬阻塞）："
            "确认无重复 translate/refine 后运行 "
            "python3 scripts/pipeline_worker_registry.py --heal --json"
        )
    if not steps and blocks:
        steps.append("查看 blocks/warnings 详情后手动修复，勿绕过 gate 直接跑真实 API")
    return steps


def evaluate_gate(*, allow_diagnostic: bool = False) -> dict[str, Any]:
    apply_local_env(REPO_ROOT)
    warnings: list[str] = []
    blocks: list[str] = []

    registry = _registry.summarize_registry()
    active_workers = registry.get("active_workers") or []
    orphan_workers = registry.get("orphan_workers") or _registry.find_orphan_api_workers()
    soft_blocks: list[str] = []
    if orphan_workers:
        for ow in orphan_workers:
            warnings.append(
                f"orphan_api_worker: pid={ow.get('pid')} run_id={ow.get('run_id')} "
                f"reason={ow.get('orphan_reason')}"
            )
        blocks.append(f"orphan_api_worker_count: {len(orphan_workers)}")
    if len(active_workers) > 1:
        soft_blocks.append(f"duplicate_worker: {len(active_workers)} active workers")
    elif len(active_workers) == 1 and not orphan_workers:
        w = active_workers[0]
        warnings.append(
            f"active_worker: pid={w.get('pid')} task={w.get('task_type')} run_id={w.get('run_id')}"
        )

    run_rows = _analyze_runs()
    conflicts = [r for r in run_rows if r["recovery_label"] == "state_conflict"]
    missing = [r for r in run_rows if r["recovery_label"] == "recoverable_missing_artifacts"]
    in_progress = [r for r in run_rows if r["recovery_label"] == "recoverable_in_progress"]

    for row in conflicts:
        rid = str(row["run_id"])
        if is_diagnostic_run_id(rid):
            warnings.append(f"diagnostic_state_conflict: run_id={rid}")
        else:
            blocks.append(f"state_conflict: run_id={rid}")
    for row in missing:
        warnings.append(f"recoverable_missing_artifacts: run_id={row['run_id']}")
    for row in in_progress:
        cp = row.get("checkpoint_status") or ""
        if str(cp).startswith("in_progress"):
            warnings.append(f"recoverable_in_progress: run_id={row['run_id']}")

    prod_stage_path = production_stage_state_path(REPO_ROOT)
    stage_state = safe_load_json(prod_stage_path) or safe_load_json(WORKSPACE / "stage_state.json") or {}
    stage_state_source = (
        "production" if prod_stage_path.is_file() else "default"
    )
    if stage_state.get("status") == "in_progress":
        ss_run = str(stage_state.get("run_id") or "")
        active_run_ids = {w.get("run_id") for w in active_workers}
        if ss_run and ss_run not in active_run_ids and not active_workers:
            warnings.append(f"stage_state_stale: points to {ss_run} without active worker")
    if (
        stage_state.get("refine_blocked")
        and str(stage_state.get("phase") or "") == "draft"
        and stage_state.get("status") == "completed"
    ):
        warnings.append(
            f"refine_pending: {stage_state_source} draft completed but refine not started "
            f"(run_id={stage_state.get('run_id')})"
        )
    elif (
        stage_state.get("refine_blocked")
        and str(stage_state.get("phase") or "") == "refine"
        and stage_state.get("status") == "in_progress"
    ):
        remaining = (stage_state.get("summary") or {}).get("remaining_refine_segments")
        hint = f", remaining≈{remaining}" if remaining is not None else ""
        warnings.append(
            f"refine_in_progress: {stage_state_source} refine batch done, more segments pending"
            f"{hint} (run_id={stage_state.get('run_id')})"
        )
    diag_run = str(stage_state.get("run_id") or "")
    if stage_state_source == "default" and is_diagnostic_run_id(diag_run):
        warnings.append(
            f"stage_state_diagnostic: workspace/stage_state.json 指向测试 run {diag_run}；"
            "生产续跑请用 --stage-state-path workspace/stage_state_production.json"
        )

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
        if is_diagnostic_run_id(run_id):
            warnings.append(f"diagnostic_completed_checkpoint: {run_id}")
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

    # Cost guard / API key (after .env load)
    has_key = bool(os.environ.get("OPENROUTER_API_KEY", "").strip())
    max_cost = float(os.environ.get("MAX_TEST_COST_USD", "0") or "0")
    if not has_key:
        warnings.append("missing_api_key: OPENROUTER_API_KEY 未配置或为空（.env 中勿留 OPENROUTER_API_KEY= 空行）")
    if max_cost <= 0:
        warnings.append("cost_guard: MAX_TEST_COST_USD=0 may block real API")

    draft_completed, refined_exportable = _count_chapter_metrics()
    exportable = refined_exportable
    fix_paths = _build_fix_paths(blocks=blocks, warnings=warnings, missing_runs=missing)

    if blocks:
        decision = DECISION_BLOCK
        exit_code = 2
    elif soft_blocks or warnings:
        decision = DECISION_WARN
        exit_code = 1
        for sb in soft_blocks:
            warnings.append(sb)
    else:
        decision = DECISION_ALLOW
        exit_code = 0

    if allow_diagnostic and decision == DECISION_BLOCK:
        warnings.append("diagnostic_override: isolated real API may proceed with caution")
        decision = DECISION_WARN
        exit_code = 1

    return {
        "decision": decision,
        "exit_code": exit_code,
        "warnings": warnings,
        "blocks": blocks,
        "soft_blocks": soft_blocks,
        "hard_blocks": blocks,
        "active_workers": active_workers,
        "active_worker_count": len(active_workers),
        "orphan_workers": orphan_workers,
        "orphan_worker_count": len(orphan_workers),
        "run_analysis": run_rows,
        "exportable_chapters": exportable,
        "draft_completed_chapters": draft_completed,
        "refined_exportable_chapters": refined_exportable,
        "stage_state_status": stage_state.get("status"),
        "stage_state_run_id": stage_state.get("run_id"),
        "stage_state_source": stage_state_source,
        "has_api_key": has_key,
        "max_test_cost_usd": max_cost,
        "fix_paths": fix_paths,
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
        print(
            f"  draft_completed_chapters={result['draft_completed_chapters']} "
            f"refined_exportable_chapters={result['refined_exportable_chapters']}"
        )
    return int(result["exit_code"])


if __name__ == "__main__":
    raise SystemExit(main())
