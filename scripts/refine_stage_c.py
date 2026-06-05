#!/usr/bin/env python3
"""Stage C controlled refinement pilot on a completed Stage B draft run."""

from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from translation.refine_runner import STAGE_C_MAX_SEGMENTS, run_refine_pilot  # noqa: E402


def _apply_local_env(repo_root: Path) -> None:
    env_path = repo_root / ".env"
    if not env_path.is_file():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        if not key or key in os.environ:
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ[key] = value


def _acquire_refine_lock(run_id: str) -> int:
    lock_dir = REPO_ROOT / "workspace" / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    lock_path = lock_dir / f"refine_stage_c_{run_id}.lock"
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


def _release_lock(fd: int) -> None:
    if fd < 0:
        return
    try:
        fcntl.flock(fd, fcntl.LOCK_UN)
    finally:
        os.close(fd)


def _default_run_id() -> str:
    state_path = REPO_ROOT / "workspace" / "stage_state.json"
    if state_path.is_file():
        data = json.loads(state_path.read_text(encoding="utf-8"))
        rid = (data.get("run_id") or "").strip()
        if rid:
            return rid
    return ""


def _update_stage_state(run_id: str, status: str, summary: dict, *, state_path: Path | None = None) -> None:
    path = state_path or (REPO_ROOT / "workspace" / "stage_state.json")
    payload = {
        "phase": "refine",
        "stage": "refine_stage_c_pilot",
        "status": status,
        "run_id": run_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "refine_blocked": status != "completed",
        "pilot": True,
        "summary": summary,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Stage C refinement pilot")
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

    _apply_local_env(REPO_ROOT)
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

    stage_state_path = args.stage_state_path
    try:
        _update_stage_state(
            run_id,
            "in_progress",
            {"limit_segments": limit, "dry_run": args.dry_run},
            state_path=stage_state_path,
        )
        try:
            summary, run_root = run_refine_pilot(
                repo_root=REPO_ROOT,
                run_id=run_id,
                limit_segments=limit,
                force_dry_run=args.dry_run,
            )
        except Exception as exc:
            _update_stage_state(run_id, "failed", {"error": str(exc)}, state_path=stage_state_path)
            print(f"refine failed: {exc}", file=sys.stderr)
            return 2

        ok = not summary.aborted
        status = "completed" if ok else "failed"
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
        }
        _update_stage_state(run_id, status, payload, state_path=stage_state_path)

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
        _release_lock(lock_fd)


if __name__ == "__main__":
    raise SystemExit(main())
