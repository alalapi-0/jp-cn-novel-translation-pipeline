#!/usr/bin/env python3
"""Phase B completion gate (FS-037): verify consistency audit acceptance criteria."""

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

from consistency.draft_consistency_report import build_draft_consistency_report  # noqa: E402
from consistency.conflict_audit import SCHEMA_VERSION as GLOSSARY_SCHEMA_VERSION  # noqa: E402
from consistency.entity_index import SCHEMA_VERSION as ENTITY_SCHEMA_VERSION, entity_index_digest  # noqa: E402
from consistency.index_workspace_storage import (  # noqa: E402
    IndexWorkspaceStorageError,
    index_workspace_path,
)
from consistency.segment_index import index_shape_consistent  # noqa: E402
from consistency.retranslate import fix_plan_scope  # noqa: E402
from scheduler.status import collect_status  # noqa: E402
from translation.chapter_parser import count_source_chapters  # noqa: E402
from translation.run_progress import safe_load_json  # noqa: E402
from translation.source_versions import value_sha  # noqa: E402

INDEX_DIR = "workspace/indexes"
MANIFEST_DIR = "workspace/manifests"
AUDIT_DIR = "workspace/consistency_audit"


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


def _artifact(repo_root: Path, rel_dir: str, name: str) -> dict[str, Any] | None:
    path = (
        index_workspace_path(name, repo_root=repo_root)
        if rel_dir == INDEX_DIR
        else repo_root / rel_dir / name
    )
    return safe_load_json(path)


def _manifest_snapshot_covers(manifest: dict[str, Any], total: int) -> bool:
    """Check the manifest's own snapshot; current source freshness is separate."""
    stats = manifest.get("stats")
    chapters = manifest.get("chapters")
    if (type(total) is not int or total <= 0 or type(stats) is not dict
            or type(chapters) is not dict or len(chapters) != total
            or type(manifest.get("total_expected_chapters")) is not int
            or manifest["total_expected_chapters"] != total
            or type(stats.get("chapters_indexed")) is not int or stats["chapters_indexed"] != total
            or type(stats.get("source_chapters_found")) is not int or stats["source_chapters_found"] != total
            or type(stats.get("draft_chapters_found")) is not int or stats["draft_chapters_found"] != total
            or stats.get("full_coverage") is not True):
        return False
    for key in ("missing_source_chapters", "missing_draft_chapters", "extra_source_chapters",
                "duplicate_source_chapters", "gaps_in_source_sequence"):
        if stats.get(key) != []:
            return False
    numbers = []
    for chapter in chapters.values():
        if (type(chapter) is not dict or type(chapter.get("chapter_number")) is not int
                or not isinstance(chapter.get("source_path"), str) or not chapter["source_path"]
                or not isinstance(chapter.get("source_fingerprint"), str)
                or re.fullmatch(r"sha256:[0-9a-f]{64}", chapter["source_fingerprint"]) is None
                or chapter.get("draft_status") != "complete"):
            return False
        numbers.append(chapter["chapter_number"])
    return len(set(numbers)) == total and set(numbers) == set(range(1, total + 1))


def _report_matches(saved: Any, current: Any) -> bool:
    """Ignore only the report creation time when checking its saved snapshot."""
    if type(saved) is not dict or type(current) is not dict:
        return False
    return ({k: v for k, v in saved.items() if k != "generated_at"}
            == {k: v for k, v in current.items() if k != "generated_at"})


