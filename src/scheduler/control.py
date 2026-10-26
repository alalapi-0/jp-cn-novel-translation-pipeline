"""Pause-file and lock-file control protocol for the local scheduler.

Implements docs/product_final_state_spec.md §9.3 / §9.4:

- pause file  workspace/control/scheduler_paused.json
  When present with {"paused": true}, the scheduler must not start real API
  work. A malformed pause file is treated as paused (fail-safe: when in
  doubt, do not spend money).

- lock file   workspace/control/scheduler_running.lock
  Tick identity is PID + process start ticks + boot/host identity + nonce.
  Serialized metadata transitions prevent competing reclaims. Only a proved
  stale local identity may be reclaimed; malformed/foreign identities block.
"""

from __future__ import annotations

import json
import os
import socket
import tempfile
import stat
import uuid

from providers.controlled_run import checkpoint_lock
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
    except PermissionError:
        return True
    except ProcessLookupError:
        return False
    except OSError:
        return True


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

_OWNED_NONCES: dict[str, str] = {}


def _boot_id() -> str:
    return Path('/proc/sys/kernel/random/boot_id').read_text().strip()


def _start_ticks(pid: int) -> int | None:
    try:
        text = Path(f'/proc/{pid}/stat').read_text()
    except FileNotFoundError:
        return None
    # comm may itself contain spaces and parentheses; fields start after its
    # final closing parenthesis. Field22 is index19 after field3(state).
    fields = text[text.rindex(')') + 2:].split()
    return None if fields[0] == 'Z' else int(fields[19])


def _snapshot(path: Path):
    try:
        info = path.lstat()
    except FileNotFoundError:
        return None
    if not stat.S_ISREG(info.st_mode):
        raise SchedulerLockError('unknown_lock_identity')
    raw = path.read_bytes()
    again = path.lstat()
    if (info.st_dev, info.st_ino, info.st_mtime_ns) != (again.st_dev, again.st_ino, again.st_mtime_ns):
        raise SchedulerLockError('lock_changed')
    return info.st_dev, info.st_ino, raw


def read_lock(repo_root: Path | None = None) -> dict[str, Any] | None:
    try:
        snapshot = _snapshot(lock_file_path(repo_root))
        if snapshot is None:
            return None
        doc = json.loads(snapshot[2])
        return doc if isinstance(doc, dict) else {'malformed': True}
    except (OSError, ValueError, SchedulerLockError):
        return {'malformed': True}


def lock_status(repo_root: Path | None = None) -> dict[str, Any]:
    doc = read_lock(repo_root)
    result = {'exists': doc is not None, 'pid': None, 'alive': False,
              'stale': False, 'unknown': False, 'holder': doc}
    if doc is None:
        return result
    pid = doc.get('pid')
    if type(pid) is not int or pid <= 0 or doc.get('host', socket.gethostname()) != socket.gethostname():
        return dict(result, unknown=True)
    result['pid'] = pid
    if 'schema' not in doc:
        # A live legacy PID gives no possession/start identity. A proved dead
        # local legacy PID remains explicitly reclaimable without rewriting it.
        alive = pid_alive(pid)
        return dict(result, alive=alive, stale=not alive, unknown=alive)
    if type(doc.get('schema')) is not int or doc['schema'] != 2 or 'host' not in doc:
        return dict(result, unknown=True)
    ticks, boot, nonce = doc.get('start_ticks'), doc.get('boot_id'), doc.get('nonce')
    if (type(ticks) is not int or ticks <= 0 or not isinstance(boot, str) or not boot
            or not isinstance(nonce, str) or len(nonce) != 32
            or any(c not in '0123456789abcdef' for c in nonce)):
        return dict(result, unknown=True)
    try:
        if str(uuid.UUID(boot)) != boot:
            raise ValueError('noncanonical boot identity')
    except (ValueError, AttributeError):
        return dict(result, unknown=True)
    try:
        if boot != _boot_id():
            return dict(result, stale=True)
        current = _start_ticks(pid)
    except (OSError, ValueError, IndexError):
        return dict(result, unknown=True)
    alive = current == ticks
    return dict(result, alive=alive, stale=not alive)


