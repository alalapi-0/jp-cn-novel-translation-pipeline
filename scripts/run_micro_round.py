#!/usr/bin/env python3
"""Supervised micro-round runner — internal batch loop, compact progress, single Agent handoff."""

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from local_env import apply_local_env  # noqa: E402
from micro_round_plan import resolve_round_plan  # noqa: E402
from plan_translation_batches import plan_batches, resolve_plan_segments  # noqa: E402
from translation.draft_runner import (  # noqa: E402
    DraftRunTickExit,
    RunBudget,
    run_draft_stage_b,
)
from translation.run_progress import safe_load_json, update_stage_state_if_newer  # noqa: E402
from translation.stop_control import StopRequested, check_stop_or_raise, clear_stop_request, install_signal_handlers  # noqa: E402

_registry_spec = importlib.util.spec_from_file_location(
    "pipeline_worker_registry", REPO_ROOT / "scripts" / "pipeline_worker_registry.py"
)
assert _registry_spec and _registry_spec.loader
_registry = importlib.util.module_from_spec(_registry_spec)
_registry_spec.loader.exec_module(_registry)

DEFAULT_DRAFT_MODEL = "deepseek/deepseek-v4-pro"
DEFAULT_ASSET_CONTEXT = REPO_ROOT / "workspace/assets/translation_memory/pw-user-assets-flow.json"
STAGE_STATE_PRODUCTION = REPO_ROOT / "workspace/stage_state_production.json"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _python() -> str:
    venv = REPO_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


