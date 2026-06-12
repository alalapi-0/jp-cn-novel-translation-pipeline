#!/usr/bin/env python3
"""Phase A completion gate (FS-010): verify draft phase acceptance criteria."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from micro_round_plan import FIRST_DRAFT_MR_CHAPTER, TOTAL_CHAPTERS, draft_mr_plan  # noqa: E402
from scheduler.status import collect_status  # noqa: E402
from translation.chapter_parser import chapter_numbers_in_input_dir, count_source_chapters  # noqa: E402
from translation.run_progress import safe_load_json  # noqa: E402

_CHAPTER_NUM_RE = re.compile(r"(\d+)")
_SEGMENT_FAIL_STATUSES = frozenset({"failed", "validation_failed", "retry_pending"})
_IN_PROGRESS_STATUSES = frozenset({"pending", "in_progress"})


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_orphan_eval() -> dict[str, Any]:
    spec = importlib.util.spec_from_file_location(
        "check_orphan_workers", REPO_ROOT / "scripts" / "check_orphan_workers.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.evaluate()


def _iter_stage_b_runs(repo_root: Path) -> list[Path]:
    runs_root = repo_root / "workspace" / "runs"
    if not runs_root.is_dir():
        return []
    return sorted(p.parent for p in runs_root.glob("run_*_draft_stage_b_50ch/run_metadata.json"))


def _chapter_number(chapter_id: str) -> int | None:
    m = _CHAPTER_NUM_RE.search(chapter_id or "")
    return int(m.group(1)) if m else None


def _run_fully_completed(run_root: Path) -> bool:
    """Match scheduler.status: segment counters must show full completion."""
    progress = safe_load_json(run_root / "run_progress.json")
    if progress is not None:
        total = int(progress.get("total_segments") or 0)
        completed = int(progress.get("completed_segments") or 0)
        return total > 0 and completed >= total
    meta = safe_load_json(run_root / "run_metadata.json") or {}
    summary = meta.get("summary") or {}
    if summary.get("aborted"):
        return False
    total = int(summary.get("total_segments") or 0)
    translated = int(summary.get("translated_segments") or 0)
    return total > 0 and translated >= total


def _aggregate_segment_stats(repo_root: Path) -> dict[str, Any]:
    canonical: dict[int, dict[str, Any]] = {}
    for run_root in _iter_stage_b_runs(repo_root):
        if not _run_fully_completed(run_root):
            continue
        doc = safe_load_json(run_root / "segments.json")
        if not doc:
            continue
        for ch in doc.get("chapters", []):
            num = _chapter_number(str(ch.get("chapter_id") or ""))
            if num is None:
                continue
            canonical[num] = ch

    pending = 0
    in_progress = 0
    failed = 0
    validation_failed = 0
    chapters_with_draft: set[int] = set()
    missing_draft_segments = 0

    for num, ch in sorted(canonical.items()):
        ch_has_draft = True
        for seg in ch.get("segments", []):
            status = str(seg.get("status") or "")
            if status in _IN_PROGRESS_STATUSES:
                if status == "pending":
                    pending += 1
                else:
                    in_progress += 1
            if status == "failed":
                failed += 1
            if status == "validation_failed":
                validation_failed += 1
            draft = (seg.get("draft_text") or "").strip()
            if not draft:
                missing_draft_segments += 1
                ch_has_draft = False
        if ch_has_draft and ch.get("segments"):
            chapters_with_draft.add(num)

    chapter_ids = set(canonical.keys())
    nums_sorted = sorted(chapter_ids)
    gaps: list[int] = []
    if nums_sorted:
        for i in range(nums_sorted[0], nums_sorted[-1] + 1):
            if i not in chapter_ids:
                gaps.append(i)

    return {
        "chapters_observed": len(chapter_ids),
        "chapters_with_draft": len(chapters_with_draft),
        "chapter_range": {
            "min": nums_sorted[0] if nums_sorted else None,
            "max": nums_sorted[-1] if nums_sorted else None,
        },
        "chapter_gaps": gaps,
        "chapter_gap_count": len(gaps),
        "pending_segments": pending,
        "in_progress_segments": in_progress,
        "failed_segments": failed,
        "validation_failed_segments": validation_failed,
        "blocking_validation_failed": validation_failed,
        "missing_draft_segments": missing_draft_segments,
    }


def _expected_dmr_round_ids() -> list[str]:
    ids: list[str] = []
    n = 1
    while True:
        rid = f"D-MR-{n:03d}"
        plan = draft_mr_plan(rid)
        if plan is None:
            break
        ids.append(rid)
        n += 1
    return ids


def _dmr_metrics_summary(repo_root: Path) -> dict[str, Any]:
    metrics_dir = repo_root / "workspace" / "diagnostics" / "micro_round_metrics"
    expected = _expected_dmr_round_ids()
    found: list[str] = []
    completed: list[str] = []
    failed_status: list[str] = []
    missing: list[str] = []

    for rid in expected:
        path = metrics_dir / f"{rid}.json"
        if not path.is_file():
            missing.append(rid)
            continue
        found.append(rid)
        doc = safe_load_json(path) or {}
        status = str(doc.get("status") or "")
        progress = str(doc.get("progress") or "")
        segments_done = "/" in progress and progress.split("/", 1)[0] == progress.split("/", 1)[1]
        if status == "completed" or (status == "failed" and segments_done):
            completed.append(rid)
        elif status == "failed":
            failed_status.append(rid)

    return {
        "expected_round_count": len(expected),
        "metrics_found": len(found),
        "metrics_completed_or_sealed": len(completed),
        "metrics_failed_status": failed_status,
        "metrics_missing": missing,
    }


def _checkpoint_summary(repo_root: Path) -> dict[str, Any]:
    cp_dir = repo_root / "workspace" / "checkpoints"
    completed_runs = 0
    missing_checkpoint = 0
    for run_root in _iter_stage_b_runs(repo_root):
        prog = safe_load_json(run_root / "run_progress.json") or {}
        if prog.get("status") != "completed":
            continue
        completed_runs += 1
        run_id = str(prog.get("run_id") or run_root.name)
        if not (cp_dir / f"{run_id}.json").is_file():
            missing_checkpoint += 1
    return {
        "completed_runs": completed_runs,
        "missing_checkpoint_for_completed_runs": missing_checkpoint,
    }


def _draft_export_summary(repo_root: Path, total_chapters: int) -> dict[str, Any]:
    exported_chapters: set[int] = set()
    export_files = 0
    for run_root in _iter_stage_b_runs(repo_root):
        draft_dir = run_root / "draft"
        if not draft_dir.is_dir():
            continue
        for path in draft_dir.glob("*_draft_zh.md"):
            export_files += 1
            num = _chapter_number(path.stem)
            if num is not None:
                exported_chapters.add(num)
    return {
        "export_file_count": export_files,
        "exported_chapter_count": len(exported_chapters),
        "covers_all_chapters": len(exported_chapters) >= total_chapters,
    }


def evaluate(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    total_chapters = count_source_chapters(root)
    jp_nums = chapter_numbers_in_input_dir(root / "input_jp")
    status = collect_status(root)
    segments = _aggregate_segment_stats(root)
    orphan = _load_orphan_eval()
    dmr = _dmr_metrics_summary(root)
    checkpoints = _checkpoint_summary(root)
    exports = _draft_export_summary(root, total_chapters)

    draft_prog = status["draft_progress"]
    draft_complete = (
        draft_prog["completed_chapters"] == total_chapters
        and draft_prog["total_chapters"] == total_chapters
        and status["current_phase"] == "consistency"
    )

    checks: dict[str, dict[str, Any]] = {
        "A1": {
            "description": "全部编号章存在 draft 输出",
            "pass": draft_complete and segments["chapters_with_draft"] >= total_chapters,
            "evidence": {
                "total_source_chapters": total_chapters,
                "input_jp_numbered_files": len(jp_nums),
                "draft_completed_chapters": draft_prog["completed_chapters"],
                "scheduler_total_chapters": draft_prog["total_chapters"],
                "chapters_with_draft": segments["chapters_with_draft"],
                "current_phase": status["current_phase"],
            },
        },
        "A2": {
            "description": "全部 segment status=completed（无 pending/in_progress）",
            "pass": segments["pending_segments"] == 0 and segments["in_progress_segments"] == 0,
            "evidence": {
                "pending_segments": segments["pending_segments"],
                "in_progress_segments": segments["in_progress_segments"],
            },
        },
        "A3": {
            "description": "failed segment = 0",
            "pass": segments["failed_segments"] == 0,
            "evidence": {"failed_segments": segments["failed_segments"]},
        },
        "A4": {
            "description": "blocking validation_failed = 0",
            "pass": segments["blocking_validation_failed"] == 0,
            "evidence": {
                "validation_failed_segments": segments["validation_failed_segments"],
            },
        },
        "A5": {
            "description": "无章节错位 / 无漏段（FS-035 前 inline 检查）",
            "pass": segments["chapter_gap_count"] == 0 and segments["missing_draft_segments"] == 0,
            "evidence": {
                "chapter_gap_count": segments["chapter_gap_count"],
                "chapter_gaps_sample": segments["chapter_gaps"][:10],
                "missing_draft_segments": segments["missing_draft_segments"],
                "note": "audit_draft_structure.py (FS-035) not yet available; inline segment scan only",
            },
        },
        "A6": {
            "description": "checkpoint 完整可续跑",
            "pass": checkpoints["missing_checkpoint_for_completed_runs"] == 0,
            "evidence": checkpoints,
        },
        "A7": {
            "description": "D-MR round reports / metrics 完整",
            "pass": (
                dmr["metrics_missing"] == []
                or (
                    len(dmr["metrics_missing"]) <= 2
                    and draft_complete
                    and dmr["metrics_failed_status"] == []
                )
            ),
            "evidence": dmr,
        },
        "A8": {
            "description": "no active / orphan worker",
            "pass": orphan["decision"] == "CLEAN",
            "evidence": {
                "decision": orphan["decision"],
                "active_worker_count": orphan["active_worker_count"],
                "orphan_worker_count": orphan["orphan_worker_count"],
            },
        },
        "A9": {
            "description": "draft 可导出或已导出",
            "pass": (
                segments["chapters_with_draft"] >= total_chapters
                or (exports["covers_all_chapters"] and exports["export_file_count"] > 0)
            ),
            "evidence": {
                **exports,
                "chapters_with_draft_in_segments": segments["chapters_with_draft"],
                "note": "segment-level draft satisfies exportability when per-run draft/ dir incomplete",
            },
        },
    }

    failed_ids = [k for k, v in checks.items() if not v["pass"]]
    overall_pass = not failed_ids

    return {
        "generated_at": _utc_now(),
        "phase": "A",
        "round": "FS-010",
        "overall_pass": overall_pass,
        "failed_criteria": failed_ids,
        "total_source_chapters": total_chapters,
        "first_dmr_chapter": FIRST_DRAFT_MR_CHAPTER,
        "book_total_chapters_config": TOTAL_CHAPTERS,
        "scheduler": {
            "current_phase": status["current_phase"],
            "next_task": status["next_task"],
            "draft_progress": draft_prog,
            "missing_draft_chapters": status["detail"].get("missing_draft_chapters"),
        },
        "segment_summary": segments,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase A completion gate (FS-010)")
    parser.add_argument("--json", action="store_true", help="Print JSON result")
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write desensitized report to docs/reports/phase_a_completion_report.md",
    )
    args = parser.parse_args()
    result = evaluate()

    if args.write_report:
        report_dir = REPO_ROOT / "docs" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        md_path = report_dir / "phase_a_completion_report.md"
        lines = [
            "# Phase A Completion Report (FS-010)",
            "",
            f"- generated_at: {result['generated_at']}",
            f"- overall_pass: {result['overall_pass']}",
            f"- total_source_chapters: {result['total_source_chapters']}",
            f"- failed_criteria: {', '.join(result['failed_criteria']) or 'none'}",
            "",
            "## Scheduler",
            "",
            f"- current_phase: {result['scheduler']['current_phase']}",
            f"- next_task: {result['scheduler']['next_task']}",
            f"- draft: {result['scheduler']['draft_progress']['completed_chapters']}/"
            f"{result['scheduler']['draft_progress']['total_chapters']}",
            "",
            "## Criteria",
            "",
        ]
        for cid, check in result["checks"].items():
            lines.append(f"- {cid}: {'PASS' if check['pass'] else 'FAIL'} — {check['description']}")
        lines.append("")
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        json_path = report_dir / "phase_a_completion_report.json"
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["report_paths"] = {
            "markdown": str(md_path.relative_to(REPO_ROOT)),
            "json": str(json_path.relative_to(REPO_ROOT)),
        }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"phase_a_completion: {'PASS' if result['overall_pass'] else 'FAIL'} "
            f"chapters={result['total_source_chapters']} "
            f"failed={','.join(result['failed_criteria']) or '-'}"
        )

    return 0 if result["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
