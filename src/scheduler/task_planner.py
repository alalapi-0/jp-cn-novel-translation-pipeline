"""Phase -> next-task decision table for scheduler ticks (FS-004, spec §9.1).

Maps a status snapshot (FS-002 ``collect_status`` output shape) onto exactly
one next task. Six task families exist across the production line:

    draft           -> next D-MR micro round, or a gap backfill micro round
    consistency     -> consistency audit sub-task        (lands FS-031..037)
    baseline_lock   -> baseline lock                     (lands FS-038)
    refinement      -> next R-MR micro round             (lands FS-040+)
    final_review    -> final review sub-task             (lands FS-046+)
    production_candidate -> candidate build              (lands FS-050)

Only the draft family is executable today, by spawning a *supervised*
``run_micro_round.py`` child process (never detached). Every other branch
returns an explicit ``implemented=False`` plan with ``not_implemented``
semantics so a tick can report it instead of silently skipping — and so a
future real-mode tick cannot accidentally run machinery that does not exist.

The planner itself never executes anything and never spends API budget;
it only decides and (for the draft family) renders the exact command line,
including pass-through budget limits.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

RUN_MICRO_ROUND_REL = "scripts/run_micro_round.py"

# Budget keys accepted from callers, mapped to run_micro_round CLI flags.
BUDGET_FLAGS = {
    "max_api_calls": "--max-api-calls",
    "max_segments": "--max-segments",
    "max_wall_time_minutes": "--max-wall-time-minutes",
    "batch_token_budget": "--batch-token-budget",
    "max_segments_per_call": "--max-segments-per-call",
}

_NOT_IMPLEMENTED_ROUNDS = {
    "consistency": ("consistency_audit", "consistency tooling lands in FS-031..FS-037"),
    "baseline_lock": ("baseline_lock", "baseline lock lands in FS-038"),
    "refinement": ("refine_micro_round", "refinement pipeline lands in FS-040+"),
    "final_review": ("final_review", "final review tooling lands in FS-046+"),
    "production_candidate": ("production_candidate", "candidate build lands in FS-050"),
}


@dataclass
class TaskPlan:
    """One tick's decision: what to run next (or why nothing can run)."""

    task_type: str
    implemented: bool
    reason: str
    round_id: str | None = None
    chapter_range: str | None = None
    command: list[str] | None = None
    budget: dict[str, Any] = field(default_factory=dict)
    mode: str = "dry_run"

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_type": self.task_type,
            "implemented": self.implemented,
            "reason": self.reason,
            "round_id": self.round_id,
            "chapter_range": self.chapter_range,
            "command": self.command,
            "budget": self.budget,
            "mode": self.mode,
        }


def _parse_range(chapter_range: str) -> tuple[int, int]:
    start_s, _, end_s = chapter_range.partition("-")
    start = int(start_s)
    end = int(end_s) if end_s else start
    return start, max(start, end)


def _first_block(chapter_range: str, per_round: int) -> str:
    """Cut the first micro-round-sized block out of a (possibly long) range.

    Gap backfill ranges arrive whole (e.g. 191-202); one tick must only run
    one micro round, so it takes the first ``per_round`` chapters.
    """
    start, end = _parse_range(chapter_range)
    block_end = min(start + max(1, per_round) - 1, end)
    return f"{start}-{block_end}"


def _draft_command(
    *,
    round_id: str,
    chapter_range: str,
    mode: str,
    budgets: dict[str, Any],
    python_executable: str,
) -> list[str]:
    cmd = [
        python_executable,
        RUN_MICRO_ROUND_REL,
        "--phase",
        "draft",
        "--round-id",
        round_id,
        "--chapter-range",
        chapter_range,
        "--supervised",
    ]
    if mode == "real":
        cmd.append("--real-api")
    else:
        # run_micro_round defaults to --real-api=True: a dry-run plan must
        # disarm it explicitly, belt and braces.
        cmd.extend(["--dry-run", "--no-real-api"])
    for key, flag in BUDGET_FLAGS.items():
        if key in budgets and budgets[key] is not None:
            cmd.extend([flag, str(budgets[key])])
    return cmd


def plan_next_task(
    status: dict[str, Any],
    *,
    mode: str = "dry_run",
    budgets: dict[str, Any] | None = None,
    repo_root: Path | None = None,  # noqa: ARG001 - reserved for later planners
    python_executable: str = "python3",
) -> TaskPlan:
    """Decide the single next task for one tick from a status snapshot.

    ``status`` is the FS-002 ``collect_status`` dict (or a compatible
    fixture). Exactly one plan is returned — a tick never runs tasks
    concurrently.
    """
    if mode not in ("dry_run", "real"):
        raise ValueError(f"unknown planner mode: {mode!r}")
    budgets = dict(budgets or {})
    unknown = set(budgets) - set(BUDGET_FLAGS)
    if unknown:
        raise ValueError(f"unknown budget keys: {sorted(unknown)}")

    if status.get("paused"):
        return TaskPlan(
            task_type="paused",
            implemented=False,
            reason="scheduler paused via pause file",
            mode=mode,
        )

    phase = str(status.get("current_phase") or "")

    if phase == "draft":
        next_task = str(status.get("next_task") or "")
        detail = status.get("detail") or {}
        per_round = int(detail.get("chapters_per_round") or 3)
        chapter_range = status.get("next_chapter_range")
        if not chapter_range:
            return TaskPlan(
                task_type="draft_micro_round",
                implemented=False,
                reason="draft phase but no next chapter range in status snapshot",
                mode=mode,
            )
        if next_task == "draft_gap_backfill":
            block = _first_block(str(chapter_range), per_round)
            round_id = f"GAP-{block}"
            task_type = "draft_gap_backfill"
        else:
            block = str(chapter_range)
            round_id = str(status.get("next_round_id") or f"D-MR-{block}")
            task_type = "draft_micro_round"
        return TaskPlan(
            task_type=task_type,
            implemented=True,
            reason="next draft micro round per status snapshot",
            round_id=round_id,
            chapter_range=block,
            command=_draft_command(
                round_id=round_id,
                chapter_range=block,
                mode=mode,
                budgets=budgets,
                python_executable=python_executable,
            ),
            budget=budgets,
            mode=mode,
        )

    if phase in _NOT_IMPLEMENTED_ROUNDS:
        task_type, reason = _NOT_IMPLEMENTED_ROUNDS[phase]
        return TaskPlan(
            task_type=task_type,
            implemented=False,
            reason=f"not_implemented: {reason}",
            mode=mode,
        )

    return TaskPlan(
        task_type="unknown",
        implemented=False,
        reason=f"not_implemented: unrecognized phase {phase!r}",
        mode=mode,
    )
