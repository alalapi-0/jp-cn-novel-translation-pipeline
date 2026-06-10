"""Tests for the tick task decision table (FS-004, spec §9.1)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from scheduler.task_planner import plan_next_task  # noqa: E402


def make_status(
    *,
    phase: str = "draft",
    next_task: str = "draft_micro_round",
    round_id: str | None = "D-MR-001",
    chapter_range: str | None = "203-205",
    paused: bool = False,
    per_round: int = 3,
) -> dict:
    return {
        "current_phase": phase,
        "next_task": next_task,
        "next_round_id": round_id,
        "next_chapter_range": chapter_range,
        "paused": paused,
        "detail": {"chapters_per_round": per_round},
    }


# ---------------------------------------------------------------------------
# Decision table: one correct next task per phase fixture
# ---------------------------------------------------------------------------

def test_draft_phase_plans_micro_round_command() -> None:
    plan = plan_next_task(make_status(), mode="dry_run")
    assert plan.implemented is True
    assert plan.task_type == "draft_micro_round"
    assert plan.round_id == "D-MR-001"
    assert plan.chapter_range == "203-205"
    cmd = plan.command
    assert cmd is not None
    assert cmd[1].endswith("run_micro_round.py")
    assert cmd[cmd.index("--round-id") + 1] == "D-MR-001"
    assert cmd[cmd.index("--chapter-range") + 1] == "203-205"
    assert "--supervised" in cmd
    # dry-run plans must disarm run_micro_round's real-api default.
    assert "--dry-run" in cmd
    assert "--no-real-api" in cmd
    assert "--real-api" not in cmd


def test_draft_gap_backfill_takes_first_block_only() -> None:
    status = make_status(
        next_task="draft_gap_backfill",
        round_id=None,
        chapter_range="191-202",
        per_round=3,
    )
    plan = plan_next_task(status)
    assert plan.implemented is True
    assert plan.task_type == "draft_gap_backfill"
    assert plan.round_id == "GAP-191-193"
    assert plan.chapter_range == "191-193"  # one micro round per tick
    assert plan.command is not None
    assert plan.command[plan.command.index("--chapter-range") + 1] == "191-193"


def test_consistency_phase_not_implemented() -> None:
    status = make_status(
        phase="consistency",
        next_task="draft_consistency_audit",
        round_id=None,
        chapter_range=None,
    )
    plan = plan_next_task(status)
    assert plan.implemented is False
    assert plan.task_type == "consistency_audit"
    assert "not_implemented" in plan.reason
    assert plan.command is None


def test_baseline_lock_phase_not_implemented() -> None:
    status = make_status(phase="baseline_lock", next_task="baseline_lock", round_id=None, chapter_range=None)
    plan = plan_next_task(status)
    assert plan.implemented is False
    assert plan.task_type == "baseline_lock"
    assert "not_implemented" in plan.reason


def test_refinement_phase_not_implemented() -> None:
    status = make_status(phase="refinement", next_task="refine_micro_round", round_id="R-MR-001", chapter_range="1-3")
    plan = plan_next_task(status)
    assert plan.implemented is False
    assert plan.task_type == "refine_micro_round"
    assert "not_implemented" in plan.reason


def test_final_review_phase_not_implemented() -> None:
    status = make_status(phase="final_review", next_task="final_review", round_id=None, chapter_range=None)
    plan = plan_next_task(status)
    assert plan.implemented is False
    assert plan.task_type == "final_review"


def test_production_candidate_phase_not_implemented() -> None:
    status = make_status(phase="production_candidate", next_task="production_candidate", round_id=None, chapter_range=None)
    plan = plan_next_task(status)
    assert plan.implemented is False
    assert plan.task_type == "production_candidate"


def test_unknown_phase_is_explicit() -> None:
    plan = plan_next_task(make_status(phase="weird"))
    assert plan.implemented is False
    assert plan.task_type == "unknown"
    assert "not_implemented" in plan.reason


def test_paused_status_yields_paused_plan() -> None:
    plan = plan_next_task(make_status(paused=True))
    assert plan.implemented is False
    assert plan.task_type == "paused"


# ---------------------------------------------------------------------------
# Budget pass-through and modes
# ---------------------------------------------------------------------------

def test_budget_passthrough_into_command() -> None:
    plan = plan_next_task(
        make_status(),
        budgets={"max_api_calls": 5, "max_wall_time_minutes": 30, "max_segments": 120},
    )
    cmd = plan.command
    assert cmd is not None
    assert cmd[cmd.index("--max-api-calls") + 1] == "5"
    assert cmd[cmd.index("--max-wall-time-minutes") + 1] == "30"
    assert cmd[cmd.index("--max-segments") + 1] == "120"
    assert plan.budget == {"max_api_calls": 5, "max_wall_time_minutes": 30, "max_segments": 120}


def test_unknown_budget_key_rejected() -> None:
    with pytest.raises(ValueError, match="unknown budget keys"):
        plan_next_task(make_status(), budgets={"max_cost_usd": 1})


def test_real_mode_arms_real_api_flag() -> None:
    plan = plan_next_task(make_status(), mode="real", budgets={"max_api_calls": 5})
    cmd = plan.command
    assert cmd is not None
    assert "--real-api" in cmd
    assert "--dry-run" not in cmd
    assert "--no-real-api" not in cmd
    assert plan.mode == "real"


def test_unknown_mode_rejected() -> None:
    with pytest.raises(ValueError, match="unknown planner mode"):
        plan_next_task(make_status(), mode="yolo")


def test_python_executable_respected() -> None:
    plan = plan_next_task(make_status(), python_executable="/opt/py/bin/python")
    assert plan.command is not None
    assert plan.command[0] == "/opt/py/bin/python"


def test_draft_without_range_is_explicitly_unplannable() -> None:
    status = make_status(round_id=None, chapter_range=None)
    plan = plan_next_task(status)
    assert plan.implemented is False
    assert plan.task_type == "draft_micro_round"
    assert "no next chapter range" in plan.reason


def test_single_chapter_gap_block() -> None:
    status = make_status(
        next_task="draft_gap_backfill",
        round_id=None,
        chapter_range="2-2",
        per_round=3,
    )
    plan = plan_next_task(status)
    assert plan.round_id == "GAP-2-2"
    assert plan.chapter_range == "2-2"