def _entity_snapshot_matches(entity: dict[str, Any], segment_index: dict[str, Any]) -> bool:
    """Compare the indexed file selection and metadata, without reading sources."""
    if not index_shape_consistent(segment_index):
        return False
    stats = entity.get("stats"); files = entity.get("files"); entries = entity.get("entities")
    conflicts = entity.get("conflicts"); unlisted = entity.get("unlisted_high_freq")
    if (type(entity.get("schema_version")) is not int or entity["schema_version"] != ENTITY_SCHEMA_VERSION
            or entity.get("chapter_filter") != [None, None]
            or type(stats) is not dict or type(files) is not dict or not files
            or type(entries) is not dict or type(conflicts) is not list or type(unlisted) is not list
            or type(entity.get("dependency_sha256")) is not str
            or re.fullmatch(r"[0-9a-f]{64}", entity["dependency_sha256"]) is None
            or list(files) != segment_index["file_order"]):
        return False
    counts = {"files_total": len(files), "entities_with_hits": len(entries),
              "conflict_count": len(conflicts), "unlisted_high_freq_count": len(unlisted)}
    if any(type(stats.get(key)) is not int or stats[key] != value for key, value in counts.items()):
        return False
    if (any(type(stats.get(key)) is not int or stats[key] < 0
            for key in ("files_scanned", "files_reused", "entities_indexed", "chapters_covered"))
            or stats["files_scanned"] + stats["files_reused"] != len(files)):
        return False
    return all(type(entry) is dict and type(entry.get("entities")) is dict
               and type(entry.get("unlisted")) is dict
               and entry.get("fingerprint") == segment_index["segment_files"][key].get("fingerprint")
               for key, entry in files.items())


def _glossary_snapshot_matches(glossary: dict[str, Any], entity: dict[str, Any]) -> bool:
    inputs = glossary.get("inputs"); stats = glossary.get("stats"); findings = glossary.get("findings")
    if (type(glossary.get("schema_version")) is not int or glossary["schema_version"] != GLOSSARY_SCHEMA_VERSION
            or type(inputs) is not dict or type(stats) is not dict or type(findings) is not list
            or any(type(row) is not dict or type(row.get("blocking")) is not bool for row in findings)):
        return False
    try:
        matches = inputs.get("entity_index_sha256") == entity_index_digest(entity)
    except (TypeError, ValueError, OverflowError):
        return False
    blocking = sum(row["blocking"] for row in findings)
    counts = {"findings_total": len(findings), "blocking_count": blocking,
              "non_blocking_count": len(findings) - blocking}
    return matches and all(type(stats.get(key)) is int and stats[key] == value
                           for key, value in counts.items())


