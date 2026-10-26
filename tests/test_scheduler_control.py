"""Tests for the local scheduler pause / lock control protocol (FS-001)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from scheduler.control import (  # noqa: E402
    SchedulerLockError,
    acquire_lock,
    clear_pause,
    clear_stale_lock,
    is_paused,
    lock_file_path,
    lock_status,
    pause_file_path,
    read_pause_state,
    release_lock,
    request_pause,
    safe_to_start_real_api,
    scheduler_lock,
)


def _dead_pid() -> int:
    proc = subprocess.Popen([sys.executable, "-c", "pass"])
    proc.wait()
    return proc.pid


def _write_lock(repo_root: Path, pid: int) -> Path:
    path = lock_file_path(repo_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps({"pid": pid, "owner": "test", "created_at": "2026-06-11T00:00:00+00:00"}),
        encoding="utf-8",
    )
    return path


# ---------------------------------------------------------------------------
# Pause file
# ---------------------------------------------------------------------------

def test_is_paused_missing_file(tmp_path: Path) -> None:
    assert is_paused(tmp_path) is False
    assert read_pause_state(tmp_path) is None


def test_is_paused_true(tmp_path: Path) -> None:
    path = pause_file_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"paused": true}', encoding="utf-8")
    assert is_paused(tmp_path) is True


def test_is_paused_false_payload(tmp_path: Path) -> None:
    path = pause_file_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"paused": false}', encoding="utf-8")
    assert is_paused(tmp_path) is False


def test_is_paused_malformed_is_fail_safe(tmp_path: Path) -> None:
    path = pause_file_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")
    assert is_paused(tmp_path) is True
    state = read_pause_state(tmp_path)
    assert state is not None and state.get("malformed") is True


def test_request_and_clear_pause_roundtrip(tmp_path: Path) -> None:
    payload = request_pause(reason="unit_test", requested_by="pytest", repo_root=tmp_path)
    assert payload["paused"] is True
    assert is_paused(tmp_path) is True
    on_disk = json.loads(pause_file_path(tmp_path).read_text(encoding="utf-8"))
    assert on_disk["reason"] == "unit_test"
    assert on_disk["requested_by"] == "pytest"
    assert clear_pause(tmp_path) is True
    assert is_paused(tmp_path) is False
    assert clear_pause(tmp_path) is False


def test_safe_to_start_real_api_blocked_by_pause(tmp_path: Path) -> None:
    assert safe_to_start_real_api(tmp_path)["safe"] is True
    request_pause(repo_root=tmp_path)
    guard = safe_to_start_real_api(tmp_path)
    assert guard["safe"] is False
    assert guard["paused"] is True


# ---------------------------------------------------------------------------
# Lock file
# ---------------------------------------------------------------------------

def test_acquire_and_release_lock(tmp_path: Path) -> None:
    payload = acquire_lock(owner="test", repo_root=tmp_path)
    assert payload["pid"] == os.getpid()
    status = lock_status(tmp_path)
    assert status["exists"] is True
    assert status["alive"] is True
    assert status["stale"] is False
    assert release_lock(repo_root=tmp_path) is True
    assert lock_status(tmp_path)["exists"] is False


def test_second_acquire_fails_when_holder_alive(tmp_path: Path) -> None:
    acquire_lock(owner="first", repo_root=tmp_path)
    with pytest.raises(SchedulerLockError) as exc:
        acquire_lock(owner="second", repo_root=tmp_path)
    assert exc.value.reason == "lock_held"
    release_lock(repo_root=tmp_path)


def test_stale_lock_rejected_without_reclaim(tmp_path: Path) -> None:
    _write_lock(tmp_path, _dead_pid())
    status = lock_status(tmp_path)
    assert status["stale"] is True
    with pytest.raises(SchedulerLockError) as exc:
        acquire_lock(repo_root=tmp_path)
    assert exc.value.reason == "stale_lock"


def test_stale_lock_reclaimed_with_flag(tmp_path: Path) -> None:
    _write_lock(tmp_path, _dead_pid())
    payload = acquire_lock(repo_root=tmp_path, reclaim_stale=True)
    assert payload["pid"] == os.getpid()
    assert lock_status(tmp_path)["alive"] is True
    release_lock(repo_root=tmp_path)


def test_clear_stale_lock(tmp_path: Path) -> None:
    assert clear_stale_lock(tmp_path) is False  # nothing to clear
    _write_lock(tmp_path, _dead_pid())
    assert clear_stale_lock(tmp_path) is True
    assert lock_status(tmp_path)["exists"] is False


def test_clear_stale_lock_refuses_alive_holder(tmp_path: Path) -> None:
    _write_lock(tmp_path, os.getpid())
    with pytest.raises(SchedulerLockError) as exc:
        clear_stale_lock(tmp_path)
    assert exc.value.reason == "lock_held"


def test_malformed_lock_is_unknown_and_preserved(tmp_path: Path) -> None:
    path = lock_file_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json at all", encoding="utf-8")
    status = lock_status(tmp_path)
    assert status["exists"] is True
    assert status["stale"] is False and status['unknown'] is True
    before = path.read_bytes()
    with pytest.raises(SchedulerLockError, match='unknown_lock_identity'):
        acquire_lock(repo_root=tmp_path, reclaim_stale=True)
    assert path.read_bytes() == before


def test_release_refuses_foreign_alive_lock(tmp_path: Path) -> None:
    _write_lock(tmp_path, os.getpid())
    with pytest.raises(SchedulerLockError) as exc:
        release_lock(repo_root=tmp_path, pid=999999999)
    assert exc.value.reason == "not_lock_owner"
    with pytest.raises(SchedulerLockError, match='not_lock_owner'):
        release_lock(repo_root=tmp_path, force=True)
    assert lock_status(tmp_path)['exists'] is True


def test_release_allows_removing_dead_holder(tmp_path: Path) -> None:
    _write_lock(tmp_path, _dead_pid())
    assert release_lock(repo_root=tmp_path) is True
    assert lock_status(tmp_path)["exists"] is False


def test_release_when_no_lock(tmp_path: Path) -> None:
    assert release_lock(repo_root=tmp_path) is False


def test_scheduler_lock_context_manager(tmp_path: Path) -> None:
    with scheduler_lock(owner="ctx", repo_root=tmp_path) as payload:
        assert payload["pid"] == os.getpid()
        assert lock_status(tmp_path)["exists"] is True
    assert lock_status(tmp_path)["exists"] is False


def test_scheduler_lock_releases_on_exception(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError):
        with scheduler_lock(owner="ctx", repo_root=tmp_path):
            raise RuntimeError("boom")
    assert lock_status(tmp_path)["exists"] is False


def test_reused_pid_is_not_the_original_scheduler(tmp_path):
    import socket
    path = _write_lock(tmp_path, os.getpid())
    path.write_text(json.dumps({'schema': 2, 'pid': os.getpid(), 'start_ticks': 1,
        'boot_id': Path('/proc/sys/kernel/random/boot_id').read_text().strip(),
        'host': socket.gethostname(), 'nonce': 'a' * 32}))
    assert lock_status(tmp_path)['stale'] is True


def test_changed_possession_token_cannot_release_new_holder(tmp_path):
    acquire_lock(repo_root=tmp_path)
    path = lock_file_path(tmp_path)
    doc = json.loads(path.read_text());doc['nonce'] = 'b' * 32
    path.write_text(json.dumps(doc));before = path.read_bytes()
    with pytest.raises(SchedulerLockError):
        release_lock(repo_root=tmp_path)
    assert path.read_bytes() == before


def test_unknown_malformed_lock_cannot_be_automatically_reclaimed(tmp_path):
    path = lock_file_path(tmp_path);path.parent.mkdir(parents=True)
    path.write_text('{"pid":"unknown"}');before = path.read_bytes()
    with pytest.raises(SchedulerLockError):
        clear_stale_lock(tmp_path)
    assert path.read_bytes() == before


def test_foreign_host_lock_is_not_local_dead_pid_evidence(tmp_path):
    path = _write_lock(tmp_path, _dead_pid())
    doc = json.loads(path.read_text());doc['host'] = 'synthetic-foreign-host'
    path.write_text(json.dumps(doc));before = path.read_bytes()
    with pytest.raises(SchedulerLockError):
        clear_stale_lock(tmp_path)
    assert path.read_bytes() == before


def test_old_token_cannot_release_reacquired_same_process_lock(tmp_path):
    first = acquire_lock(repo_root=tmp_path)
    release_lock(repo_root=tmp_path, nonce=first['nonce'])
    second = acquire_lock(repo_root=tmp_path)
    before = lock_file_path(tmp_path).read_bytes()
    with pytest.raises(SchedulerLockError, match='not_lock_owner'):
        release_lock(repo_root=tmp_path, nonce=first['nonce'], force=True)
    assert lock_file_path(tmp_path).read_bytes() == before
    release_lock(repo_root=tmp_path, nonce=second['nonce'])


def test_pid_reuse_identity_is_explicitly_reclaimable(tmp_path):
    payload = acquire_lock(repo_root=tmp_path)
    path = lock_file_path(tmp_path)
    payload['start_ticks'] += 1
    path.write_text(json.dumps(payload))
    newer = acquire_lock(repo_root=tmp_path, reclaim_stale=True)
    assert newer['nonce'] != payload['nonce']
    assert lock_status(tmp_path)['alive'] is True
    release_lock(repo_root=tmp_path, nonce=newer['nonce'])


def test_cross_process_reclaim_cannot_cross_active_transition(tmp_path):
    import scheduler.control as control
    path = _write_lock(tmp_path, _dead_pid());before = path.read_bytes()
    code = '''
import sys
from pathlib import Path
from scheduler.control import acquire_lock,SchedulerLockError
try:
    acquire_lock(repo_root=Path(sys.argv[1]),reclaim_stale=True)
except SchedulerLockError as exc:
    assert exc.reason=='lock_held'
else:
    raise AssertionError('concurrent reclaim entered')
'''
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT/'src'))
    with control._transition(path):
        result = subprocess.run([sys.executable, '-c', code, str(tmp_path)], env=env, timeout=10)
    assert result.returncode == 0 and path.read_bytes() == before
    payload = acquire_lock(repo_root=tmp_path, reclaim_stale=True)
    release_lock(repo_root=tmp_path, nonce=payload['nonce'])


def test_process_death_leaves_exact_stale_identity_for_explicit_reclaim(tmp_path):
    code = '''
import os,sys
from pathlib import Path
from scheduler.control import acquire_lock
acquire_lock(repo_root=Path(sys.argv[1]))
os._exit(23)
'''
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT/'src'))
    result = subprocess.run([sys.executable, '-c', code, str(tmp_path)], env=env, timeout=10)
    assert result.returncode == 23 and lock_status(tmp_path)['stale'] is True
    payload = acquire_lock(repo_root=tmp_path, reclaim_stale=True)
    release_lock(repo_root=tmp_path, nonce=payload['nonce'])


def test_publish_failure_leaves_no_partial_lock(tmp_path, monkeypatch):
    import scheduler.control as control
    def fail(*_): raise OSError('synthetic publication failure')
    monkeypatch.setattr(control.os, 'link', fail)
    with pytest.raises(OSError): acquire_lock(repo_root=tmp_path)
    assert not lock_file_path(tmp_path).exists()
    assert not list(lock_file_path(tmp_path).parent.glob('.scheduler-lock-*'))


def test_changed_candidate_is_preserved_before_stale_deletion(tmp_path, monkeypatch):
    import scheduler.control as control
    path = _write_lock(tmp_path, _dead_pid())
    original = control._remove_exact
    replacement = b'{"owner":"synthetic replacement","pid":1}'
    def replace_then_remove(path, snapshot):
        path.write_bytes(replacement)
        return original(path, snapshot)
    monkeypatch.setattr(control, '_remove_exact', replace_then_remove)
    with pytest.raises(SchedulerLockError, match='lock_changed'):
        clear_stale_lock(tmp_path)
    assert path.read_bytes() == replacement


def test_permission_denied_liveness_is_not_proof_of_dead_pid(monkeypatch):
    import scheduler.control as control
    def deny(*_): raise PermissionError('synthetic permission denial')
    monkeypatch.setattr(control.os, 'kill', deny)
    assert control.pid_alive(123) is True


@pytest.mark.parametrize('change', ['unknown_schema', 'missing_host', 'invalid_boot'])
def test_incomplete_or_unknown_identity_version_is_preserved(tmp_path, change):
    payload = acquire_lock(repo_root=tmp_path)
    release_lock(repo_root=tmp_path)
    if change == 'unknown_schema':
        payload['schema'] = 3;payload['pid'] = _dead_pid()
    elif change == 'missing_host':
        del payload['host']
    else:
        payload['boot_id'] = 'malformed boot'
    path = lock_file_path(tmp_path);path.write_text(json.dumps(payload));before = path.read_bytes()
    assert lock_status(tmp_path)['unknown'] is True
    with pytest.raises(SchedulerLockError):clear_stale_lock(tmp_path)
    assert path.read_bytes() == before
