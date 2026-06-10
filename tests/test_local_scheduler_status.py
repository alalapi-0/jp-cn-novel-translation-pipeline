"""Tests for local scheduler status aggregation (FS-002, spec §9.2)."""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from scheduler.control import request_pause  # noqa: E402
from scheduler.status import collect_status  # noqa: E402

SPEC_FIELDS = [
    "current_phase",
    "next_task",
    "next_round_id",
    "next_chapter_range",
    "active_worker_count",
    "orphan_worker_count",
    "scheduler_lock_status",
    "paused",
    "last_successful_tick",
    "last_blocked_reason",
    "draft_progress",
    "refinement_progress",
    "safe_to_run",
]


def make_repo(tmp_path: Path, chapters: int = 9) -> Path:
    (tmp_path / "input_jp").mkdir(parents=True, exist_ok=True)
    for i in range(1, chapters + 1):
        (tmp_path / "input_jp" / f"{i}-ch.md").write_text("x", encoding="utf-8")
    (tmp_path / "workspace" / "control").mkdir(parents=True, exist_ok=True)
    return tmp_path


def set_queue(repo: Path, anchor: int, per_round: int = 3) -> None:
    path = repo / "workspace" / "control" / "scheduler_queue.json"
    path.write_text(
        json.dumps({"dmr_anchor_chapter": anchor, "chapters_per_round": per_round}),
        encoding="utf-8",
    )


