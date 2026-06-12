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

import json
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
    "baseline_lock": ("baseline_lock", "baseline lock lands in FS-038"),
    "refinement": ("refine_micro_round", "refinement pipeline lands in FS-040+"),
    "final_review": ("final_review", "final review tooling lands in FS-046+"),
    "production_candidate": ("production_candidate", "candidate build lands in FS-050"),
}

BUILD_FIX_PLAN_REL = "scripts/build_local_fix_plan.py"
APPLY_TERM_FIXES_REL = "scripts/apply_term_fixes.py"
ARBITRATE_CONFLICTS_REL = "scripts/arbitrate_conflicts.py"
RUN_CONSISTENCY_RETRANSLATE_REL = "scripts/run_consistency_retranslate.py"
BUILD_CONSISTENCY_REPORT_REL = "scripts/build_draft_consistency_report.py"

_CONSISTENCY_TASKS: dict[str, tuple[str, str, str]] = {
    # next_task -> (task_type, script_rel, human reason)
    "draft_consistency_audit": (
        "consistency_build_fix_plan",
        BUILD_FIX_PLAN_REL,
        "build local fix plan from FS-034/035 audits",
    ),
    "consistency_build_fix_plan": (
        "consistency_build_fix_plan",
        BUILD_FIX_PLAN_REL,
        "build local fix plan from FS-034/035 audits",
    ),
    "consistency_apply_term_fixes": (
        "consistency_apply_term_fixes",
        APPLY_TERM_FIXES_REL,
        "apply deterministic term patches (dry-run unless real mode)",
    ),
    "consistency_arbitrate": (
        "consistency_arbitrate",
        ARBITRATE_CONFLICTS_REL,
        "Level 4 model arbitration for rule-undecidable conflicts",
    ),
    "consistency_build_report": (
        "consistency_build_report",
        BUILD_CONSISTENCY_REPORT_REL,
        "aggregate full draft consistency report (stats only)",
    ),
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
    resume_run_id: str = ""

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
            "resume_run_id": self.resume_run_id,
        }


def _parse_range(chapter_range: str) -> tuple[int, int]:
    start_s, _, end_s = chapter_range.partition("-")
    start = int(start_s)
    end = int(end_s) if end_s else start
    return start, max(start, end)


_DIAGNOSTIC_PREFIXES = (
    "draft-a-",
    "micro_validate",
    "fixture_",
    "asset-context",
    "round_50_e2e",
)


def find_resumable_run(repo_root: Path | None, chapter_start: int) -> str:
    """Find an interrupted run for this exact chapter offset to resume.

    Resuming our own interrupted run (same offset, status in_progress) via
    ``--run-id`` + checkpoint hydration prevents re-translating segments
    that already completed (FS-008 acceptance: no duplicate translation).
    This is distinct from the forbidden *reuse* of a finished run directory
    for a different chapter range (FS-002 data-loss root cause): the match
    is strictly same-offset + in_progress.
    """
    if repo_root is None:
        return ""
    runs_root = repo_root / "workspace" / "runs"
    if not runs_root.is_dir():
        return ""
    offset = chapter_start - 1
    candidates: list[tuple[float, str]] = []
    for progress_path in runs_root.glob("*/run_progress.json"):
        run_id = progress_path.parent.name
        if any(run_id.startswith(p) for p in _DIAGNOSTIC_PREFIXES):
            continue
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            meta = json.loads(
                (progress_path.parent / "run_metadata.json").read_text(encoding="utf-8")
            )
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(progress, dict) or not isinstance(meta, dict):
            continue
        if str(progress.get("status") or "") != "in_progress":
            continue
        if int(meta.get("chapter_offset") if meta.get("chapter_offset") is not None else -1) != offset:
            continue
        candidates.append((progress_path.stat().st_mtime, run_id))
    if not candidates:
        return ""
    return max(candidates)[1]


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
    resume_run_id: str = "",
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
    if resume_run_id:
        cmd.extend(["--run-id", resume_run_id])
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


def _consistency_command(
    *,
    script_rel: str,
    mode: str,
    python_executable: str,
    budgets: dict[str, Any] | None = None,
) -> list[str]:
    budgets = budgets or {}
    cmd = [python_executable, script_rel]
    if script_rel.endswith("build_local_fix_plan.py"):
        cmd.append("--json")
    elif script_rel.endswith("apply_term_fixes.py"):
        if mode == "real":
            cmd.append("--apply")
        else:
            cmd.append("--dry-run")
        cmd.append("--json")
    elif script_rel.endswith("arbitrate_conflicts.py"):
        if mode == "real":
            cmd.append("--real-api")
        else:
            cmd.append("--dry-run")
        if budgets.get("max_api_calls"):
            cmd.extend(["--max-api-calls", str(budgets["max_api_calls"])])
        cmd.append("--json")
    elif script_rel.endswith("run_consistency_retranslate.py"):
        if mode == "real":
            cmd.append("--real-api")
        else:
            cmd.append("--dry-run")
        if budgets.get("max_api_calls"):
            cmd.extend(["--max-api-calls", str(budgets["max_api_calls"])])
        if budgets.get("max_segments"):
            cmd.extend(["--limit", str(budgets["max_segments"])])
        cmd.append("--json")
    elif script_rel.endswith("build_draft_consistency_report.py"):
        cmd.append("--json")
    return cmd


def plan_next_task(
    status: dict[str, Any],
    *,
    mode: str = "dry_run",
    budgets: dict[str, Any] | None = None,
    repo_root: Path | None = None,
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
        block_start, _ = _parse_range(block)
        resume_run_id = find_resumable_run(repo_root, block_start)
        return TaskPlan(
            task_type=task_type,
            implemented=True,
            reason="next draft micro round per status snapshot"
            + (f" (resuming interrupted run {resume_run_id})" if resume_run_id else ""),
            round_id=round_id,
            chapter_range=block,
            command=_draft_command(
                round_id=round_id,
                chapter_range=block,
                mode=mode,
                budgets=budgets,
                python_executable=python_executable,
                resume_run_id=resume_run_id,
            ),
            budget=budgets,
            mode=mode,
            resume_run_id=resume_run_id,
        )

    if phase == "consistency":
        next_task = str(status.get("next_task") or "")
        if next_task == "consistency_retranslate":
            return TaskPlan(
                task_type="consistency_retranslate",
                implemented=True,
                reason="localized segment retranslate from fix plan (batched, checkpoint/resume)",
                command=_consistency_command(
                    script_rel=RUN_CONSISTENCY_RETRANSLATE_REL,
                    mode=mode,
                    python_executable=python_executable,
                    budgets=budgets,
                ),
                budget=budgets,
                mode=mode,
            )
        spec = _CONSISTENCY_TASKS.get(next_task)
        if spec:
            task_type, script_rel, reason = spec
            return TaskPlan(
                task_type=task_type,
                implemented=True,
                reason=reason,
                command=_consistency_command(
                    script_rel=script_rel,
                    mode=mode,
                    python_executable=python_executable,
                    budgets=budgets,
                ),
                budget=budgets,
                mode=mode,
            )
        return TaskPlan(
            task_type="consistency_audit",
            implemented=False,
            reason=f"not_implemented: unknown consistency next_task {next_task!r}",
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