@contextmanager
def _transition(path: Path):
    # Stable sidecar is never unlinked: all supported acquire/release/reclaim
    # paths serialize their read/compare/write lifecycle using the same inode.
    try:
        with checkpoint_lock(path.with_name(path.name + '.transition')):
            yield
    except RuntimeError as exc:
        if str(exc) == 'checkpoint is already in use':
            raise SchedulerLockError('lock_held', {'reason': 'transition_in_use'}) from exc
        raise


def _sync_directory(path: Path):
    fd = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _remove_exact(path: Path, snapshot):
    if _snapshot(path) != snapshot:
        raise SchedulerLockError('lock_changed')
    path.unlink()
    _sync_directory(path)


def _publish_lock(path: Path, payload):
    fd, name = tempfile.mkstemp(prefix='.scheduler-lock-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            json.dump(payload, handle, ensure_ascii=False)
            handle.write('\n');handle.flush();os.fsync(handle.fileno())
        # Publish a complete file only when absent, never overwrite a holder.
        os.link(name, path)
        _sync_directory(path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def acquire_lock(*, owner='local_scheduler_tick', repo_root=None,
                 reclaim_stale=False, pid=None) -> dict[str, Any]:
    own_pid = os.getpid()
    if pid is not None and (type(pid) is not int or pid != own_pid):
        raise SchedulerLockError('not_current_process')
    try:
        ticks, boot = _start_ticks(own_pid), _boot_id()
        if ticks is None:
            raise ValueError('missing current process identity')
    except (OSError, ValueError, IndexError) as exc:
        raise SchedulerLockError('process_identity_unavailable') from exc
    payload = {'schema': 2, 'pid': own_pid, 'start_ticks': ticks, 'boot_id': boot,
               'host': socket.gethostname(), 'nonce': uuid.uuid4().hex,
               'owner': owner, 'created_at': utc_now()}
    path = lock_file_path(repo_root)
    with _transition(path):
        snapshot = _snapshot(path)
        if snapshot is not None:
            status = lock_status(repo_root)
            if status['alive']:
                raise SchedulerLockError('lock_held', status['holder'])
            if status['unknown']:
                raise SchedulerLockError('unknown_lock_identity', status['holder'])
            if not status['stale'] or not reclaim_stale:
                raise SchedulerLockError('stale_lock', status['holder'])
            _remove_exact(path, snapshot)
        try:
            _publish_lock(path, payload)
        except FileExistsError as exc:
            raise SchedulerLockError('lock_changed') from exc
        _OWNED_NONCES[str(path.resolve())] = payload['nonce']
    return payload


def release_lock(*, repo_root=None, pid=None, force=False, nonce=None) -> bool:
    """Release exact possession; force cannot override a live/unknown holder.

    Proven stale local records can be cleared, retaining legacy dead-PID cleanup.
    """
    path = lock_file_path(repo_root)
    with _transition(path):
        snapshot = _snapshot(path)
        if snapshot is None:
            return False
        status = lock_status(repo_root);doc = status['holder']
        own_pid = os.getpid() if pid is None else pid
        token = nonce if nonce is not None else _OWNED_NONCES.get(str(path.resolve()))
        owned = (own_pid == os.getpid() and doc.get('pid') == own_pid
                 and status['alive'] and not status['unknown']
                 and token is not None and token == doc.get('nonce'))
        if not owned and not status['stale']:
            raise SchedulerLockError('not_lock_owner', doc)
        _remove_exact(path, snapshot)
        _OWNED_NONCES.pop(str(path.resolve()), None)
    return True


def clear_stale_lock(repo_root: Path | None = None) -> bool:
    path = lock_file_path(repo_root)
    with _transition(path):
        snapshot = _snapshot(path)
        if snapshot is None:
            return False
        status = lock_status(repo_root)
        if status['alive']:
            raise SchedulerLockError('lock_held', status['holder'])
        if status['unknown'] or not status['stale']:
            raise SchedulerLockError('unknown_lock_identity', status['holder'])
        _remove_exact(path, snapshot)
    return True


@contextmanager
def scheduler_lock(*, owner='local_scheduler_tick', repo_root=None,
                   reclaim_stale=False) -> Iterator[dict[str, Any]]:
    payload = acquire_lock(owner=owner, repo_root=repo_root, reclaim_stale=reclaim_stale)
    try:
        yield payload
    finally:
        release_lock(repo_root=repo_root, pid=payload['pid'], nonce=payload['nonce'])


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
