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


def test_malformed_lock_is_stale_and_reclaimable(tmp_path: Path) -> None:
    path = lock_file_path(tmp_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not json at all", encoding="utf-8")
    status = lock_status(tmp_path)
    assert status["exists"] is True
    assert status["stale"] is True
    payload = acquire_lock(repo_root=tmp_path, reclaim_stale=True)
    assert payload["pid"] == os.getpid()
    release_lock(repo_root=tmp_path)


def test_release_refuses_foreign_alive_lock(tmp_path: Path) -> None:
    _write_lock(tmp_path, os.getpid())
    with pytest.raises(SchedulerLockError) as exc:
        release_lock(repo_root=tmp_path, pid=999999999)
    assert exc.value.reason == "not_lock_owner"
    assert release_lock(repo_root=tmp_path, force=True) is True


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