def add_run(
    repo: Path,
    run_id: str,
    chapters: list[int],
    *,
    phase: str = "draft",
    total: int = 30,
    completed: int = 30,
    base: str = "workspace/runs",
    write_progress: bool = True,
    summary: dict | None = None,
) -> None:
    root = repo / base / run_id
    root.mkdir(parents=True, exist_ok=True)
    meta = {
        "run_id": run_id,
        "phase": phase,
        "chapter_files": [f"input_jp/{c}-ch.md" for c in chapters],
    }
    if summary is not None:
        meta["summary"] = summary
    (root / "run_metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    if write_progress:
        progress = {
            "run_id": run_id,
            "total_segments": total,
            "completed_segments": completed,
        }
        (root / "run_progress.json").write_text(json.dumps(progress), encoding="utf-8")


def add_worker(
    repo: Path,
    *,
    task_type: str = "translate",
    controller_pid: int | None = None,
) -> None:
    state_path = repo / "workspace" / "pipeline_state.json"
    state = {"schema_version": 1, "workers": []}
    if state_path.is_file():
        state = json.loads(state_path.read_text(encoding="utf-8"))
    worker = {
        "worker_id": f"w{len(state['workers']) + 1}",
        "status": "in_progress",
        "task_type": task_type,
        "pid": os.getpid(),
        "heartbeat_at": datetime.now(timezone.utc).isoformat(),
    }
    if controller_pid is not None:
        worker["controller_pid"] = controller_pid
    state["workers"].append(worker)
    state_path.write_text(json.dumps(state), encoding="utf-8")


# ---------------------------------------------------------------------------
# Field coverage and progress counting
# ---------------------------------------------------------------------------

def test_all_spec_fields_present(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    report = collect_status(repo)
    for field in SPEC_FIELDS:
        assert field in report, f"missing spec §9.2 field: {field}"


def test_draft_progress_counts_completed_runs_only(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, chapters=9)
    set_queue(repo, anchor=1)
    add_run(repo, "run_a", [1, 2, 3], completed=30, total=30)
    add_run(repo, "run_b", [4, 5, 6], completed=12, total=30)  # partial
    report = collect_status(repo)
    assert report["draft_progress"] == {
        "completed_chapters": 3,
        "total_chapters": 9,
        "percent": 33.33,
    }
    assert report["current_phase"] == "draft"
    assert report["next_task"] == "draft_micro_round"


def test_overlapping_runs_dedupe_chapters(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, chapters=9)
    set_queue(repo, anchor=1)
    add_run(repo, "run_a", [1, 2, 3])
    add_run(repo, "run_b", [3, 4, 5])  # re-run overlap
    report = collect_status(repo)
    assert report["draft_progress"]["completed_chapters"] == 5


def test_archived_runs_count_and_diagnostics_ignored(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, chapters=9)
    set_queue(repo, anchor=1)
    add_run(repo, "run_old", [1, 2, 3], base="workspace/archived_runs")
    add_run(repo, "micro_validate_x", [4, 5, 6])  # diagnostic prefix → ignored
    add_run(repo, "fixture_demo", [7, 8])  # diagnostic prefix → ignored
    report = collect_status(repo)
    assert report["draft_progress"]["completed_chapters"] == 3


def test_legacy_run_without_progress_uses_metadata_summary(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, chapters=9)
    set_queue(repo, anchor=1)
    add_run(
        repo,
        "run_legacy",
        [1, 2, 3],
        write_progress=False,
        summary={"total_segments": 100, "translated_segments": 100, "aborted": False},
    )
    add_run(
        repo,
        "run_aborted",
        [4, 5, 6],
        write_progress=False,
        summary={"total_segments": 100, "translated_segments": 100, "aborted": True},
    )
    add_run(
        repo,
        "run_incomplete_legacy",
        [7, 8],
        write_progress=False,
        summary={"total_segments": 100, "translated_segments": 40, "aborted": False},
    )
    report = collect_status(repo)
    assert report["draft_progress"]["completed_chapters"] == 3


def test_refine_runs_feed_refinement_progress(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, chapters=9)
    set_queue(repo, anchor=1)
    add_run(repo, "run_d", [1, 2, 3])
    add_run(repo, "run_r", [1, 2], phase="refine")
    report = collect_status(repo)
    assert report["refinement_progress"]["completed_chapters"] == 2
    assert report["draft_progress"]["completed_chapters"] == 3


# ---------------------------------------------------------------------------
# Next round / chapter range mapping
# ---------------------------------------------------------------------------

def test_next_round_anchor_math(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, chapters=9)
    set_queue(repo, anchor=1, per_round=3)
    add_run(repo, "run_a", [1, 2, 3])
    report = collect_status(repo)
    assert report["next_round_id"] == "D-MR-002"
    assert report["next_chapter_range"] == "4-6"


def test_partial_round_keeps_canonical_range(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, chapters=9)
    set_queue(repo, anchor=1, per_round=3)
    add_run(repo, "run_a", [1, 2, 3, 4])  # round 2 partially covered
    report = collect_status(repo)
    assert report["next_round_id"] == "D-MR-002"
    assert report["next_chapter_range"] == "4-6"


def test_last_round_truncated_at_book_end(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, chapters=7)
    set_queue(repo, anchor=1, per_round=3)
    add_run(repo, "run_a", [1, 2, 3, 4, 5, 6])
    report = collect_status(repo)
    assert report["next_round_id"] == "D-MR-003"
    assert report["next_chapter_range"] == "7-7"


def test_gap_below_anchor_flagged_as_backfill(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, chapters=9)
    set_queue(repo, anchor=5, per_round=3)
    add_run(repo, "run_a", [1, 3, 4])  # chapter 2 missing below anchor
    report = collect_status(repo)
    assert report["next_round_id"] is None
    assert report["next_chapter_range"] == "2-2"
    assert report["next_task"] == "draft_gap_backfill"


def test_draft_complete_transitions_to_consistency(tmp_path: Path) -> None:
    repo = make_repo(tmp_path, chapters=6)
    set_queue(repo, anchor=1)
    add_run(repo, "run_a", [1, 2, 3, 4, 5, 6])
    report = collect_status(repo)
    assert report["current_phase"] == "consistency"
    assert report["next_task"] == "draft_consistency_audit"
    assert report["next_round_id"] is None
    assert report["next_chapter_range"] is None
    assert report["draft_progress"]["percent"] == 100.0


# ---------------------------------------------------------------------------
# safe_to_run aggregation
# ---------------------------------------------------------------------------

def test_safe_to_run_true_on_clean_repo(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    report = collect_status(repo)
    assert report["safe_to_run"] is True
    assert report["detail"]["blocked_reasons"] == []


def test_paused_blocks_safe_to_run(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    request_pause(reason="test", repo_root=repo)
    report = collect_status(repo)
    assert report["paused"] is True
    assert report["safe_to_run"] is False
    assert "paused" in report["detail"]["blocked_reasons"]
    assert report["next_task"] == "paused"


def test_held_lock_blocks_safe_to_run(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    lock = repo / "workspace" / "control" / "scheduler_running.lock"
    lock.write_text(json.dumps({"pid": os.getpid()}), encoding="utf-8")
    report = collect_status(repo)
    assert report["scheduler_lock_status"] == "held"
    assert report["safe_to_run"] is False
    assert "lock_held" in report["detail"]["blocked_reasons"]


def test_stale_lock_blocks_safe_to_run(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    lock = repo / "workspace" / "control" / "scheduler_running.lock"
    lock.write_text(json.dumps({"pid": 0}), encoding="utf-8")
    report = collect_status(repo)
    assert report["scheduler_lock_status"] == "stale"
    assert report["safe_to_run"] is False
    assert "stale_lock" in report["detail"]["blocked_reasons"]


def test_orphan_worker_blocks_safe_to_run(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    add_worker(repo, controller_pid=0)  # missing controller → orphan
    report = collect_status(repo)
    assert report["orphan_worker_count"] == 1
    assert report["safe_to_run"] is False
    assert "orphan_workers" in report["detail"]["blocked_reasons"]


def test_active_worker_blocks_safe_to_run(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    add_worker(repo, controller_pid=os.getpid())  # supervised → active, not orphan
    report = collect_status(repo)
    assert report["active_worker_count"] == 1
    assert report["orphan_worker_count"] == 0
    assert report["safe_to_run"] is False
    assert "active_workers" in report["detail"]["blocked_reasons"]


# ---------------------------------------------------------------------------
# Tick state passthrough
# ---------------------------------------------------------------------------

def test_tick_state_passthrough(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    tick_state = repo / "workspace" / "control" / "scheduler_tick_state.json"
    tick_state.write_text(
        json.dumps(
            {
                "last_successful_tick": "2026-06-11T00:00:00+00:00",
                "last_blocked_reason": "paused",
            }
        ),
        encoding="utf-8",
    )
    report = collect_status(repo)
    assert report["last_successful_tick"] == "2026-06-11T00:00:00+00:00"
    assert report["last_blocked_reason"] == "paused"


def test_tick_state_defaults_to_none(tmp_path: Path) -> None:
    repo = make_repo(tmp_path)
    report = collect_status(repo)
    assert report["last_successful_tick"] is None
    assert report["last_blocked_reason"] is None
