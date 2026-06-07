#!/usr/bin/env python3
"""Controlled translation CLI: draft Stage A/B (bounded chapters)."""

from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from local_env import apply_local_env  # noqa: E402

from translation.draft_runner import (  # noqa: E402
    STAGE_A_MAX_CHAPTERS,
    STAGE_B_MAX_CHAPTERS,
    run_draft_stage_a,
    run_draft_stage_b,
)
from translation.run_progress import update_stage_state_if_newer  # noqa: E402
from translation.stop_control import StopRequested, check_stop_or_raise, clear_stop_request, install_signal_handlers  # noqa: E402

_registry_spec = importlib.util.spec_from_file_location(
    "pipeline_worker_registry",
    REPO_ROOT / "scripts" / "pipeline_worker_registry.py",
)
assert _registry_spec and _registry_spec.loader
_registry = importlib.util.module_from_spec(_registry_spec)
_registry_spec.loader.exec_module(_registry)

STAGE_STATE_MAP = {
    "stage_a": "draft_stage_a_5ch",
    "stage_b": "draft_stage_b_50ch",
}


def _acquire_translate_lock(stage: str, run_id: str) -> int:
    """Non-blocking exclusive lock for one stage/run translate process."""
    lock_dir = REPO_ROOT / "workspace" / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    key = run_id.strip() if run_id.strip() else f"{stage}_default"
    lock_path = lock_dir / f"translate_{stage}_{key}.lock"
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        print(
            f"translate.py already running for stage={stage} run_id={key} (lock: {lock_path})",
            file=sys.stderr,
        )
        return -1
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()}\n".encode())
    return fd


def _release_translate_lock(fd: int) -> None:
    if fd < 0:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _update_stage_state(
    repo_root: Path,
    stage: str,
    run_id: str,
    status: str,
    summary: dict,
    *,
    state_path: Path | None = None,
) -> None:
    payload = {
        "phase": "draft",
        "stage": STAGE_STATE_MAP[stage],
        "status": status,
        "run_id": run_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "refine_blocked": True,
        "summary": summary,
    }
    update_stage_state_if_newer(repo_root, payload, run_id=run_id, state_path=state_path)


