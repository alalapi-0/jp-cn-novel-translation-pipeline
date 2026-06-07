"""Unified stop signal for supervised translation workers."""

from __future__ import annotations

import json
import os
import signal
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

STOP_REL = "workspace/control/stop_requested.json"


class StopRequested(Exception):
    """Raised when controller requests worker shutdown."""

    def __init__(self, reason: str = "stop_requested") -> None:
        self.reason = reason
        super().__init__(reason)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def stop_file_path(repo_root: Path | None = None) -> Path:
    root = repo_root or _repo_root()
    return root / STOP_REL


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=f".{path.name}.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def read_stop_request(repo_root: Path | None = None) -> dict[str, Any] | None:
    path = stop_file_path(repo_root)
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if doc.get("requested"):
        return doc
    return None


def request_stop(
    *,
    reason: str = "controller_exit",
    requested_by: str = "translation_autopilot_loop",
    target_worker_id: str = "",
    target_run_id: str = "",
    repo_root: Path | None = None,
) -> dict[str, Any]:
    payload = {
        "requested": True,
        "reason": reason,
        "requested_by": requested_by,
        "requested_at": utc_now(),
        "target_worker_id": target_worker_id,
        "target_run_id": target_run_id,
    }
    _atomic_write(stop_file_path(repo_root), payload)
    return payload


def clear_stop_request(repo_root: Path | None = None) -> None:
    path = stop_file_path(repo_root)
    if path.is_file():
        path.unlink(missing_ok=True)


def is_stop_requested(
    *,
    worker_id: str = "",
    run_id: str = "",
    repo_root: Path | None = None,
) -> bool:
    doc = read_stop_request(repo_root)
    if not doc:
        return False
    target_wid = str(doc.get("target_worker_id") or "")
    target_rid = str(doc.get("target_run_id") or "")
    if target_wid and worker_id and target_wid != worker_id:
        return False
    if target_rid and run_id and target_rid != run_id:
        return False
    return True


def check_stop_or_raise(
    *,
    worker_id: str = "",
    run_id: str = "",
    repo_root: Path | None = None,
) -> None:
    doc = read_stop_request(repo_root)
    if is_stop_requested(worker_id=worker_id, run_id=run_id, repo_root=repo_root):
        reason = str((doc or {}).get("reason") or "stop_requested")
        raise StopRequested(reason)


_signal_stop_requested = False


def install_signal_handlers() -> None:
    global _signal_stop_requested

    def _handler(signum: int, _frame: object) -> None:
        global _signal_stop_requested
        _signal_stop_requested = True
        request_stop(
            reason=f"signal_{signum}",
            requested_by="translate_worker",
        )

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except (ValueError, OSError):
            pass


def signal_stop_pending() -> bool:
    return _signal_stop_requested or read_stop_request() is not None