def evaluate(repo_root: Path | None = None) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    total_chapters = count_source_chapters(root)
    status = collect_status(root)
    orphan = _load_orphan_eval()
    full_report = build_draft_consistency_report(root)

    manifest = _artifact(root, MANIFEST_DIR, "chapter_manifest.json") or {}
    segment_index = _artifact(root, INDEX_DIR, "segment_index.json") or {}
    entity_index = _artifact(root, INDEX_DIR, "entity_index.json") or {}
    glossary = _artifact(root, AUDIT_DIR, "glossary_conflict_audit.json") or {}
    fix_status = _artifact(root, AUDIT_DIR, "fix_plan_status.json") or {}
    fix_plan = _artifact(root, AUDIT_DIR, "local_fix_plan.json") or {}
    arbitration = _artifact(root, AUDIT_DIR, "arbitration_report.json") or {}
    saved_report = _artifact(root, AUDIT_DIR, "draft_consistency_report.json")

    manifest_stats = manifest.get("stats") if type(manifest.get("stats")) is dict else {}
    segment_stats = segment_index.get("stats") if type(segment_index.get("stats")) is dict else {}
    glossary_findings = glossary.get("findings")
    glossary_blocking = (sum(1 for f in glossary_findings if f.get("blocking") is True)
                         if type(glossary_findings) is list and all(type(f) is dict for f in glossary_findings)
                         else None)

    retranslate = fix_status.get("retranslate_tasks") if type(fix_status.get("retranslate_tasks")) is dict else {}
    term_fixes = fix_status.get("term_fixes") if type(fix_status.get("term_fixes")) is dict else {}
    deferred = fix_status.get("deferred") if type(fix_status.get("deferred")) is dict else {}
    try:
        fix_plan_matches = bool(fix_plan) and fix_status.get("plan_sha256") == value_sha(fix_plan)
    except (TypeError, ValueError, OverflowError):
        fix_plan_matches = False
    plan_scope = fix_plan_scope(fix_plan)
    retranslate_total = plan_scope["retranslate_segment_count"]
    task_counts_match = (type(retranslate_total) is int
                         and type(retranslate.get("total_segments")) is int
                         and retranslate["total_segments"] == retranslate_total
                         and type(retranslate.get("completed_segments")) is int
                         and retranslate["completed_segments"] == retranslate_total
                         and type(retranslate.get("remaining_segments")) is int
                         and retranslate["remaining_segments"] == 0)

    b6_pass = (
        fix_plan_matches
        and plan_scope["items_known"] and plan_scope["source_scope_known"]
        and plan_scope["counts_consistent"] and plan_scope["term_fix_count"] == 0
        and plan_scope["deferred_count"] == 0 and task_counts_match
        and fix_status.get("all_closed") is True
        and fix_status.get("retranslation_result_matches_plan") is True
        and fix_status.get("source_scope_known") is True
        and fix_status.get("plan_items_known") is True
        and fix_status.get("plan_counts_consistent") is True
        and fix_status.get("dry_run") is False
        and term_fixes.get("status") == "closed"
        and deferred.get("status") == "closed"
        and retranslate.get("status") == "closed"
    )

    arb_calls = arbitration.get("api_calls")
    arb_total = arbitration.get("provider_invocations_used")
    arb_cap = arbitration.get("max_api_calls")
    arb_within = (all(type(n) is int and n >= 0 for n in (arb_calls, arb_total, arb_cap))
                  and arb_calls <= arb_total <= arb_cap
                  and arbitration.get("budget_exhausted") is False)
    disclosure = full_report.get("progressive_disclosure")
    disclosure = disclosure if type(disclosure) is dict else {}
    manifest_report = disclosure.get("level_0_manifest")
    manifest_report = manifest_report if type(manifest_report) is dict else {}
    index_report = disclosure.get("segment_index")
    index_report = index_report if type(index_report) is dict else {}
    entity_matches = _entity_snapshot_matches(entity_index, segment_index)
    glossary_matches = entity_matches and _glossary_snapshot_matches(glossary, entity_index)
    required_levels = {"level_0_manifest", "level_1_entity_index", "level_2_glossary_conflicts",
                       "level_2_structure", "level_3_fix_plan", "level_4_arbitration",
                       "level_5_retranslate", "segment_index"}

    checks: dict[str, dict[str, Any]] = {
        "B1": {
            "description": "chapter manifest 内部覆盖所列编号章，来源实时状态另核",
            "pass": _manifest_snapshot_covers(manifest, total_chapters),
            "evidence": {
                "chapters_indexed": manifest_stats.get("chapters_indexed"),
                "full_coverage": manifest_stats.get("full_coverage"),
                "total_source_chapters": total_chapters,
                "scope": "indexed_snapshot_only",
                "source_freshness_status": manifest_report.get("source_freshness_status", "UNVERIFIED"),
            },
        },
        "B2": {
            "description": "segment index 已构建且漏段=0",
            "pass": index_shape_consistent(segment_index) and segment_stats.get("clean") is True,
            "evidence": {
                "segments_indexed": segment_stats.get("segments_indexed"),
                "missing_segments_count": segment_stats.get("missing_segments_count"),
                "source_freshness_status": index_report.get("source_freshness_status", "UNVERIFIED"),
            },
        },
        "B3": {
            "description": "entity index 与 segment index 的来源快照一致",
            "pass": entity_matches,
            "evidence": {"entities_indexed": (entity_index.get("stats") or {}).get("entities_indexed"),
                         "scope": "indexed_snapshot_only"},
        },
        "B4": {
            "description": "glossary 冲突统计绑定当前 entity index 快照",
            "pass": glossary_matches,
            "evidence": {"findings_total": len(glossary_findings) if type(glossary_findings) is list else None},
        },
        "B5": {
            "description": "blocking conflicts = 0",
            "pass": (glossary_matches and glossary_blocking == 0
                     and type(full_report.get("blocking_conflicts")) is int
                     and full_report["blocking_conflicts"] == 0),
            "evidence": {
                "glossary_blocking": glossary_blocking,
                "report_blocking": full_report.get("blocking_conflicts"),
            },
        },
        "B6": {
            "description": "必要局部修正 / 重译已全部完成",
            "pass": b6_pass,
            "evidence": fix_status or {"note": "fix_plan_status.json missing"},
        },
        "B7": {
            "description": "一致性报告完整",
            "pass": (full_report.get("status") == "PASS"
                     and full_report.get("recommendation") == "ready_for_final_export"
                     and manifest_report.get("source_freshness_status") == "VERIFIED"
                     and index_report.get("source_freshness_status") == "VERIFIED"
                     and _report_matches(saved_report, full_report)),
            "evidence": {
                "report_status": full_report.get("status"),
                "recommendation": full_report.get("recommendation"),
                "saved_snapshot_matches": _report_matches(saved_report, full_report),
                "manifest_source_freshness_status": manifest_report.get("source_freshness_status", "UNVERIFIED"),
                "source_freshness_status": index_report.get("source_freshness_status", "UNVERIFIED"),
            },
        },
        "B8": {
            "description": "progressive disclosure 合规；Level 4 调用数 ≤ 预算",
            "pass": arb_within and required_levels.issubset(disclosure),
            "evidence": {
                "arbitration_api_calls": arb_calls,
                "arbitration_provider_invocations_used": arb_total,
                "arbitration_max_api_calls": arb_cap,
                "budget_exhausted": arbitration.get("budget_exhausted"),
                "levels_present": list(disclosure),
            },
        },
    }

    failed_ids = [k for k, v in checks.items() if not v["pass"]]
    overall_pass = not failed_ids

    return {
        "generated_at": _utc_now(),
        "phase": "B",
        "round": "FS-037",
        "overall_pass": overall_pass,
        "failed_criteria": failed_ids,
        "total_source_chapters": total_chapters,
        "scheduler": {
            "current_phase": status["current_phase"],
            "next_task": status["next_task"],
            "draft_progress": status["draft_progress"],
        },
        "orphan_decision": orphan.get("decision"),
        "full_consistency_report": {
            "status": full_report.get("status"),
            "blocking_conflicts": full_report.get("blocking_conflicts"),
            "retranslate_remaining": (full_report.get("progressive_disclosure") or {})
            .get("level_5_retranslate", {})
            .get("remaining_segments"),
        },
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Phase B completion gate (FS-037)")
    parser.add_argument("--json", action="store_true")
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write desensitized report to docs/reports/phase_b_completion_report.md",
    )
    args = parser.parse_args()
    try:
        result = evaluate()
    except IndexWorkspaceStorageError as exc:
        print(f"phase_b_completion: {exc}", file=sys.stderr)
        return 78

    if args.write_report:
        report_dir = REPO_ROOT / "docs" / "reports"
        report_dir.mkdir(parents=True, exist_ok=True)
        md_path = report_dir / "phase_b_completion_report.md"
        lines = [
            "# Phase B Completion Report (FS-037)",
            "",
            f"- generated_at: {result['generated_at']}",
            f"- overall_pass: {result['overall_pass']}",
            f"- failed_criteria: {', '.join(result['failed_criteria']) or 'none'}",
            "",
            "## Criteria",
            "",
        ]
        for cid, check in result["checks"].items():
            lines.append(f"- {cid}: {'PASS' if check['pass'] else 'FAIL'} — {check['description']}")
        lines.append("")
        md_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
        json_path = report_dir / "phase_b_completion_report.json"
        json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        result["report_paths"] = {
            "markdown": str(md_path.relative_to(REPO_ROOT)),
            "json": str(json_path.relative_to(REPO_ROOT)),
        }

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(
            f"phase_b_completion: {'PASS' if result['overall_pass'] else 'FAIL'} "
            f"failed={','.join(result['failed_criteria']) or '-'}"
        )

    return 0 if result["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
