#!/usr/bin/env python3
"""Phase B completion gate (FS-037): verify consistency audit acceptance criteria."""

from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from consistency.draft_consistency_report import build_draft_consistency_report  # noqa: E402
from scheduler.status import collect_status  # noqa: E402
from translation.chapter_parser import count_source_chapters  # noqa: E402
from translation.run_progress import safe_load_json  # noqa: E402

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
    return safe_load_json(repo_root / rel_dir / name)


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
    arbitration = _artifact(root, AUDIT_DIR, "arbitration_report.json") or {}

    manifest_stats = manifest.get("stats") or {}
    segment_stats = segment_index.get("stats") or {}
    glossary_blocking = sum(1 for f in glossary.get("findings") or [] if f.get("blocking"))

    retranslate = fix_status.get("retranslate_tasks") or {}
    term_fixes = fix_status.get("term_fixes") or {}
    deferred = fix_status.get("deferred") or {}

    b6_pass = (
        term_fixes.get("status") == "closed"
        and deferred.get("status") == "closed"
        and (
            retranslate.get("status") == "closed"
            or (
                retranslate.get("status") == "partial"
                and retranslate.get("pilot_validated")
                and glossary_blocking == 0
            )
        )
    )

    arb_calls = int(arbitration.get("api_calls") or 0)
    arb_cap = int(arbitration.get("max_api_calls") or 0)
    arb_within = not arbitration or (arb_cap == 0 or arb_calls <= arb_cap)

    checks: dict[str, dict[str, Any]] = {
        "B1": {
            "description": "chapter manifest 已构建且覆盖全书编号章",
            "pass": bool(manifest)
            and (
                bool((manifest.get("stats") or {}).get("full_coverage"))
                or int(manifest_stats.get("chapters_indexed") or 0) >= total_chapters
            ),
            "evidence": {
                "chapters_indexed": manifest_stats.get("chapters_indexed"),
                "full_coverage": manifest_stats.get("full_coverage"),
                "total_source_chapters": total_chapters,
            },
        },
        "B2": {
            "description": "segment index 已构建且漏段=0",
            "pass": bool(segment_index)
            and int(segment_stats.get("missing_segments_count") or 0) == 0,
            "evidence": {
                "segments_indexed": segment_stats.get("segments_indexed"),
                "missing_segments_count": segment_stats.get("missing_segments_count"),
            },
        },
        "B3": {
            "description": "entity index 已构建",
            "pass": bool(entity_index),
            "evidence": {"entities_indexed": (entity_index.get("stats") or {}).get("entities_indexed")},
        },
        "B4": {
            "description": "glossary 冲突已统计",
            "pass": bool(glossary),
            "evidence": {"findings_total": len(glossary.get("findings") or [])},
        },
        "B5": {
            "description": "blocking conflicts = 0",
            "pass": glossary_blocking == 0 and int(full_report.get("blocking_conflicts") or 0) == 0,
            "evidence": {
                "glossary_blocking": glossary_blocking,
                "report_blocking": full_report.get("blocking_conflicts"),
            },
        },
        "B6": {
            "description": "必要局部修正 / 重译已完成（fix plan 状态 closed 或 pilot 验证）",
            "pass": b6_pass,
            "evidence": fix_status or {"note": "fix_plan_status.json missing"},
        },
        "B7": {
            "description": "一致性报告完整",
            "pass": (root / AUDIT_DIR / "draft_consistency_report.json").is_file(),
            "evidence": {
                "report_status": full_report.get("status"),
                "recommendation": full_report.get("recommendation"),
            },
        },
        "B8": {
            "description": "progressive disclosure 合规；Level 4 调用数 ≤ 预算",
            "pass": arb_within and bool(full_report.get("progressive_disclosure")),
            "evidence": {
                "arbitration_api_calls": arb_calls,
                "arbitration_max_api_calls": arb_cap,
                "budget_exhausted": arbitration.get("budget_exhausted"),
                "levels_present": list((full_report.get("progressive_disclosure") or {}).keys()),
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
    result = evaluate()

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
