#!/usr/bin/env python3
"""Generate translation recovery round report (md + json) from run artifacts."""

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

from local_env import apply_local_env  # noqa: E402
from translation.run_progress import safe_load_json  # noqa: E402

# Reuse gate metrics
_gate_spec = importlib.util.spec_from_file_location(
    "throughput_gate", REPO_ROOT / "scripts" / "throughput_gate.py"
)
assert _gate_spec and _gate_spec.loader
_gate = importlib.util.module_from_spec(_gate_spec)
_gate_spec.loader.exec_module(_gate)

ROUND_PLAN: dict[str, dict[str, Any]] = {
    "T-001": {"phase": "draft", "chapter_start": 171, "chapter_end": 190, "offset": 170, "limit": 20},
    "T-002": {"phase": "draft", "chapter_start": 191, "chapter_end": 210, "offset": 190, "limit": 20},
    "T-003": {"phase": "draft", "chapter_start": 211, "chapter_end": 230, "offset": 210, "limit": 20},
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _iter_stage_b_runs() -> list[Path]:
    runs_root = REPO_ROOT / "workspace" / "runs"
    if not runs_root.is_dir():
        return []
    return sorted(p.parent for p in runs_root.glob("run_*_draft_stage_b_50ch/run_metadata.json"))


def _chapter_quality(doc: dict[str, Any], ch_start: int, ch_end: int) -> dict[str, Any]:
    completed: list[int] = []
    failed: list[int] = []
    validation_failed = 0
    source_residual = 0
    format_issues = 0
    jp_re = re.compile(r"[\u3040-\u30ff\u4e00-\u9fff]")

    for ch in doc.get("chapters", []):
        ch_id = str(ch.get("chapter_id") or "")
        m = re.search(r"(\d+)", ch_id)
        if not m:
            continue
        num = int(m.group(1))
        if num < ch_start or num > ch_end:
            continue
        segs = ch.get("segments", [])
        if not segs:
            failed.append(num)
            continue
        all_draft = True
        ch_fail = False
        for s in segs:
            status = str(s.get("status") or "")
            if status in {"validation_failed", "failed"}:
                validation_failed += 1
                ch_fail = True
            draft = (s.get("draft_text") or "").strip()
            if not draft:
                all_draft = False
            elif jp_re.search(draft) and len(draft) < 200:
                source_residual += 1
            if draft and draft.count("\n\n\n") > 2:
                format_issues += 1
        if all_draft and not ch_fail:
            completed.append(num)
        else:
            failed.append(num)

    return {
        "completed_chapters": sorted(set(completed)),
        "failed_chapters": sorted(set(failed)),
        "validation_failed": validation_failed,
        "source_residual_segments": source_residual,
        "format_issues": format_issues,
    }


def _find_run_for_round(round_id: str, plan: dict[str, Any]) -> Path | None:
    offset = int(plan["offset"])
    best: Path | None = None
    for run_root in reversed(_iter_stage_b_runs()):
        meta = safe_load_json(run_root / "run_metadata.json") or {}
        if int(meta.get("chapter_offset") or -1) == offset:
            return run_root
        prog = safe_load_json(run_root / "run_progress.json") or {}
        if int(prog.get("chapter_offset") or -1) == offset:
            best = run_root
    return best


def build_report(round_id: str, *, run_id: str | None = None) -> dict[str, Any]:
    plan = ROUND_PLAN.get(round_id, {})
    phase = plan.get("phase", "draft")
    ch_start = int(plan.get("chapter_start", 0))
    ch_end = int(plan.get("chapter_end", 0))

    run_root = None
    if run_id:
        candidate = REPO_ROOT / "workspace" / "runs" / run_id
        if candidate.is_dir():
            run_root = candidate
    if run_root is None and plan:
        run_root = _find_run_for_round(round_id, plan)

    gate = _gate.evaluate_gate()
    draft_total, refined_total = _gate._count_chapter_metrics()

    meta: dict[str, Any] = {}
    progress: dict[str, Any] = {}
    checkpoint: dict[str, Any] = {}
    quality: dict[str, Any] = {
        "completed_chapters": [],
        "failed_chapters": [],
        "validation_failed": 0,
        "source_residual_segments": 0,
        "format_issues": 0,
    }

    if run_root:
        meta = safe_load_json(run_root / "run_metadata.json") or {}
        progress = safe_load_json(run_root / "run_progress.json") or {}
        cp_path = REPO_ROOT / "workspace" / "checkpoints" / f"{run_root.name}.json"
        checkpoint = safe_load_json(cp_path) or {}
        seg_doc = safe_load_json(run_root / "segments.json") or {}
        if ch_start and ch_end:
            quality = _chapter_quality(seg_doc, ch_start, ch_end)

    api_calls = int(checkpoint.get("api_calls") or meta.get("summary", {}).get("api_calls") or 0)
    spent = float(checkpoint.get("spent_usd") or meta.get("summary", {}).get("spent_usd") or 0)
    retries = int(checkpoint.get("retry_count") or 0)

    completed_in_round = len(quality["completed_chapters"])
    failed_in_round = len(quality["failed_chapters"])
    target = ch_end - ch_start + 1 if ch_start and ch_end else 0
    round_done = target > 0 and completed_in_round >= target

    continue_decision = "continue"
    blockers: list[str] = []
    if gate.get("decision") == "BLOCK":
        continue_decision = "blocked"
        blockers.extend(gate.get("blocks") or [])
    if gate.get("active_worker_count", 0) > 0:
        continue_decision = "blocked"
        blockers.append("active_worker_conflict")
    if not gate.get("has_api_key"):
        blockers.append("missing_api_key")

    report = {
        "generated_at": _utc_now(),
        "round_id": round_id,
        "phase": phase,
        "chapter_range": {"start": ch_start, "end": ch_end, "count": target},
        "run_id": run_root.name if run_root else (run_id or ""),
        "api_usage": {
            "provider": meta.get("provider_mode") or checkpoint.get("provider_mode") or "unknown",
            "model": meta.get("model_name") or checkpoint.get("model_name") or "",
            "calls": api_calls,
            "retries": retries,
            "estimated_cost_usd": round(spent, 6),
            "latency_ms_avg": None,
        },
        "output": {
            "local_draft_path": str(run_root / "draft") if run_root else "",
            "local_refined_path": "",
            "report_path": f"workspace/round_reports/{round_id}/",
            "exported": bool(run_root and (run_root / "segments.json").is_file()),
        },
        "quality_summary": {
            **quality,
            "terminology_issues": 0,
            "name_issues": 0,
            "skill_name_issues": 0,
            "entity_issues": 0,
        },
        "progress": {
            "run_status": progress.get("status"),
            "completed_segments": progress.get("completed_segments"),
            "total_segments": progress.get("total_segments"),
            "checkpoint_status": checkpoint.get("status"),
            "draft_completed_chapters_global": draft_total,
            "refined_exportable_chapters_global": refined_total,
        },
        "project_problems": {
            "pipeline": [],
            "checkpoint": [],
            "exporter": [],
            "validator": [],
            "prompt": [],
            "ui": [],
            "mcp_tools": [],
            "user_experience": [],
        },
        "fixes_applied": [],
        "unresolved": [],
        "tests": [],
        "git_commit": "",
        "continue_decision": continue_decision if round_done else ("in_progress" if run_root else continue_decision),
        "blockers": blockers,
        "next_round": f"T-{int(round_id.split('-')[1]) + 1:03d}" if round_id.startswith("T-") and round_done else round_id,
        "gate_decision": gate.get("decision"),
    }

    if not round_done and run_root and progress.get("status") == "in_progress":
        report["continue_decision"] = "in_progress"

    return report


def render_markdown(report: dict[str, Any]) -> str:
    ch = report["chapter_range"]
    q = report["quality_summary"]
    api = report["api_usage"]
    lines = [
        "# Translation Recovery Round Report",
        "",
        f"## 1. Round ID\n\n{report['round_id']}",
        f"## 2. Phase\n\n{report['phase']}",
        f"## 3. Chapter Range\n\n{ch['start']}–{ch['end']} ({ch['count']} 章)",
        "## 4. API Usage",
        f"- provider: {api['provider']}",
        f"- model: {api['model']}",
        f"- calls: {api['calls']}",
        f"- retries: {api['retries']}",
        f"- estimated cost: ${api['estimated_cost_usd']:.6f}",
        "- latency: 见 `workspace/diagnostics/throughput_metrics.json`",
        "## 5. Output",
        f"- local draft path: `{report['output']['local_draft_path']}`",
        f"- run_id: `{report['run_id']}`",
        f"- exported: {report['output']['exported']}",
        "## 6. Quality Summary",
        f"- completed chapters: {q['completed_chapters']}",
        f"- failed chapters: {q['failed_chapters']}",
        f"- validation_failed: {q['validation_failed']}",
        f"- source residual segments: {q['source_residual_segments']}",
        f"- format issues: {q['format_issues']}",
        "## 7. Project Problems Found",
        "（本轮 pipeline/checkpoint 问题见 `fixes_applied` 与 gate warnings）",
        "## 8. Fixes Applied This Round",
        *(f"- {x}" for x in report.get("fixes_applied") or ["见 commit 与路线图文档"]),
        "## 9. Tests",
        *(f"- {t}" for t in report.get("tests") or ["agent_gate", "throughput_gate"]),
        f"## 10. Git Commit\n\n{report.get('git_commit') or 'pending'}",
        f"## 11. Continue Decision\n\n{report['continue_decision']}",
        f"## 12. Next Round\n\n{report['next_round']}",
        "",
        f"_generated_at: {report['generated_at']}_",
    ]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate translation recovery round report")
    parser.add_argument("--round-id", required=True)
    parser.add_argument("--run-id", default="")
    parser.add_argument("--json-only", action="store_true")
    args = parser.parse_args()
    apply_local_env(REPO_ROOT)

    report = build_report(args.round_id, run_id=args.run_id.strip() or None)
    out_dir = REPO_ROOT / "workspace" / "round_reports" / args.round_id
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "translation_round_report.json"
    md_path = out_dir / "translation_round_report.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not args.json_only:
        md_path.write_text(render_markdown(report), encoding="utf-8")
        print(f"wrote {md_path}")
    print(f"wrote {json_path}")
    print(f"continue_decision={report['continue_decision']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
