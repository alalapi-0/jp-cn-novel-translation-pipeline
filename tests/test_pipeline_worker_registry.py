"""Tests for pipeline worker registry."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_registry():
    spec = importlib.util.spec_from_file_location(
        "pipeline_worker_registry_test",
        REPO_ROOT / "scripts" / "pipeline_worker_registry.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_register_rejects_duplicate_active_worker(tmp_path, monkeypatch):
    reg = _load_registry()
    state_path = tmp_path / "pipeline_state.json"
    monkeypatch.setattr(reg, "DEFAULT_STATE_PATH", state_path)
    monkeypatch.setattr(reg, "pid_alive", lambda pid: True)

    worker1, reason1 = reg.register_worker(
        task_type="translate",
        stage="stage_b",
        run_id="run_test",
        chapter_offset=0,
        pid=1001,
        state_path=state_path,
    )
    assert worker1 is not None
    assert reason1 == "registered"

    worker2, reason2 = reg.register_worker(
        task_type="translate",
        stage="stage_b",
        run_id="run_test",
        chapter_offset=0,
        pid=1002,
        state_path=state_path,
    )
    assert worker2 is None
    assert "already_running" in reason2


def test_stale_worker_when_pid_dead(tmp_path, monkeypatch):
    reg = _load_registry()
    state_path = tmp_path / "pipeline_state.json"
    monkeypatch.setattr(reg, "DEFAULT_STATE_PATH", state_path)
    monkeypatch.setattr(reg, "pid_alive", lambda pid: False)

    worker, _ = reg.register_worker(
        task_type="refine",
        stage="refine_stage_c",
        run_id="run_refine",
        pid=2001,
        state_path=state_path,
    )
    assert worker is not None
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["workers"][0]["heartbeat_at"] = "2020-01-01T00:00:00+00:00"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    worker = state["workers"][0]

    assert not reg.is_worker_active(worker)
    assert reg.is_worker_stale(worker)


def test_stale_worker_when_pid_alive_but_heartbeat_old(tmp_path, monkeypatch):
    reg = _load_registry()
    state_path = tmp_path / "pipeline_state.json"
    monkeypatch.setattr(reg, "pid_alive", lambda pid: True)

    worker, _ = reg.register_worker(
        task_type="translate",
        stage="stage_b",
        run_id="run_frozen",
        pid=4001,
        state_path=state_path,
    )
    assert worker is not None
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["workers"][0]["heartbeat_at"] = "2020-01-01T00:00:00+00:00"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    worker = state["workers"][0]

    assert not reg.is_worker_active(worker)
    assert reg.is_worker_stale(worker)


def test_heal_skips_when_run_progress_heartbeat_fresh(tmp_path, monkeypatch):
    reg = _load_registry()
    state_path = tmp_path / "pipeline_state.json"
    lock_dir = tmp_path / "locks"
    run_id = "run_live_progress"
    run_root = tmp_path / "workspace" / "runs" / run_id
    run_root.mkdir(parents=True)
    (run_root / "run_progress.json").write_text(
        json.dumps({"heartbeat_at": reg.utc_now(), "status": "in_progress"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(reg, "DEFAULT_STATE_PATH", state_path)
    monkeypatch.setattr(reg, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(reg, "pid_alive", lambda pid: True)
    monkeypatch.setattr(reg, "_kill_pid", lambda pid: (_ for _ in ()).throw(AssertionError("should not kill")))

    worker, _ = reg.register_worker(
        task_type="translate",
        stage="stage_b",
        run_id=run_id,
        pid=6001,
        state_path=state_path,
    )
    assert worker is not None
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["workers"][0]["heartbeat_at"] = "2020-01-01T00:00:00+00:00"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    result = reg.heal_stale_workers(
        state_path=state_path,
        lock_dir=lock_dir,
        repo_root=tmp_path,
        heartbeat_timeout_sec=60,
    )
    assert result["healed_count"] == 0


def test_heal_stale_workers_kills_and_clears_lock(tmp_path, monkeypatch):
    reg = _load_registry()
    state_path = tmp_path / "pipeline_state.json"
    lock_dir = tmp_path / "locks"
    lock_dir.mkdir()
    killed: list[int] = []
    monkeypatch.setattr(reg, "DEFAULT_STATE_PATH", state_path)
    monkeypatch.setattr(reg, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(reg, "pid_alive", lambda pid: pid == 5001)
    monkeypatch.setattr(reg, "_kill_pid", lambda pid: killed.append(pid) or True)

    worker, _ = reg.register_worker(
        task_type="translate",
        stage="stage_b",
        run_id="run_heal",
        pid=5001,
        state_path=state_path,
    )
    assert worker is not None
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["workers"][0]["heartbeat_at"] = "2020-01-01T00:00:00+00:00"
    state_path.write_text(json.dumps(state), encoding="utf-8")
    (lock_dir / "translate_stage_b_run_heal.lock").write_text("5001\n", encoding="utf-8")

    result = reg.heal_stale_workers(state_path=state_path, lock_dir=lock_dir, heartbeat_timeout_sec=60, repo_root=tmp_path)
    assert result["healed_count"] == 1
    assert 5001 in killed
    assert "translate_stage_b_run_heal.lock" in result["cleared_locks"]


def test_heartbeat_and_unregister(tmp_path, monkeypatch):
    reg = _load_registry()
    state_path = tmp_path / "pipeline_state.json"
    monkeypatch.setattr(reg, "pid_alive", lambda pid: True)

    worker, _ = reg.register_worker(
        task_type="translate",
        stage="stage_b",
        run_id="run_hb",
        pid=3001,
        state_path=state_path,
    )
    assert worker is not None
    assert reg.heartbeat_worker(worker["worker_id"], state_path=state_path)
    assert reg.unregister_worker(worker["worker_id"], status="completed", state_path=state_path)

    state = json.loads(state_path.read_text(encoding="utf-8"))
    statuses = [w["status"] for w in state["workers"]]
    assert "completed" in statuses
