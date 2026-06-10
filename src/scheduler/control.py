"""Pause-file and lock-file control protocol for the local scheduler.

Implements docs/product_final_state_spec.md §9.3 / §9.4:

- pause file  workspace/control/scheduler_paused.json
  When present with {"paused": true}, the scheduler must not start real API
  work. A malformed pause file is treated as paused (fail-safe: when in
  doubt, do not spend money).

- lock file   workspace/control/scheduler_running.lock
  Mutual exclusion between ticks. If the lock exists and its pid is alive,
  a new tick must exit. A stale lock (dead pid or unreadable payload) may be
  safely cleared, either explicitly or via acquire(reclaim_stale=True).
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

PAUSE_REL = "workspace/control/scheduler_paused.json"
LOCK_REL = "workspace/control/scheduler_running.lock"


class SchedulerLockError(Exception):
    """Raised when the scheduler lock cannot be acquired or released."""

    def __init__(self, reason: str, holder: dict[str, Any] | None = None) -> None:
        self.reason = reason
        self.holder = holder or {}
        super().__init__(reason)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent.parent


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def pause_file_path(repo_root: Path | None = None) -> Path:
    return (repo_root or _repo_root()) / PAUSE_REL


def lock_file_path(repo_root: Path | None = None) -> Path:
    return (repo_root or _repo_root()) / LOCK_REL


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
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


# ---------------------------------------------------------------------------
# Pause file protocol (spec §9.3)
# ---------------------------------------------------------------------------

def read_pause_state(repo_root: Path | None = None) -> dict[str, Any] | None:
    """Return the pause file payload, or None when the file is absent.

    A present-but-unreadable file returns {"paused": True, "malformed": True}
    so callers fail safe.
    """
    path = pause_file_path(repo_root)
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"paused": True, "malformed": True}
    if not isinstance(doc, dict):
        return {"paused": True, "malformed": True}
    return doc


def is_paused(repo_root: Path | None = None) -> bool:
    doc = read_pause_state(repo_root)
    if doc is None:
        return False
    return bool(doc.get("paused"))


def request_pause(
    *,
    reason: str = "user_requested",
    requested_by: str = "unknown",
    repo_root: Path | None = None,
) -> dict[str, Any]:
    payload = {
        "paused": True,
        "reason": reason,
        "requested_by": requested_by,
        "requested_at": utc_now(),
    }
    _atomic_write_json(pause_file_path(repo_root), payload)
    return payload


def clear_pause(repo_root: Path | None = None) -> bool:
    """Remove the pause file (resume). Returns True when a file was removed."""
    path = pause_file_path(repo_root)
    if path.is_file():
        path.unlink(missing_ok=True)
        return True
    return False


# ---------------------------------------------------------------------------
# Lock file protocol (spec §9.4)
# ---------------------------------------------------------------------------

def read_lock(repo_root: Path | None = None) -> dict[str, Any] | None:
    """Return lock payload, None when absent, or {"malformed": True} on bad JSON."""
    path = lock_file_path(repo_root)
    if not path.is_file():
        return None
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"malformed": True}
    if not isinstance(doc, dict):
        return {"malformed": True}
    return doc


def lock_status(repo_root: Path | None = None) -> dict[str, Any]:
    """Describe the current lock: exists / pid / alive / stale / holder payload."""
    doc = read_lock(repo_root)
    if doc is None:
        return {"exists": False, "pid": None, "alive": False, "stale": False, "holder": None}
    pid = int(doc.get("pid") or 0)
    alive = pid_alive(pid)
    # Malformed payloads and dead pids are both stale: nobody provably owns it.
    stale = not alive
    return {"exists": True, "pid": pid or None, "alive": alive, "stale": stale, "holder": doc}


def acquire_lock(
    *,
    owner: str = "local_scheduler_tick",
    repo_root: Path | None = None,
    reclaim_stale: bool = False,
    pid: int | None = None,
) -> dict[str, Any]:
    """Atomically acquire the scheduler lock.

    Raises SchedulerLockError(reason="lock_held") when an alive holder exists,
    and SchedulerLockError(reason="stale_lock") when a stale lock exists and
    reclaim_stale is False. With reclaim_stale=True a stale lock is cleared
    and acquisition retried once.
    """
    path = lock_file_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "pid": int(pid if pid is not None else os.getpid()),
        "owner": owner,
        "host": socket.gethostname(),
        "created_at": utc_now(),
    }
    for attempt in (1, 2):
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            status = lock_status(repo_root)
            if status["alive"]:
                raise SchedulerLockError("lock_held", holder=status["holder"])
            if not reclaim_stale or attempt == 2:
                raise SchedulerLockError("stale_lock", holder=status["holder"])
            clear_stale_lock(repo_root)
            continue
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        return payload
    raise SchedulerLockError("unreachable")  # pragma: no cover


def release_lock(
    *,
    repo_root: Path | None = None,
    pid: int | None = None,
    force: bool = False,
) -> bool:
    """Release the lock owned by `pid` (default: current process).

    Refuses to remove a lock held by a different alive pid unless force=True.
    Returns True when a lock file was removed.
    """
    path = lock_file_path(repo_root)
    doc = read_lock(repo_root)
    if doc is None:
        return False
    own_pid = int(pid if pid is not None else os.getpid())
    holder_pid = int(doc.get("pid") or 0)
    if not force and holder_pid != own_pid and pid_alive(holder_pid):
        raise SchedulerLockError("not_lock_owner", holder=doc)
    path.unlink(missing_ok=True)
    return True


def clear_stale_lock(repo_root: Path | None = None) -> bool:
    """Remove the lock only when it is stale. Returns True when removed.

    Raises SchedulerLockError(reason="lock_held") if the holder pid is alive.
    """
    status = lock_status(repo_root)
    if not status["exists"]:
        return False
    if status["alive"]:
        raise SchedulerLockError("lock_held", holder=status["holder"])
    lock_file_path(repo_root).unlink(missing_ok=True)
    return True


@contextmanager
def scheduler_lock(
    *,
    owner: str = "local_scheduler_tick",
    repo_root: Path | None = None,
    reclaim_stale: bool = False,
) -> Iterator[dict[str, Any]]:
    """Context manager: acquire on enter, always release own lock on exit."""
    payload = acquire_lock(owner=owner, repo_root=repo_root, reclaim_stale=reclaim_stale)
    try:
        yield payload
    finally:
        release_lock(repo_root=repo_root, pid=payload["pid"])


def safe_to_start_real_api(repo_root: Path | None = None) -> dict[str, Any]:
    """Aggregate guard used by future tick/status scripts (FS-002/FS-003).

    Real API work is allowed only when not paused. Lock state is reported for
    the caller's decision (a tick must additionally hold the lock itself).
    """
    paused = is_paused(repo_root)
    lock = lock_status(repo_root)
    return {
        "paused": paused,
        "lock": lock,
        "safe": not paused,
    }
