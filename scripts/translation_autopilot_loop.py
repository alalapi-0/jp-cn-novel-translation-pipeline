#!/usr/bin/env python3
"""Supervised translation autopilot — one short tick per invocation, returns control to Agent."""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from local_env import apply_local_env  # noqa: E402
from translation.stop_control import clear_stop_request  # noqa: E402
from translation.run_progress import safe_load_json  # noqa: E402

from micro_round_plan import resolve_round_plan  # noqa: E402

_registry_spec = importlib.util.spec_from_file_location(
    "pipeline_worker_registry", REPO_ROOT / "scripts" / "pipeline_worker_registry.py"
)
assert _registry_spec and _registry_spec.loader
_registry = importlib.util.module_from_spec(_registry_spec)
_registry_spec.loader.exec_module(_registry)

DEFAULT_DRAFT_MODEL = "deepseek/deepseek-v4-pro"
DEFAULT_TICK_MAX_SEGMENTS = 80
DEFAULT_TICK_MAX_WALL_SECONDS = 180.0


def _python() -> str:
    venv = REPO_ROOT / ".venv" / "bin" / "python"
    return str(venv) if venv.is_file() else sys.executable


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _production_env(controller_run_id: str, round_id: str, draft_model: str) -> dict[str, str]:
    env = os.environ.copy()
    env["REAL_API_TESTS_ENABLED"] = "1"
    env["CONTROLLED_RUN_ENABLED"] = "1"
    env["TRANSLATION_CONTROLLER_PID"] = str(os.getpid())
    env["TRANSLATION_CONTROLLER_RUN_ID"] = controller_run_id
    env["TRANSLATION_ROUND_ID"] = round_id
    if draft_model:
        env["DRAFT_MODEL"] = draft_model
    return env


