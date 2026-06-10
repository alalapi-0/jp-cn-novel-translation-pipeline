"""Tests for stale lock healing (FS-006)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import heal_stale_locks as heal_mod  # noqa: E402

HEAL_CLI = REPO_ROOT / "scripts" / "heal_stale_locks.py"


def make_repo(tmp_path: Path) -> Path:
    (tmp_path / "workspace" / ".locks").mkdir(parents=True, exist_ok=True)
    (tmp_path / "workspace" / "control").mkdir(parents=True, exist_ok=True)
    return tmp_path


def write_flock(repo: Path, name: str, content: str) -> Path:
    path = repo / "workspace" / ".locks" / name
    path.write_text(content, encoding="utf-8")
    return path


def write_scheduler_lock(repo: Path, pid: int) -> Path:
    path = repo / "workspace" / "control" / "scheduler_running.lock"
    path.write_text(json.dumps({"pid": pid, "owner": "test"}), encoding="utf-8")
    return path


def test_dry_run_reports_stale_without_deleting(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    stale = write_flock(repo, "refine_stage_c_x.lock", "999999999\n")
    report = heal_mod.heal(repo, apply=False)
    assert report["mode"] == "dry_run"
    verdicts = {e["path"]: e["verdict"] for e in report["flock_locks"]}
    assert verdicts["workspace/.locks/refine_stage_c_x.lock"] == "stale"
    assert stale.exists()
    assert report["healed"] == []
    assert any("would_delete" in i["action"] for i in report["needs_attention"])


def test_apply_deletes_stale_flock(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    stale = write_flock(repo, "translate_stage_b_y.lock", "999999999\n")
    report = heal_mod.heal(repo, apply=True)
    assert not stale.exists()
    assert "workspace/.locks/translate_stage_b_y.lock" in report["healed"]


def test_live_pid_lock_is_kept(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    held = write_flock(repo, "translate_stage_b_live.lock", f"{os.getpid()}\n")
    report = heal_mod.heal(repo, apply=True)
    assert held.exists()
    assert "workspace/.locks/translate_stage_b_live.lock" in report["kept"]
    assert report["healed"] == []


def test_unknown_pid_lock_never_auto_deleted(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    weird = write_flock(repo, "translate_stage_b_weird.lock", "not-a-pid\n")
    report = heal_mod.heal(repo, apply=True)
    assert weird.exists()
    assert any(
        i["path"] == "workspace/.locks/translate_stage_b_weird.lock"
        and "inspect manually" in i["action"]
        for i in report["needs_attention"]
    )


def test_scheduler_stale_lock_cleared_with_apply(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    lock = write_scheduler_lock(repo, pid=0)  # dead pid
    report = heal_mod.heal(repo, apply=True)
    assert not lock.exists()
    assert "workspace/control/scheduler_running.lock" in report["healed"]


def test_scheduler_live_lock_kept(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    lock = write_scheduler_lock(repo, pid=os.getpid())
    report = heal_mod.heal(repo, apply=True)
    assert lock.exists()
    assert "workspace/control/scheduler_running.lock" in report["kept"]


def test_cli_json_dry_run(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    write_flock(repo, "refine_stage_c_z.lock", "999999999\n")
    proc = subprocess.run(
        [sys.executable, str(HEAL_CLI), "--json", "--repo-root", str(repo)],
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert proc.returncode == 0, proc.stderr
    doc = json.loads(proc.stdout)
    assert doc["mode"] == "dry_run"
    assert doc["flock_locks"][0]["verdict"] == "stale"
