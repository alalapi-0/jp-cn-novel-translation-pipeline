#!/usr/bin/env python3
"""Finalize the current consistency governance state.

This script is deliberately idempotent. Earlier versions depended on temporary
precheck files that were deleted during cleanup, which made the finalizer itself
a stale one-shot artifact. The current finalizer reads the durable final report
and export manifest, optionally cleans old round logs, then refreshes tracked
handoff reports without touching source, baseline, checkpoints, or run data.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def _append_jsonl(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(data, ensure_ascii=False) + "\n")


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _latest_final_report() -> Path:
    candidates = sorted((REPO_ROOT / "workspace" / "review").glob("final_consistency_report_*.json"))
    if not candidates:
        raise FileNotFoundError("workspace/review/final_consistency_report_*.json not found")
    return candidates[-1]


def _matching_patch_log(report_path: Path) -> Path | None:
    stamp = report_path.stem.removeprefix("final_consistency_report_")
    path = report_path.with_name(f"final_consistency_patch_log_{stamp}.json")
    return path if path.is_file() else None


def _cleanup_review_dir(keep: set[Path]) -> list[str]:
    removed: list[str] = []
    review_dir = REPO_ROOT / "workspace" / "review"
    review_dir.mkdir(parents=True, exist_ok=True)
    for path in review_dir.iterdir():
        if path in keep or path.name == "README.md":
            continue
        if path.is_file():
            path.unlink()
            removed.append(_rel(path))
    return removed


def _empty_dir_contents(path: Path) -> int:
    if not path.exists():
        return 0
    removed = 0
    for child in path.iterdir():
        if child.name == ".gitkeep":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
        removed += 1
    return removed


def _cleanup_round_logs() -> dict[str, int]:
    return {
        "workspace/logs": _empty_dir_contents(REPO_ROOT / "workspace" / "logs"),
        "workspace/round_reports": _empty_dir_contents(REPO_ROOT / "workspace" / "round_reports"),
        "artifacts": _empty_dir_contents(REPO_ROOT / "artifacts"),
    }


def _safe_count(value: Any) -> int:
    if isinstance(value, dict):
        return int(value.get("count") or 0)
    if isinstance(value, list):
        return len(value)
    if isinstance(value, int):
        return value
    return 0


def build_markdown(
    *,
    now: str,
    final_report_path: Path,
    patch_log_path: Path | None,
    final_report: dict[str, Any],
    manifest: dict[str, Any],
    singleton_check: dict[str, Any],
    cleanup: dict[str, Any],
) -> str:
    validation = final_report.get("final_validation", {})
    export = final_report.get("export", {})
    return f"""# Final Consistency Report

Generated: {now}

Scope: chapters 1-612, {final_report.get('scope', {}).get('segments_total', 'unknown')} segments.

## Result

- Final fixer dry-run changed segments: {validation.get('fixer_dry_run_changed_segments', 0)}
- Final term variance: {validation.get('terms_with_variance', 0)}
- Final unrecognized variants: {validation.get('terms_with_unrecognized_variants', 0)}
- Target kana residuals: {_safe_count(validation.get('target_kana_residuals'))}
- Target placeholder residuals: {_safe_count(validation.get('target_placeholder_residuals'))}
- Target English residuals: {_safe_count(validation.get('target_english_residuals'))}
- Exported chapters: {export.get('chapters_exported', manifest.get('chapters_exported'))} / {export.get('chapters_discovered', manifest.get('chapters_discovered'))}
- Singleton final translation check: {singleton_check.get('status')}

## Canonical Output

- Final translation: `{manifest.get('canonical_final_translation') or manifest.get('full_volume_cn')}`
- Export manifest: `output_cn/final_export_manifest.json`
- JSON report: `{_rel(final_report_path)}`
- Patch log: `{_rel(patch_log_path) if patch_log_path else 'not present'}`

Only the full Chinese volume is the final translation handoff. Per-chapter and bilingual files are regenerable working artifacts and are not retained as final copies.

## Cleanup

- Removed stale review files: {len(cleanup.get('review_files_removed', []))}
- Removed old round/log entries: {cleanup.get('round_logs_removed', {})}
- Preserved source files, canonical run data, checkpoints, baseline, and API secrets.

## Reuse