def _run_gate() -> dict[str, Any]:
    proc = __import__("subprocess").run(
        [_python(), "scripts/throughput_gate.py", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if not proc.stdout.strip():
        return {"decision": "BLOCK", "blocks": ["gate_empty_output"]}
    return json.loads(proc.stdout)


def _translate_lock_path(stage: str, run_id: str) -> Path:
    key = run_id.strip() if run_id.strip() else f"{stage}_default"
    return REPO_ROOT / "workspace" / ".locks" / f"translate_{stage}_{key}.lock"


def _acquire_translate_lock(stage: str, run_id: str) -> int:
    lock_path = _translate_lock_path(stage, run_id)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return -1
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()}\n".encode())
    return fd


def _release_translate_lock(fd: int, stage: str = "", run_id: str = "") -> int:
    if fd < 0:
        return -1
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    except OSError:
        pass
    try:
        os.close(fd)
    except OSError:
        pass
    # Remove the residue file so monitoring never sees a dead-pid lock
    # (FS-008; same pattern as refine_stage_c in FS-006). flock dies with
    # the process; supervised micro rounds are single-worker by contract.
    if stage:
        _translate_lock_path(stage, run_id).unlink(missing_ok=True)
    return -1


def _production_env(
    controller_run_id: str,
    round_id: str,
    draft_model: str,
    *,
    real_api: bool = True,
) -> dict[str, str]:
    env = os.environ.copy()
    if real_api:
        env["REAL_API_TESTS_ENABLED"] = "1"
    else:
        env.pop("REAL_API_TESTS_ENABLED", None)
    env["CONTROLLED_RUN_ENABLED"] = "1"
    env["TRANSLATION_CONTROLLER_PID"] = str(os.getpid())
    env["TRANSLATION_CONTROLLER_RUN_ID"] = controller_run_id
    env["TRANSLATION_ROUND_ID"] = round_id
    if draft_model:
        env["DRAFT_MODEL"] = draft_model
    env["MODEL_ROUTER_DEFAULT_PROFILE"] = "draft_translation"
    return env


def _hydrate_if_needed(
    run_id: str,
    offset: int,
    limit: int,
    env: dict[str, str],
) -> int:
    progress_path = REPO_ROOT / "workspace" / "runs" / run_id / "run_progress.json"
    checkpoint_path = REPO_ROOT / "workspace" / "checkpoints" / f"{run_id}.json"
    prev = safe_load_json(progress_path) or {}
    prev_offset = int(prev.get("chapter_offset") or -1)
    prev_status = str(prev.get("status") or "")
    if prev_offset == offset and prev_status not in {"aborted", "pending", ""}:
        return 0
    # Fresh micro-round run: no prior checkpoint/progress — draft_runner initializes artifacts.
    if not checkpoint_path.is_file() and not progress_path.is_file():
        return 0
    if prev_offset >= 0 and prev_offset != offset:
        # Redirecting an existing run to a different chapter window rewrites
        # its history (FS-008 incident: legacy run's ch209-211 records were
        # destroyed by a 206-208 rehydrate; FS-002 lost ch191-208 the same
        # way). A run directory is single-window: resume must be same-offset,
        # anything else needs a fresh run_id.
        print(
            f"hydrate refused: run {run_id} holds offset={prev_offset} "
            f"(status={prev_status}); requested offset={offset} would rewrite history",
            file=sys.stderr,
        )
        return 1
    proc = __import__("subprocess").run(
        [
            _python(),
            "scripts/hydrate_checkpoint.py",
            "--run-id",
            run_id,
            "--chapter-offset",
            str(offset),
            "--limit-chapters",
            str(limit),
            "--json",
            "--apply",
        ],
        cwd=REPO_ROOT,
        env=env,
    )
    return proc.returncode


def _chapter_quality(doc: dict[str, Any], ch_start: int, ch_end: int) -> dict[str, Any]:
    import re

    completed: list[int] = []
    failed: list[int] = []
    for ch in doc.get("chapters", []):
        m = re.search(r"(\d+)", str(ch.get("chapter_id") or ""))
        if not m:
            continue
        num = int(m.group(1))
        if num < ch_start or num > ch_end:
            continue
        segs = ch.get("segments", [])
        if not segs:
            failed.append(num)
            continue
        ok = all((s.get("draft_text") or "").strip() for s in segs)
        if ok:
            completed.append(num)
        else:
            failed.append(num)
    target = ch_end - ch_start + 1
    return {
        "completed_chapters": sorted(set(completed)),
        "round_done": len(set(completed)) >= target and not failed,
    }


def _write_metrics(round_id: str, payload: dict[str, Any]) -> Path:
    metrics_dir = REPO_ROOT / "workspace" / "diagnostics" / "micro_round_metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    safe_id = re.sub(r"[^\w\-]+", "_", round_id)
    path = metrics_dir / f"{safe_id}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return path


def _dry_run_plan(
    *,
    round_id: str,
    run_id: str,
    chapter_range: str,
    batch_token_budget: int,
    max_segments_per_call: int,
) -> dict[str, Any]:
    segments, meta = resolve_plan_segments(
        run_id=run_id,
        round_id=round_id,
        chapter_range=chapter_range,
        pending_only=bool(run_id),
    )
    plan = plan_batches(
        segments,
        token_budget=batch_token_budget,
        max_segments_per_call=max_segments_per_call,
    )
    payload = plan.to_dict(segments=segments)
    payload.update(meta)
    payload["round_id"] = round_id
    payload["mode"] = "dry_run"
    return payload


def build_compact_summary(
    *,
    round_id: str,
    plan: dict[str, Any],
    run_id: str,
    progress: dict[str, Any],
    checkpoint: dict[str, Any],
    summary_api_calls: int,
    status: str,
    run_budget: RunBudget | None,
    log_path: str = "",
) -> dict[str, Any]:
    completed = int(progress.get("completed_segments") or 0)
    total = int(progress.get("total_segments") or 0)
    api_calls = summary_api_calls or int(checkpoint.get("api_calls") or 0)
    seg_per_call = round(completed / api_calls, 2) if api_calls else 0
    payload: dict[str, Any] = {
        "round_id": round_id,
        "run_id": run_id,
        "chapter_range": f"{plan['chapter_start']}-{plan['chapter_end']}",
        "status": status,
        "progress": f"{completed}/{total}",
        "api_calls": api_calls,
        "segments_per_call_avg": seg_per_call,
        "cost_usd": float(checkpoint.get("spent_usd") or 0),
        "finished_at": _utc_now(),
    }
    if run_budget:
        payload["budget"] = {
            "max_api_calls": run_budget.max_api_calls,
            "max_segments": run_budget.max_segments,
            "max_wall_seconds": run_budget.max_wall_seconds,
            "api_calls_used": run_budget.api_calls_used,
            "segments_used": run_budget.segments_used,
        }
    if log_path:
        payload["log_path"] = log_path
    return payload


def write_final_micro_round_progress(
    run_root: Path,
    *,
    round_id: str,
    run_id: str,
    status: str,
    progress: dict[str, Any],
    checkpoint: dict[str, Any],
    summary_api_calls: int,
    run_budget: RunBudget | None,
) -> Path:
    """Synchronize the compact progress card with the authoritative run state."""
    completed = int(progress.get("completed_segments") or 0)
    total = int(progress.get("total_segments") or 0)
    api_calls = summary_api_calls or int(checkpoint.get("api_calls") or 0)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "run_id": run_id,
        "round_id": round_id,
        "status": status,
        "progress": f"{completed}/{total}",
        "api_calls": api_calls,
        "cost_usd": round(float(checkpoint.get("spent_usd") or 0), 6),
        "segments_per_call": round(completed / api_calls, 2) if api_calls else 0,
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
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def run_micro_round(
    *,
    phase: str = "draft",
    round_id: str = "D-MR-003",
    chapter_range: str = "",
    run_id: str = "",
    model_profile: str = "draft_translation_primary",
    batch_token_budget: int = 12_000,
    max_segments_per_call: int = 30,
    max_api_calls: int = 0,
    max_segments: int = 0,
    max_wall_time_minutes: float = 0,
    progress_interval_seconds: float = 30,
    resume_from_checkpoint: bool = True,
    real_api: bool = True,
    fake_provider: bool = False,
    dry_run: bool = False,
    diagnostic_only: bool = False,
    stop_on_round_complete: bool = True,
    supervised: bool = True,
    skip_gate: bool = False,
    draft_model: str = DEFAULT_DRAFT_MODEL,
) -> tuple[int, dict[str, Any]]:
    if phase != "draft":
        return 2, {"error": "only draft phase supported"}
    if not supervised:
        return 2, {"error": "--supervised required"}

    apply_local_env(REPO_ROOT)

    if dry_run:
        payload = _dry_run_plan(
            round_id=round_id,
            run_id=run_id.strip(),
            chapter_range=chapter_range.strip(),
            batch_token_budget=batch_token_budget,
            max_segments_per_call=max_segments_per_call,
        )
        metrics_path = _write_metrics(round_id, payload)
        payload["metrics_path"] = str(metrics_path.relative_to(REPO_ROOT))
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0, payload

    install_signal_handlers()
    clear_stop_request(REPO_ROOT)

    plan = resolve_round_plan(round_id, run_id=run_id, chapter_range=chapter_range)
    if not plan:
        return 2, {"error": f"unknown round_id={round_id}"}

    _registry.heal_stale_workers()
    if _registry.find_orphan_api_workers():
        return 2, {"error": "orphan workers present"}

    use_real_api = real_api and not fake_provider
    if diagnostic_only:
        skip_gate = True
    if not skip_gate and use_real_api:
        gate = _run_gate()
        if gate.get("decision") == "BLOCK":
            return 2, {"error": "throughput_gate BLOCK", "gate": gate}

    offset = int(plan["offset"])
    limit = int(plan.get("limit") or 3)
    ch_start = int(plan["chapter_start"])
    ch_end = int(plan["chapter_end"])
    explicit_run_id = run_id.strip()
    run_id = explicit_run_id or str(plan.get("resume_run_id") or "").strip()
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    if fake_provider or diagnostic_only:
        if not explicit_run_id or not explicit_run_id.startswith("micro_validate"):
            run_id = f"micro_validate_{ts}"
    elif not run_id:
        run_id = f"run_{ts}_draft_stage_b_50ch"

    controller_run_id = f"micro_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    env = _production_env(controller_run_id, round_id, draft_model, real_api=use_real_api)
    for key, val in env.items():
        os.environ[key] = val
    if fake_provider:
        os.environ.pop("REAL_API_TESTS_ENABLED", None)

    if resume_from_checkpoint and run_id and not diagnostic_only and not fake_provider:
        rc = _hydrate_if_needed(run_id, offset, limit, env)
        if rc != 0:
            return rc, {"error": "hydrate_checkpoint failed", "run_id": run_id}

    run_budget = RunBudget(
        max_api_calls=max_api_calls,
        max_segments=max_segments,
        max_wall_seconds=max_wall_time_minutes * 60 if max_wall_time_minutes > 0 else 0,
        progress_interval_seconds=progress_interval_seconds,
    )
    os.environ["MICRO_ROUND_MAX_API_CALLS"] = str(max_api_calls or 0)
    os.environ["MICRO_ROUND_MAX_SEGMENTS"] = str(max_segments or 0)
    os.environ["MICRO_ROUND_MAX_WALL_SECONDS"] = str(run_budget.max_wall_seconds or 0)
    os.environ["MICRO_ROUND_PROGRESS_INTERVAL"] = str(progress_interval_seconds)

    log_dir = REPO_ROOT / "workspace" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"micro_round_{round_id}_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.log"

    lock_fd = _acquire_translate_lock("stage_b", run_id)
    if lock_fd < 0:
        return 2, {"error": f"translate lock busy for run_id={run_id}"}

    worker, reason = _registry.register_worker(
        task_type="translate",
        stage="stage_b",
        run_id=run_id,
        chapter_offset=offset,
        controller_pid=os.getpid(),
        controller_run_id=controller_run_id,
        round_id=round_id,
        chapter_range=f"{ch_start}-{ch_end}",
        provider="fake" if fake_provider else "model_router",
        model=draft_model if use_real_api else "fake-model-v1",
        stop_policy="stop_when_controller_exits",
    )
    if worker is None:
        _release_translate_lock(lock_fd, "stage_b", run_id)
        return 2, {"error": reason or "register_worker failed"}

    worker_id = worker["worker_id"]

    def heartbeat() -> None:
        check_stop_or_raise(worker_id=worker_id, run_id=run_id, repo_root=REPO_ROOT)
        _registry.heartbeat_worker(worker_id)

    asset_path = DEFAULT_ASSET_CONTEXT if DEFAULT_ASSET_CONTEXT.is_file() else None
    exit_code = 0
    status = "failed"
    summary_api_calls = 0

    try:
        if use_real_api and not diagnostic_only:
            update_stage_state_if_newer(
                REPO_ROOT,
                {
                    "phase": "draft",
                    "stage": "draft_stage_b_50ch",
                    "status": "in_progress",
                    "run_id": run_id,
                    "updated_at": _utc_now(),
                    "refine_blocked": True,
                    "summary": {"chapter_offset": offset, "limit_chapters": limit},
                },
                run_id=run_id,
                state_path=STAGE_STATE_PRODUCTION,
            )

        while True:
            heartbeat()
            try:
                summary, run_root = run_draft_stage_b(
                    repo_root=REPO_ROOT,
                    input_dir=REPO_ROOT / "input_jp",
                    limit_chapters=limit,
                    chapter_offset=offset,
                    run_id=run_id,
                    asset_context_path=asset_path,
                    heartbeat_cb=heartbeat,
                    worker_id=worker_id,
                    tick_max_segments=0,
                    tick_max_wall_seconds=0,
                    batch_token_budget=batch_token_budget,
                    max_segments_per_call=max_segments_per_call,
                    compact_context=True,
                    run_budget=run_budget,
                )
                summary_api_calls = summary.api_calls
                if summary.aborted:
                    status = "failed"
                    break
                status = "completed"
                break
            except DraftRunTickExit as tick_exit:
                summary_api_calls = tick_exit.summary.api_calls
                progress_path = tick_exit.run_root / "run_progress.json"
                progress = safe_load_json(progress_path) or {}
                seg_doc = safe_load_json(tick_exit.run_root / "segments.json") or {}
                quality = _chapter_quality(seg_doc, ch_start, ch_end)
                if stop_on_round_complete and quality["round_done"]:
                    status = "completed"
                    break
                if run_budget.exhausted():
                    status = "budget_exhausted"
                    break
                if progress.get("status") == "in_progress":
                    status = "in_progress"
                    time.sleep(0.5)
                    continue
                status = "paused"
                break
            except StopRequested as exc:
                status = "stopped_by_controller"
                exit_code = 3
                _registry.unregister_worker(worker_id, status=status)
                return exit_code, {"error": str(exc), "run_id": run_id}
    except Exception as exc:
        _registry.unregister_worker(worker_id, status="failed")
        return 2, {"error": str(exc), "run_id": run_id}
    finally:
        lock_fd = _release_translate_lock(lock_fd, "stage_b", run_id)

    progress_path = REPO_ROOT / "workspace" / "runs" / run_id / "run_progress.json"
    cp_path = REPO_ROOT / "workspace" / "checkpoints" / f"{run_id}.json"
    progress = safe_load_json(progress_path) or {}
    checkpoint = safe_load_json(cp_path) or {}
    seg_doc = safe_load_json(REPO_ROOT / "workspace" / "runs" / run_id / "segments.json") or {}
    quality = _chapter_quality(seg_doc, ch_start, ch_end)
    if quality["round_done"]:
        status = "completed"
    elif status == "completed":
        # Runner returned "nothing left to do" but the target range is not
        # actually covered by this run's segments (e.g. resumed run holds a
        # different window). Refusing the false success is what surfaces
        # planner/resume bugs instead of silently skipping chapters (FS-008).
        status = "failed"

    write_final_micro_round_progress(
        REPO_ROOT / "workspace" / "runs" / run_id,
        round_id=round_id,
        run_id=run_id,
        status=status,
        progress=progress,
        checkpoint=checkpoint,
        summary_api_calls=summary_api_calls,
        run_budget=run_budget,
    )

    compact = build_compact_summary(
        round_id=round_id,
        plan=plan,
        run_id=run_id,
        progress=progress,
        checkpoint=checkpoint,
        summary_api_calls=summary_api_calls,
        status=status,
        run_budget=run_budget,
        log_path=str(log_path.relative_to(REPO_ROOT)),
    )
    if fake_provider:
        compact["provider_mode"] = "fake"
    if diagnostic_only:
        compact["diagnostic_only"] = True
    avg_batch = round(
        int(progress.get("completed_segments") or 0) / max(summary_api_calls, 1),
        2,
    ) if summary_api_calls else 0
    compact["avg_segments_per_batch"] = avg_batch
    metrics_path = _write_metrics(round_id, compact)
    compact["metrics_path"] = str(metrics_path.relative_to(REPO_ROOT))
    summary_path = REPO_ROOT / "workspace" / "logs" / f"micro_round_{round_id}_summary.json"
    summary_path.write_text(json.dumps(compact, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    compact["summary_path"] = str(summary_path.relative_to(REPO_ROOT))

    reg_status = "completed" if status == "completed" else "tick_paused" if status in {"in_progress", "budget_exhausted", "paused"} else status
    _registry.unregister_worker(worker_id, status=reg_status)

    if use_real_api and not diagnostic_only and status == "completed":
        # Final writeback: without this the production stage_state stays
        # frozen at the startup "in_progress" payload and monitoring keeps
        # flagging stage_state_stale after every finished micro round
        # (FS-006 found two such fossils; root cause fixed here in FS-008).
        update_stage_state_if_newer(
            REPO_ROOT,
            {
                "phase": "draft",
                "stage": "draft_stage_b_50ch",
                "status": "completed",
                "run_id": run_id,
                "updated_at": _utc_now(),
                "refine_blocked": True,
                "summary": {
                    "chapter_offset": offset,
                    "limit_chapters": limit,
                    "total_segments": int(progress.get("total_segments") or 0),
                    "translated_segments": int(progress.get("completed_segments") or 0),
                    "api_calls": summary_api_calls,
                    "spent_usd": float(checkpoint.get("spent_usd") or 0),
                },
            },
            run_id=run_id,
            state_path=STAGE_STATE_PRODUCTION,
        )

    orphans = _registry.find_orphan_api_workers()
    if orphans:
        compact["orphan_warning"] = len(orphans)

    print(json.dumps(compact, ensure_ascii=False, indent=2))
    return (0 if status == "completed" else 0, compact)


def main() -> int:
    parser = argparse.ArgumentParser(description="Supervised micro-round translation runner")
    parser.add_argument("--phase", choices=["draft"], default="draft")
    parser.add_argument("--round-id", default="D-MR-003")
    parser.add_argument("--chapter-range", default="")
    parser.add_argument("--run-id", default="")
    parser.add_argument("--model-profile", default="draft_translation_primary")
    parser.add_argument("--real-api", action="store_true", default=True)
    parser.add_argument("--no-real-api", action="store_false", dest="real_api")
    parser.add_argument("--fake-provider", action="store_true", help="Use fake provider (no network)")
    parser.add_argument("--dry-run", action="store_true", help="Batch plan only; no worker/API")
    parser.add_argument("--diagnostic-only", action="store_true", help="Isolated validate run_id; skip gate")
    parser.add_argument("--stop-on-round-complete", action="store_true", default=True)
    parser.add_argument("--no-stop-on-round-complete", action="store_false", dest="stop_on_round_complete")
    parser.add_argument("--supervised", action="store_true", default=True)
    parser.add_argument("--batch-token-budget", type=int, default=12_000)
    parser.add_argument("--max-segments-per-call", type=int, default=30)
    parser.add_argument("--max-api-calls", type=int, default=0)
    parser.add_argument("--max-segments", type=int, default=0)
    parser.add_argument("--max-wall-time-minutes", type=float, default=0)
    parser.add_argument("--progress-interval-seconds", type=float, default=30)
    parser.add_argument("--resume-from-checkpoint", action="store_true", default=True)
    parser.add_argument("--no-resume-from-checkpoint", action="store_false", dest="resume_from_checkpoint")
    parser.add_argument("--draft-model", default=DEFAULT_DRAFT_MODEL)
    parser.add_argument("--skip-gate", action="store_true")
    args = parser.parse_args()

    code, payload = run_micro_round(
        phase=args.phase,
        round_id=args.round_id,
        chapter_range=args.chapter_range,
        run_id=args.run_id.strip(),
        model_profile=args.model_profile,
        batch_token_budget=args.batch_token_budget,
        max_segments_per_call=args.max_segments_per_call,
        max_api_calls=args.max_api_calls,
        max_segments=args.max_segments,
        max_wall_time_minutes=args.max_wall_time_minutes,
        progress_interval_seconds=args.progress_interval_seconds,
        resume_from_checkpoint=args.resume_from_checkpoint,
        real_api=args.real_api,
        fake_provider=args.fake_provider,
        dry_run=args.dry_run,
        diagnostic_only=args.diagnostic_only,
        stop_on_round_complete=args.stop_on_round_complete,
        supervised=args.supervised,
        skip_gate=args.skip_gate,
        draft_model=args.draft_model.strip() or DEFAULT_DRAFT_MODEL,
    )
    if code != 0 and payload.get("error"):
        print(json.dumps(payload, ensure_ascii=False, indent=2), file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