def main() -> int:
    parser = argparse.ArgumentParser(description="Controlled novel translation")
    parser.add_argument("--phase", choices=["draft"], required=True)
    parser.add_argument("--stage", choices=["stage_a", "stage_b"], required=True)
    parser.add_argument("--limit-chapters", type=int, default=None)
    parser.add_argument("--input-dir", type=Path, default=REPO_ROOT / "input_jp")
    parser.add_argument("--run-id", default="")
    parser.add_argument(
        "--chapter-offset",
        type=int,
        default=0,
        help="Skip first N sorted chapter files (for continuing full-novel batches)",
    )
    parser.add_argument(
        "--asset-context",
        type=Path,
        default=None,
        help="Translation-memory asset JSON to include in restart/retry prompt context.",
    )
    parser.add_argument(
        "--stage-state-path",
        type=Path,
        default=None,
        help="Write stage_state to this path (default: workspace/stage_state.json)",
    )
    parser.add_argument("--controller-pid", type=int, default=0)
    parser.add_argument("--controller-run-id", default="")
    parser.add_argument("--round-id", default="")
    parser.add_argument(
        "--tick-max-segments",
        type=int,
        default=0,
        help="Supervised tick: stop after translating this many segments (0=unlimited).",
    )
    parser.add_argument(
        "--tick-max-wall-time-seconds",
        type=float,
        default=0,
        help="Supervised tick: stop after this many wall-clock seconds (0=unlimited).",
    )
    args = parser.parse_args()
    apply_local_env(REPO_ROOT)
    install_signal_handlers()
    clear_stop_request(REPO_ROOT)
    controller_pid = int(args.controller_pid or os.environ.get("TRANSLATION_CONTROLLER_PID", "0") or 0)
    controller_run_id = (args.controller_run_id or os.environ.get("TRANSLATION_CONTROLLER_RUN_ID", "")).strip()
    round_id = (args.round_id or os.environ.get("TRANSLATION_ROUND_ID", "")).strip()
    stage_state_path = args.stage_state_path
    input_dir = args.input_dir if args.input_dir.is_absolute() else (REPO_ROOT / args.input_dir)

    if args.phase != "draft":
        print("Only draft phase is implemented", file=sys.stderr)
        return 2

    if args.stage == "stage_a":
        limit = args.limit_chapters if args.limit_chapters is not None else STAGE_A_MAX_CHAPTERS
        if limit > STAGE_A_MAX_CHAPTERS:
            print(f"Hard limit: max {STAGE_A_MAX_CHAPTERS} chapters per Stage A run", file=sys.stderr)
            return 2
        run_fn = run_draft_stage_a
    else:
        limit = args.limit_chapters if args.limit_chapters is not None else STAGE_B_MAX_CHAPTERS
        if limit > STAGE_B_MAX_CHAPTERS:
            print(f"Hard limit: max {STAGE_B_MAX_CHAPTERS} chapters per Stage B run", file=sys.stderr)
            return 2
        run_fn = run_draft_stage_b

    run_id = args.run_id.strip() or None
    lock_fd = _acquire_translate_lock(args.stage, args.run_id)
    if lock_fd < 0:
        return 2

    registry_run_id = run_id or f"{args.stage}_default"
    chapter_end = args.chapter_offset + limit
    worker, reason = _registry.register_worker(
        task_type="translate",
        stage=args.stage,
        run_id=registry_run_id,
        chapter_offset=args.chapter_offset,
        controller_pid=controller_pid,
        controller_run_id=controller_run_id,
        round_id=round_id,
        chapter_range=f"{args.chapter_offset + 1}-{chapter_end}",
        provider="model_router",
        model=os.environ.get("DRAFT_MODEL", "deepseek/deepseek-v4-pro"),
        stop_policy="stop_when_controller_exits",
    )
    if worker is None:
        print(reason, file=sys.stderr)
        _release_translate_lock(lock_fd)
        return 2

    worker_id = worker["worker_id"]

    def heartbeat() -> None:
        check_stop_or_raise(worker_id=worker_id, run_id=registry_run_id, repo_root=REPO_ROOT)
        _registry.heartbeat_worker(worker_id)

    try:
        _update_stage_state(
            REPO_ROOT,
            args.stage,
            registry_run_id,
            "in_progress",
            {"limit_chapters": limit, "chapter_offset": args.chapter_offset},
            state_path=stage_state_path,
        )

        try:
            run_kwargs = {
                "repo_root": REPO_ROOT,
                "input_dir": input_dir,
                "limit_chapters": limit,
                "chapter_offset": args.chapter_offset,
                "run_id": run_id,
                "asset_context_path": args.asset_context,
            }
            if args.stage == "stage_b":
                run_kwargs["heartbeat_cb"] = heartbeat
                run_kwargs["worker_id"] = worker_id
                run_kwargs["tick_max_segments"] = max(0, int(args.tick_max_segments or 0))
                run_kwargs["tick_max_wall_seconds"] = max(
                    0.0, float(args.tick_max_wall_time_seconds or 0)
                )
            summary, run_root = run_fn(**run_kwargs)
        except StopRequested as exc:
            _update_stage_state(
                REPO_ROOT,
                args.stage,
                registry_run_id,
                "stopped_by_controller",
                {"reason": str(exc), "limit_chapters": limit, "chapter_offset": args.chapter_offset},
                state_path=stage_state_path,
            )
            _registry.unregister_worker(worker_id, status="stopped_by_controller")
            print(f"translate stopped: {exc}", file=sys.stderr)
            return 3
        except Exception as exc:
            _update_stage_state(
                REPO_ROOT,
                args.stage,
                run_id or "failed",
                "failed",
                {"error": str(exc)},
                state_path=stage_state_path,
            )
            _registry.unregister_worker(worker_id, status="failed")
            print(f"translate failed: {exc}", file=sys.stderr)
            return 2

        ok = not summary.aborted and all(c.ok for c in summary.chapters)
        if getattr(summary, "tick_paused", False):
            status = "in_progress"
            _registry.unregister_worker(worker_id, status="tick_paused")
            print(
                f"run_id={summary.run_id} status=tick_paused "
                f"segments={summary.translated_segments}/{summary.total_segments} "
                f"api_calls={summary.api_calls} cost_usd={summary.spent_usd:.6f}"
            )
            return 0
        status = "completed" if ok else "failed"
        _update_stage_state(
            REPO_ROOT,
            args.stage,
            summary.run_id,
            status,
            {
                "translated_segments": summary.translated_segments,
                "total_segments": summary.total_segments,
                "provider_mode": summary.provider_mode,
                "model_name": summary.model_name,
                "run_root": str(run_root.relative_to(REPO_ROOT)),
                "asset_context_path": summary.asset_context_path,
                "api_calls": summary.api_calls,
                "spent_usd": summary.spent_usd,
            },
            state_path=stage_state_path,
        )
        _registry.unregister_worker(worker_id, status=status)
        print(
            f"run_id={summary.run_id} status={status} "
            f"segments={summary.translated_segments}/{summary.total_segments} "
            f"api_calls={summary.api_calls} cost_usd={summary.spent_usd:.6f}"
        )
        return 0 if ok else 1
    finally:
        _release_translate_lock(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