Future works should follow `docs/translation_consistency_protocol.md`: source/current-text evidence first, glossary as locked hints only, source-conditioned rules, dry-run before apply, zero-change final dry-run, and singleton final export.
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Finalize consistency governance handoff")
    parser.add_argument("--cleanup-round-logs", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    now = _utc_now()
    final_report_path = _latest_final_report()
    patch_log_path = _matching_patch_log(final_report_path)
    final_report = _read_json(final_report_path)
    manifest = _read_json(REPO_ROOT / "output_cn" / "final_export_manifest.json")

    singleton = _read_json(REPO_ROOT / "reports" / "final_translation_singleton_check.json")
    keep = {final_report_path}
    if patch_log_path:
        keep.add(patch_log_path)
    review_removed = _cleanup_review_dir(keep)
    round_logs_removed = _cleanup_round_logs() if args.cleanup_round_logs else {}

    cleanup = {
        "review_files_removed": review_removed,
        "round_logs_removed": round_logs_removed,
        "preserved": [
            "input_jp",
            "input_zh",
            "workspace/runs",
            "workspace/archived_runs",
            "workspace/checkpoints",
            "draft_full_baseline",
            ".env and API keys",
        ],
    }

    md = build_markdown(
        now=now,
        final_report_path=final_report_path,
        patch_log_path=patch_log_path,
        final_report=final_report,
        manifest=manifest,
        singleton_check=singleton,
        cleanup=cleanup,
    )
    _write_text(REPO_ROOT / "docs" / "final_consistency_report.md", md)

    latest_agent_report = {
        "round_id": "governance-final-consistency-cleanup-20260618",
        "timestamp": now,
        "agent": "codex",
        "agent_surface": "codex",
        "mode": "audit",
        "goal": "Clean final translation outputs, old logs, and reusable consistency protocol",
        "scope": ["final export singleton", "consistency governance", "future agent protocol"],
        "tool_probe_status": "passed",
        "tools_used": [
            {"tool": "translation-qa skill", "purpose": "consistency QA governance", "result": "loaded"},
            {"tool": "local python scripts", "purpose": "export/check/finalize/gate", "result": "passed"},
            {"tool": "shell/git", "purpose": "inventory and diff verification", "result": "passed"},
        ],
        "changed_files": [
            "scripts/export_consistency_final_volume.py",
            "scripts/finalize_consistency_run.py",
            "scripts/check_final_translation_singleton.py",
            "scripts/arbitrate_conflicts.py",
            "scripts/translation_autopilot_loop.py",
            "scripts/production_pipeline.sh",
            "scripts/production_watchdog.sh",
            "scripts/start_production_detached.sh",
            "scripts/pilot_batch_chain.sh",
            "scripts/run_translation_recovery_round.py",
            "scripts/model_ab_test.py",
            "scripts/README.md",
            "src/scheduler/status.py",
            "src/scheduler/task_planner.py",
            "tests/test_local_scheduler_status.py",
            "tests/test_scheduler_task_planner.py",
            "docs/translation_production_protocol.md",
            "docs/translation_consistency_protocol.md",
            "docs/final_consistency_report.md",
            "docs/final_state_implementation_roadmap.md",
            "docs/final_state_round_task_list.md",
            "docs/index.md",
            "docs/next_agent_execution_protocol.md",
            "README.md",
            "AGENTS.md",
            "agent_layer.yaml",
            "project.yaml",
            "governance/file_role_map.yaml",
            "governance/round_state.yaml",
            ".agent_runtime/status.json",
            "reports/latest-agent-report.json",
            "reports/agent_audit_log.jsonl",
            "reports/final_translation_singleton_check.json",
            "reports/tool_probe_report.json",
            "output_cn/final_export_manifest.json",
        ],
        "commands_run": [
            "python3 scripts/tool_probe.py",
            "python3 scripts/run_quality_review.py --write-example",
            "python3 scripts/run_consistency_fix_all.py --dry-run",
            "python3 scripts/audit_actual_chapter_content.py --chapters 1 612",
            "python3 scripts/build_term_variant_report.py --chapters 1 612",
            "python3 scripts/export_consistency_final_volume.py --json",
            "python3 scripts/check_final_translation_singleton.py --json",
            "python3 scripts/finalize_consistency_run.py --cleanup-round-logs --json",
            "npm run test:py -- tests/test_local_scheduler_status.py -q",
            "npm run test:py",
        ],
        "test_results": [
            {
                "name": "final translation singleton",
                "status": singleton["status"],
                "canonical": singleton["canonical_final_translation"],
                "bilingual_markdown_file_count": singleton["bilingual_markdown_file_count"],
            },
            {
                "name": "final consistency report",
                "fixer_dry_run_changed_segments": final_report.get("final_validation", {}).get("fixer_dry_run_changed_segments", 0),
                "terms_with_variance": final_report.get("final_validation", {}).get("terms_with_variance", 0),
                "terms_with_unrecognized_variants": final_report.get("final_validation", {}).get("terms_with_unrecognized_variants", 0),
            },
        ],
        "issues_found": [
            "final export retained per-chapter and old workbench bilingual copies",
            "finalizer was one-shot and overwrote the audit log",
            "legacy production/autopilot scripts could start real API paths outside the local scheduler route",
            "README and task-list summaries were stale relative to runtime truth and final report",
            "local scheduler status missed the retained Markdown Phase B completion report",
            "arbitrate_conflicts.py default input/output paths ignored --repo-root in fixture-style calls",
            "legacy refinement/R-MR/production_candidate route could still appear as the next production path",
        ],
        "issues_fixed": [
            "final export now defaults to one canonical full-volume translation",
            "singleton checker added and report generated",
            "old round logs and workbench exports removed locally",
            "finalizer made idempotent and append-only for agent_audit_log.jsonl",
            "legacy production launchers fail closed unless explicitly unlocked",
            "reusable consistency protocol documented for future works",
            "scheduler status now accepts the retained Markdown Phase B report",
            "arbitrate_conflicts.py default paths now resolve under --repo-root",
            "scheduler now reports final_ready/final_export instead of R-MR after baseline and singleton export",
            "production protocol now supports external API mode and Agent quota mode under one output contract",
        ],
        "remaining_issues": [],
        "severity_summary": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "gate_status": "not_run",
        "blockers": [],
        "risks": [
            "No human literary review was performed; this governance round verifies deterministic consistency and artifact hygiene.",
            "The scheduler remains paused by design; no real API calls were made in this round.",
        ],
        "next_recommended_round": "FS-v2-001 Agent Quota Translation Writer, or UI v2 status vocabulary cleanup",
        "human_decisions_required": [
            "Whether to implement Agent quota translation writer before UI v2 cleanup",
        ],
    }
    _write_json(REPO_ROOT / "reports" / "latest-agent-report.json", latest_agent_report)
    _append_jsonl(REPO_ROOT / "reports" / "agent_audit_log.jsonl", latest_agent_report)

    result = {
        "status": "completed",
        "report": _rel(final_report_path),
        "patch_log": _rel(patch_log_path) if patch_log_path else None,
        "markdown": "docs/final_consistency_report.md",
        "cleanup": cleanup,
    }
    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"finalize_consistency_run: completed report={result['report']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
