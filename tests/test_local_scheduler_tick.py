"""Tests for the local scheduler tick skeleton (FS-003, spec §9.1)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

import scheduler.tick as tick_mod  # noqa: E402
from scheduler.control import request_pause  # noqa: E402
from scheduler.tick import EXIT_BLOCKED, EXIT_ERROR, EXIT_OK, run_tick  # noqa: E402

TICK_CLI = REPO_ROOT / "scripts" / "local_scheduler_tick.py"


# ---------------------------------------------------------------------------
# Fixture helpers (mirrors test_local_scheduler_status.py conventions)
# ---------------------------------------------------------------------------

def make_repo(tmp_path: Path, chapters: int = 9) -> Path:
    (tmp_path / "input_jp").mkdir(parents=True, exist_ok=True)
    for i in range(1, chapters + 1):
        (tmp_path / "input_jp" / f"{i}-ch.md").write_text("x", encoding="utf-8")
    (tmp_path / "workspace" / "control").mkdir(parents=True, exist_ok=True)
    queue = tmp_path / "workspace" / "control" / "scheduler_queue.json"
    queue.write_text(
        json.dumps({"dmr_anchor_chapter": 1, "chapters_per_round": 3}),
        encoding="utf-8",
    )
    # Stub run_micro_round so the default dispatcher has something safe to
    # exec inside the fixture repo (prints its argv, exits 0).
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir(exist_ok=True)
    (scripts_dir / "run_micro_round.py").write_text(
        "import json, sys\nprint(json.dumps({'stub': True, 'argv': sys.argv[1:]}))\n",
        encoding="utf-8",
    )
    return tmp_path


def write_lock(repo: Path, pid: int) -> Path:
    lock = repo / "workspace" / "control" / "scheduler_running.lock"
    lock.write_text(json.dumps({"pid": pid, "owner": "other"}), encoding="utf-8")
    return lock


def lock_path(repo: Path) -> Path:
    return repo / "workspace" / "control" / "scheduler_running.lock"


def add_worker(repo: Path, *, controller_pid: int | None = None) -> None:
    state_path = repo / "workspace" / "pipeline_state.json"
    state = {"schema_version": 1, "workers": []}
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    worker = {
        "worker_id": f"w{len(state['workers']) + 1}",
        "status": "in_progress",
        "task_type": "translate",
        "pid": os.getpid(),
        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
    }
    if controller_pid is not None:
        worker["controller_pid"] = controller_pid
    state["workers"].append(worker)
    state_path.write_text(json.dumps(state), encoding="utf-8")


def tick_reports(repo: Path) -> list[Path]:
    reports_dir = repo / "workspace" / "control" / "tick_reports"
    if not reports_dir.is_dir():
        return []
    return sorted(reports_dir.glob("tick_*.json"))


def read_tick_state(repo: Path) -> dict:
    path = repo / "workspace" / "control" / "scheduler_tick_state.json"
    return json.loads(path.read_text(encoding="utf-8"))


# ---------------------------------------------------------------------------
# Happy path: dry-run completes cleanly
# ---------------------------------------------------------------------------

def fake_executor(calls: list[dict]):
    """Test executor: records the plan it was handed, performs nothing."""

    def execute(plan: dict) -> dict:
        calls.append(plan)
        return {"executed": False, "fake": True, "task_type": plan.get("task_type")}

    return execute


def test_dry_run_tick_completes_with_exit_0(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    calls: list[dict] = []
    result = run_tick(repo, executor=fake_executor(calls))
    assert result["status"] == "completed"
    assert result["exit_code"] == EXIT_OK
    assert result["mode"] == "dry_run"
    assert result["next_task"]["task"] == "draft_micro_round"
    assert result["next_task"]["round_id"] == "D-MR-001"
    # The executor receives the FS-004 plan for the same round.
    assert len(calls) == 1
    assert calls[0]["task_type"] == "draft_micro_round"
    assert calls[0]["round_id"] == "D-MR-001"
    assert calls[0]["implemented"] is True


def test_tick_report_written_to_tick_reports_dir(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    result = run_tick(repo, executor=fake_executor([]))
    reports = tick_reports(repo)
    assert len(reports) == 1
    assert result["report_path"] == str(reports[0])
    doc = json.loads(reports[0].read_text(encoding="utf-8"))
    assert doc["tick_id"] == result["tick_id"]
    assert doc["status"] == "completed"
    assert doc["mode"] == "dry_run"
    assert doc["plan"]["task_type"] == "draft_micro_round"


def test_completed_tick_updates_tick_state(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    result = run_tick(repo, executor=fake_executor([]))
    state = read_tick_state(repo)
    assert state["last_successful_tick"] == result["finished_at"]
    assert state["last_blocked_reason"] is None
    assert state["last_tick_status"] == "completed"


def test_lock_released_after_tick_and_rerunnable(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    first = run_tick(repo, executor=fake_executor([]))
    assert not lock_path(repo).exists()
    second = run_tick(repo, executor=fake_executor([]))
    assert first["status"] == second["status"] == "completed"
    assert len(tick_reports(repo)) == 2


def test_real_mode_without_budget_refused(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    try:
        run_tick(repo, dry_run=False)
    except ValueError as exc:
        assert "max_api_calls" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("unbounded real tick must be rejected")


def test_real_mode_with_budget_arms_real_api(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    calls: list[dict] = []
    result = run_tick(
        repo,
        dry_run=False,
        budgets={"max_api_calls": 5},
        executor=fake_executor(calls),
    )
    assert result["status"] == "completed"
    assert result["mode"] == "real"
    plan = calls[0]
    assert plan["mode"] == "real"
    cmd = plan["command"]
    assert "--real-api" in cmd
    assert "--dry-run" not in cmd
    assert "--no-real-api" not in cmd
    assert cmd[cmd.index("--max-api-calls") + 1] == "5"


# ---------------------------------------------------------------------------
# FS-004: planner wiring inside the tick
# ---------------------------------------------------------------------------

def test_tick_plan_carries_run_micro_round_command(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    result = run_tick(repo, executor=fake_executor([]), budgets={"max_api_calls": 5})
    plan = result["plan"]
    assert plan["implemented"] is True
    cmd = plan["command"]
    assert cmd[1].endswith("run_micro_round.py")
    assert "--dry-run" in cmd
    assert "--no-real-api" in cmd
    assert cmd[cmd.index("--max-api-calls") + 1] == "5"


def test_tick_consistency_phase_plans_fix_plan(tmp_path: Path) -> None:
    """All chapters done -> consistency phase -> build_local_fix_plan (FS-036)."""
    repo = make_repo(tmp_path, chapters=3)
    root = repo / "workspace" / "runs" / "run_all"
    root.mkdir(parents=True, exist_ok=True)
    meta = {
        "run_id": "run_all",
        "phase": "draft",
        "chapter_files": [f"input_jp/{c}-ch.md" for c in (1, 2, 3)],
    }
    (root / "run_metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    progress = {"run_id": "run_all", "total_segments": 30, "completed_segments": 30}
    (root / "run_progress.json").write_text(json.dumps(progress), encoding="utf-8")

    calls: list[dict] = []
    result = run_tick(repo, executor=fake_executor(calls))
    assert result["status"] == "completed"
    assert result["plan"]["implemented"] is True
    assert result["plan"]["task_type"] == "consistency_build_fix_plan"
    assert len(calls) == 1
    assert calls[0]["task_type"] == "consistency_build_fix_plan"


def test_dispatched_command_failure_is_tick_error(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    def failing_dispatch(plan: dict) -> dict:
        return {"executed": True, "returncode": 3, "stdout_tail": "", "stderr_tail": "boom"}

    result = run_tick(repo, executor=failing_dispatch)
    assert result["status"] == "error"
    assert result["exit_code"] == EXIT_ERROR
    assert result["blocked_reason"] == "dispatched_command_failed"
    assert not lock_path(repo).exists()


# ---------------------------------------------------------------------------
# Pause behaviour
# ---------------------------------------------------------------------------

def test_paused_skips_without_executing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    request_pause(reason="test", repo_root=repo)
    calls: list[dict] = []
    result = run_tick(repo, executor=lambda task: calls.append(task) or {})
    assert result["status"] == "skipped_paused"
    assert result["exit_code"] == EXIT_OK
    assert result["execution"] is None
    assert calls == []
    assert not lock_path(repo).exists()
    state = read_tick_state(repo)
    assert state["last_blocked_reason"] == "paused"


def test_paused_preserves_last_successful_tick(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    ok = run_tick(repo, executor=fake_executor([]))
    request_pause(reason="test", repo_root=repo)
    run_tick(repo)
    state = read_tick_state(repo)
    assert state["last_successful_tick"] == ok["finished_at"]
    assert state["last_blocked_reason"] == "paused"


def test_default_dispatcher_runs_stub_subprocess(tmp_path: Path) -> None:
    """End-to-end inside the fixture: the default dispatcher execs the
    planned command (stubbed run_micro_round) and records its outcome."""
    repo = make_repo(tmp_path)
    result = run_tick(repo, budgets={"max_api_calls": 2})
    assert result["status"] == "completed"
    execution = result["execution"]
    assert execution["executed"] is True
    assert execution["returncode"] == 0
    assert '"stub": true' in execution["stdout_tail"]
    assert "--max-api-calls" in execution["stdout_tail"]


def test_pause_rechecked_after_lock_acquired(tmp_path: Path, monkeypatch) -> None:
    """A pause requested between the gate and the lock must still win."""
    repo = make_repo(tmp_path)
    answers = iter([False, True])  # gate check, then post-lock re-check
    monkeypatch.setattr(tick_mod, "is_paused", lambda root: next(answers))
    calls: list[dict] = []
    result = run_tick(repo, executor=lambda task: calls.append(task) or {})
    assert result["status"] == "skipped_paused"
    assert calls == []
    assert not lock_path(repo).exists()


# ---------------------------------------------------------------------------
# Lock behaviour
# ---------------------------------------------------------------------------

def test_lock_held_exits_immediately_without_executing(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write_lock(repo, pid=os.getpid())  # alive holder
    before = lock_path(repo).read_text(encoding="utf-8")
    calls: list[dict] = []
    result = run_tick(repo, executor=lambda task: calls.append(task) or {})
    assert result["status"] == "skipped_lock_held"
    assert result["exit_code"] == EXIT_OK
    assert calls == []
    # The foreign lock must be left untouched.
    assert lock_path(repo).read_text(encoding="utf-8") == before


def test_stale_lock_blocks_and_is_not_cleared(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write_lock(repo, pid=0)  # dead holder -> stale
    result = run_tick(repo)
    assert result["status"] == "blocked_stale_lock"
    assert result["exit_code"] == EXIT_BLOCKED
    # FS-006 owns stale cleanup; the tick must not reclaim.
    assert lock_path(repo).exists()
    state = read_tick_state(repo)
    assert state["last_blocked_reason"] == "stale_lock"


def test_acquire_race_with_vanished_lock_is_polite_skip(tmp_path: Path, monkeypatch) -> None:
    """A 'stale' raised at acquire-time with no lock left on disk is a race
    against a finishing tick, not a genuinely stale lock."""
    repo = make_repo(tmp_path)

    def raise_stale(**kwargs):
        raise tick_mod.SchedulerLockError("stale_lock", holder={})

    monkeypatch.setattr(tick_mod, "acquire_lock", raise_stale)
    result = run_tick(repo)
    assert result["status"] == "skipped_lock_held"
    assert result["blocked_reason"] == "lock_race"
    assert result["exit_code"] == EXIT_OK


def test_concurrent_ticks_are_mutually_exclusive(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    barrier = threading.Barrier(2)
    results: list[dict] = []

    def slow_executor(task: dict) -> dict:
        time.sleep(0.3)
        return {"executed": False, "mode": "dry_run", "planned_task": task}

    def runner() -> None:
        barrier.wait()
        results.append(run_tick(repo, executor=slow_executor))

    threads = [threading.Thread(target=runner) for _ in range(2)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    statuses = sorted(r["status"] for r in results)
    assert statuses == ["completed", "skipped_lock_held"]
    assert not lock_path(repo).exists()


# ---------------------------------------------------------------------------
# Worker health behaviour
# ---------------------------------------------------------------------------

def test_orphan_workers_block_tick(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    add_worker(repo, controller_pid=0)  # dead controller -> orphan
    result = run_tick(repo)
    assert result["status"] == "blocked_orphan_workers"
    assert result["exit_code"] == EXIT_BLOCKED
    assert result["execution"] is None
    assert not lock_path(repo).exists()


def test_active_supervised_worker_yields_politely(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    add_worker(repo, controller_pid=os.getpid())  # supervised, alive
    result = run_tick(repo)
    assert result["status"] == "skipped_active_workers"
    assert result["exit_code"] == EXIT_OK
    assert result["execution"] is None


# ---------------------------------------------------------------------------
# Executor failure: lock must still be released, exit code 1
# ---------------------------------------------------------------------------

def test_executor_error_exit_1_and_lock_released(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)

    def boom(task: dict) -> dict:
        raise RuntimeError("synthetic executor failure")

    result = run_tick(repo, executor=boom)
    assert result["status"] == "error"
    assert result["exit_code"] == EXIT_ERROR
    assert "synthetic executor failure" in result["execution"]["error"]
    assert not lock_path(repo).exists()
    state = read_tick_state(repo)
    assert state["last_blocked_reason"] == "executor_error"


# ---------------------------------------------------------------------------
# CLI behaviour (subprocess, fixture repo via hidden --repo-root)
# ---------------------------------------------------------------------------

def run_cli(repo: Path, *extra: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(TICK_CLI), "--dry-run", "--repo-root", str(repo), *extra]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=120)


def test_cli_dry_run_exit_0_with_json(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    proc = run_cli(repo, "--json")
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    assert doc["status"] == "completed"
    assert doc["mode"] == "dry_run"
    assert len(tick_reports(repo)) == 1


def test_cli_paused_exit_0(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    request_pause(reason="test", repo_root=repo)
    proc = run_cli(repo, "--json")
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    assert doc["status"] == "skipped_paused"


def test_cli_stale_lock_exit_2(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write_lock(repo, pid=0)
    proc = run_cli(repo)
    assert proc.returncode == 2
    assert "blocked_stale_lock" in proc.stdout
