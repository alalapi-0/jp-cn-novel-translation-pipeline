#!/usr/bin/env python3
"""Legacy Stage C refinement runner.

The active production route no longer includes refinement. This script is kept
only for audited historical reproduction and is disabled by default.
"""

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

from translation.refine_runner import (  # noqa: E402
    STAGE_C_MAX_SEGMENTS,
    iter_refine_candidates,
    load_segments_doc,
    run_refine_controlled,
)
from translation.run_progress import update_stage_state_if_newer  # noqa: E402

_registry_spec = importlib.util.spec_from_file_location(
    "pipeline_worker_registry",
    REPO_ROOT / "scripts" / "pipeline_worker_registry.py",
)
assert _registry_spec and _registry_spec.loader
_registry = importlib.util.module_from_spec(_registry_spec)
_registry_spec.loader.exec_module(_registry)


def _refine_lock_path(run_id: str) -> Path:
    return REPO_ROOT / "workspace" / ".locks" / f"refine_stage_c_{run_id}.lock"


def _acquire_refine_lock(run_id: str) -> int:
    lock_path = _refine_lock_path(run_id)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(lock_path, os.O_CREAT | os.O_RDWR, 0o644)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        print(f"refine_stage_c already running for run_id={run_id}", file=sys.stderr)
        return -1
    os.ftruncate(fd, 0)
    os.write(fd, f"{os.getpid()}\n".encode())
    return fd


def _release_lock(fd: int, run_id: str = "") -> None:
    if fd < 0:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)
        # Remove the residue file so monitoring never sees a dead-pid lock
        # (FS-006). flock dies with the process, so the file is only
        # informational; refine runs are single-operator so the classic
        # flock/unlink race is acceptable here.
        if run_id:
            _refine_lock_path(run_id).unlink(missing_ok=True)


def _default_run_id() -> str:
    state_path = REPO_ROOT / "workspace" / "stage_state.json"
    if state_path.is_file():
        data = json.loads(state_path.read_text(encoding="utf-8"))
        rid = (data.get("run_id") or "").strip()
        if rid:
            return rid
    return ""


def _count_remaining_refine(run_root: Path) -> int:
    segments_path = run_root / "segments.json"
    if not segments_path.is_file():
        return 0
    doc = load_segments_doc(segments_path)
    return len(iter_refine_candidates(doc, limit=STAGE_C_MAX_SEGMENTS * 10))


def _resolve_refine_stage_status(
    run_status: str,
    *,
    remaining_refine: int,
    aborted: bool,
) -> tuple[str, bool]:
    """Return (stage_status, refine_blocked). Blocked until all segments are refined."""
    if aborted or run_status == "failed":
        return "failed", True
    if remaining_refine > 0:
        return "in_progress", True
    return "completed", False


def _update_stage_state(
    run_id: str,
    status: str,
    summary: dict,
    *,
    state_path: Path | None = None,
    remaining_refine: int | None = None,
) -> None:
    refine_blocked = status != "completed"
    if remaining_refine is not None:
        refine_blocked = remaining_refine > 0 or status in {"failed", "in_progress"}
    payload = {
        "phase": "refine",
        "stage": "refine_stage_c",
        "status": status,
        "run_id": run_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "refine_blocked": refine_blocked,
        "pilot": False,
        "summary": summary,
    }
    update_stage_state_if_newer(
        REPO_ROOT,
        payload,
        run_id=run_id,
        state_path=state_path,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Legacy Stage C refinement (disabled by default)")
    parser.add_argument("--run-id", default="", help="Draft run id (default: workspace/stage_state.json)")
    parser.add_argument(
        "--limit-segments",
        type=int,
        default=12,
        help=f"Max segments to refine (hard cap {STAGE_C_MAX_SEGMENTS})",
    )
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run provider (no network)")
    parser.add_argument(
        "--stage-state-path",
        type=Path,
        default=None,
        help="Write stage_state to this path (default: workspace/stage_state.json)",
    )
    parser.add_argument("--json", action="store_true", help="Print summary JSON to stdout")
    args = parser.parse_args()

    if os.environ.get("ALLOW_LEGACY_REFINEMENT") != "1":
        message = (
            "refine_stage_c.py is deprecated and disabled by default. "
            "Use docs/translation_production_protocol.md: translate -> consistency -> singleton final export."
        )
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "blocked",
                        "reason": "legacy_refinement_disabled",
                        "message": message,
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(message, file=sys.stderr)
        return 2

    apply_local_env(REPO_ROOT)
    run_id = args.run_id.strip() or _default_run_id()
    if not run_id:
        print("missing --run-id and no run_id in workspace/stage_state.json", file=sys.stderr)
        return 2

    limit = args.limit_segments
    if limit < 1 or limit > STAGE_C_MAX_SEGMENTS:
        print(f"--limit-segments must be 1..{STAGE_C_MAX_SEGMENTS}", file=sys.stderr)
        return 2

    lock_fd = _acquire_refine_lock(run_id)
    if lock_fd < 0:
        return 2

    worker, reason = _registry.register_worker(
        task_type="refine",
        stage="refine_stage_c",
        run_id=run_id,
    )
    if worker is None:
        print(reason, file=sys.stderr)
        _release_lock(lock_fd, run_id)
        return 2

    worker_id = worker["worker_id"]
    stage_state_path = args.stage_state_path

    def heartbeat() -> None:
        _registry.heartbeat_worker(worker_id)

    try:
        _update_stage_state(
            run_id,
            "in_progress",
            {"limit_segments": limit, "dry_run": args.dry_run},
            state_path=stage_state_path,
        )
        try:
            summary, run_root = run_refine_controlled(
                repo_root=REPO_ROOT,
                run_id=run_id,
                limit_segments=limit,
                force_dry_run=args.dry_run,
                heartbeat_cb=heartbeat,
            )
        except Exception as exc:
            _update_stage_state(run_id, "failed", {"error": str(exc)}, state_path=stage_state_path)
            _registry.unregister_worker(worker_id, status="failed")
            print(f"refine failed: {exc}", file=sys.stderr)
            return 2

        ok = not summary.aborted
        remaining_refine = _count_remaining_refine(run_root)
        status, _ = _resolve_refine_stage_status(
            "completed" if ok else "failed",
            remaining_refine=remaining_refine,
            aborted=summary.aborted,
        )
        payload = {
            "refined_segments": summary.refined_segments,
            "api_calls": summary.api_calls,
            "provider_mode": summary.provider_mode,
            "model_name": summary.model_name,
            "run_root": str(run_root.relative_to(REPO_ROOT)),
            "spent_usd": summary.spent_usd,
            "spent_tokens": summary.spent_tokens,
            "aborted": summary.aborted,
            "abort_reason": summary.abort_reason,
            "remaining_refine_segments": remaining_refine,
        }
        _update_stage_state(
            run_id,
            status,
            payload,
            state_path=stage_state_path,
            remaining_refine=remaining_refine,
        )
        _registry.unregister_worker(worker_id, status=status)

        if args.json:
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            print(
                f"run_id={run_id} status={status} refined={summary.refined_segments} "
                f"api_calls={summary.api_calls} cost_usd={summary.spent_usd:.6f} "
                f"mode={summary.provider_mode}"
            )
        return 0 if ok else 1
    finally:
        _release_lock(lock_fd, run_id)


if __name__ == "__main__":
    raise SystemExit(main())