def _run_gate(py: str) -> dict[str, Any]:
    proc = subprocess.run(
        [py, "scripts/throughput_gate.py", "--json"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    if not proc.stdout.strip():
        return {"decision": "BLOCK", "blocks": ["gate_empty_output"]}
    return json.loads(proc.stdout)


def _chapter_quality(doc: dict[str, Any], ch_start: int, ch_end: int) -> dict[str, Any]:
    completed: list[int] = []
    failed: list[int] = []
    validation_failed = 0
    jp_re = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")

    for ch in doc.get("chapters", []):
        ch_id = str(ch.get("chapter_id") or "")
        m = re.search(r"(\d+)", ch_id)
        if not m:
            continue
        num = int(m.group(1))
        if num < ch_start or num > ch_end:
            continue
        segs = ch.get("segments", [])
        if not segs:
            failed.append(num)
            continue
        all_draft = True
        ch_fail = False
        for s in segs:
            status = str(s.get("status") or "")
            if status in {"validation_failed", "failed"}:
                validation_failed += 1
                ch_fail = True
            if not (s.get("draft_text") or "").strip():
                all_draft = False
        if all_draft and not ch_fail:
            completed.append(num)
        else:
            failed.append(num)

    target = ch_end - ch_start + 1
    return {
        "completed_chapters": sorted(set(completed)),
        "failed_chapters": sorted(set(failed)),
        "validation_failed": validation_failed,
        "round_done": len(set(completed)) >= target and not failed,
    }


def _current_chapter_from_progress(progress: dict[str, Any]) -> str:
    last = str(progress.get("last_completed_segment_id") or "")
    m = re.match(r"ch-(\d+)-", last)
    if m:
        return f"ch-{int(m.group(1)):03d}"
    return ""


def _tick_feedback(
    *,
    round_id: str,
    plan: dict[str, Any],
    run_id: str,
    progress: dict[str, Any],
    checkpoint: dict[str, Any],
    segments_before: int,
    status: str,
    next_action: str,
) -> dict[str, Any]:
    completed = int(progress.get("completed_segments") or 0)
    total = int(progress.get("total_segments") or 0)
    return {
        "round_id": round_id,
        "run_id": run_id,
        "chapter_range": f"{plan['chapter_start']}-{plan['chapter_end']}",
        "progress": f"{completed}/{total}",
        "current_chapter": _current_chapter_from_progress(progress),
        "segments_advanced": max(0, completed - segments_before),
        "api_calls": int(checkpoint.get("api_calls") or 0),
        "cost_usd": float(checkpoint.get("spent_usd") or 0),
        "status": status,
        "next_action": next_action,
        "tick_at": _utc_now(),
    }


def run_supervised_tick(
    *,
    round_id: str,
    phase: str = "draft",
    round_size: int = 3,
    run_id_override: str = "",
    chapter_range: str = "",
    draft_model: str = "",
    model_profile: str = "",
    skip_gate: bool = False,
    tick_max_segments: int = DEFAULT_TICK_MAX_SEGMENTS,
    tick_max_wall_seconds: float = DEFAULT_TICK_MAX_WALL_SECONDS,
    auto_report_on_complete: bool = False,
) -> int:
    apply_local_env(REPO_ROOT)
    py = _python()

    plan = resolve_round_plan(
        round_id,
        round_size=round_size,
        run_id=run_id_override,
        chapter_range=chapter_range,
    )
    if not plan:
        print(f"unknown round_id={round_id}", file=sys.stderr)
        return 2

    _registry.heal_stale_workers()
    orphans = _registry.find_orphan_api_workers()
    if orphans:
        print(f"BLOCK: {len(orphans)} orphan worker(s) before tick", file=sys.stderr)
        return 2

    if not skip_gate:
        gate = _run_gate(py)
        print(f"throughput_gate: {gate.get('decision')}")
        if gate.get("decision") == "BLOCK":
            return 2
        if gate.get("orphan_workers") or _registry.find_orphan_api_workers():
            print("BLOCK: orphan API workers remain", file=sys.stderr)
            return 2

    offset = int(plan["offset"])
    limit = int(plan.get("limit") or round_size)
    run_id = (run_id_override or str(plan.get("resume_run_id") or "")).strip()
    ch_start = int(plan["chapter_start"])
    ch_end = int(plan["chapter_end"])
    controller_run_id = (
        f"autopilot_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}"
    )
    clear_stop_request(REPO_ROOT)

    segments_before = 0
    progress_path = REPO_ROOT / "workspace" / "runs" / run_id / "run_progress.json"
    if run_id and progress_path.is_file():
        prev = safe_load_json(progress_path) or {}
        segments_before = int(prev.get("completed_segments") or 0)

    env = _production_env(controller_run_id, round_id, draft_model)
    os.environ["TRANSLATION_ACTIVE_RUN_ID"] = run_id or f"stage_b_offset_{offset}"

    should_hydrate = False
    if run_id:
        prev_prog = safe_load_json(progress_path) or {}
        prev_offset = int(prev_prog.get("chapter_offset") or -1)
        prev_status = str(prev_prog.get("status") or "")
        if prev_offset != offset or prev_status in {"aborted", "pending", ""}:
            should_hydrate = True

    if run_id and should_hydrate:
        hydrate = subprocess.run(
            [
                py,
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
        if hydrate.returncode != 0:
            return hydrate.returncode

    cmd = [
        py,
        "scripts/translate.py",
        "--phase",
        phase,
        "--stage",
        "stage_b",
        "--chapter-offset",
        str(offset),
        "--limit-chapters",
        str(limit),
        "--asset-context",
        str(REPO_ROOT / "workspace/assets/translation_memory/pw-user-assets-flow.json"),
        "--stage-state-path",
        "workspace/stage_state_production.json",
        "--controller-pid",
        str(os.getpid()),
        "--controller-run-id",
        controller_run_id,
        "--round-id",
        round_id,
        "--tick-max-segments",
        str(tick_max_segments),
        "--tick-max-wall-time-seconds",
        str(tick_max_wall_seconds),
    ]
    if run_id:
        cmd.extend(["--run-id", run_id])

    profile_note = model_profile or plan.get("model_profile") or "draft_translation_primary"
    print(
        f"[autopilot tick] round={round_id} model={draft_model or DEFAULT_DRAFT_MODEL} "
        f"profile={profile_note} chapters={ch_start}-{ch_end} run_id={run_id or '(new)'}",
        flush=True,
    )
    print("+", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=REPO_ROOT, env=env)
    if proc.returncode not in {0, 3}:
        feedback = _tick_feedback(
            round_id=round_id,
            plan=plan,
            run_id=run_id,
            progress=safe_load_json(progress_path) or {},
            checkpoint={},
            segments_before=segments_before,
            status="failed",
            next_action="diagnose_and_retry",
        )
        print(json.dumps(feedback, ensure_ascii=False, indent=2))
        return proc.returncode

    if not run_id:
        run_id = _find_run_id_for_offset(offset) or ""
        progress_path = REPO_ROOT / "workspace" / "runs" / run_id / "run_progress.json"

    progress = safe_load_json(progress_path) or {}
    cp_path = REPO_ROOT / "workspace" / "checkpoints" / f"{run_id}.json"
    checkpoint = safe_load_json(cp_path) or {}
    seg_doc = safe_load_json(REPO_ROOT / "workspace" / "runs" / run_id / "segments.json") or {}
    quality = _chapter_quality(seg_doc, ch_start, ch_end)

    if quality["round_done"]:
        status = "completed"
        next_action = "generate_report"
    elif progress.get("status") in {"in_progress", "stopped_by_controller"} or proc.returncode == 0:
        status = "in_progress"
        next_action = "continue_next_tick"
    else:
        status = "failed"
        next_action = "diagnose_and_retry"

    feedback = _tick_feedback(
        round_id=round_id,
        plan=plan,
        run_id=run_id,
        progress=progress,
        checkpoint=checkpoint,
        segments_before=segments_before,
        status=status,
        next_action=next_action,
    )
    print(json.dumps(feedback, ensure_ascii=False, indent=2))

    remaining = _registry.find_orphan_api_workers()
    if remaining:
        print(f"BLOCK: orphan workers after tick: {len(remaining)}", file=sys.stderr)
        return 2

    if status == "completed" and auto_report_on_complete:
        report_cmd = [
            py,
            "scripts/generate_translation_round_report.py",
            "--round-id",
            round_id,
            "--run-id",
            run_id,
            "--chapter-range",
            f"{ch_start}-{ch_end}",
        ]
        subprocess.run(report_cmd, cwd=REPO_ROOT)

    return 0


def _find_run_id_for_offset(offset: int) -> str | None:
    runs_root = REPO_ROOT / "workspace" / "runs"
    if not runs_root.is_dir():
        return None
    for meta_path in sorted(runs_root.glob("run_*_draft_stage_b_50ch/run_metadata.json"), reverse=True):
        meta = safe_load_json(meta_path) or {}
        if int(meta.get("chapter_offset") or -1) == offset:
            return meta_path.parent.name
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Supervised translation autopilot (one tick per run)")
    parser.add_argument("--phase", choices=["draft"], default="draft")
    parser.add_argument("--round-id", default="D-MR-001")
    parser.add_argument("--round-size", type=int, default=3)
    parser.add_argument("--run-id", default="", help="Override resume run_id")
    parser.add_argument("--chapter-range", default="", help="Override chapter range e.g. 203-205")
    parser.add_argument("--model-profile", default="draft_translation_primary")
    parser.add_argument("--real-api", action="store_true", default=True)
    parser.add_argument("--supervised", action="store_true", default=True)
    parser.add_argument("--auto-resume", action="store_true", default=True)
    parser.add_argument("--auto-report-on-complete", action="store_true")
    parser.add_argument("--draft-model", default=DEFAULT_DRAFT_MODEL)
    parser.add_argument("--tick-max-segments", type=int, default=DEFAULT_TICK_MAX_SEGMENTS)
    parser.add_argument("--tick-max-wall-time-seconds", type=float, default=DEFAULT_TICK_MAX_WALL_SECONDS)
    parser.add_argument("--skip-gate", action="store_true")
    args = parser.parse_args()

    if not args.supervised:
        print("ERROR: --supervised is required for real API production", file=sys.stderr)
        return 2

    draft_model = (args.draft_model or DEFAULT_DRAFT_MODEL).strip()
    return run_supervised_tick(
        round_id=args.round_id,
        phase=args.phase,
        round_size=args.round_size,
        run_id_override=args.run_id.strip(),
        chapter_range=args.chapter_range.strip(),
        draft_model=draft_model,
        model_profile=args.model_profile,
        skip_gate=args.skip_gate,
        tick_max_segments=args.tick_max_segments,
        tick_max_wall_seconds=args.tick_max_wall_time_seconds,
        auto_report_on_complete=args.auto_report_on_complete,
    )


if __name__ == "__main__":
    raise SystemExit(main())
