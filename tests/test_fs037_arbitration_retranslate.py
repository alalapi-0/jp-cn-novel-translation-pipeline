"""Tests for FS-037: arbitration, retranslate, Phase B report."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from consistency.arbitration import (  # noqa: E402
    build_arbitration_messages,
    parse_arbitration_response,
    run_arbitration,
    select_arbitration_candidates,
)
from consistency.draft_consistency_report import build_draft_consistency_report  # noqa: E402
from consistency.local_fix_plan import build_local_fix_plan  # noqa: E402
from consistency.retranslate import (  # noqa: E402
    build_fix_plan_status,
    collect_retranslate_segment_ids,
    run_consistency_retranslate,
)
from glossary import GlossaryEntry  # noqa: E402
from providers.cost_guard import CostGuard, CostGuardConfig  # noqa: E402
from providers.fake_provider import FakeProvider  # noqa: E402
from scheduler.task_planner import plan_next_task  # noqa: E402


def _write_segments(path: Path, chapter_id: str, rows: list[tuple[str, str, str]]) -> None:
    doc = {
        "language_direction": "JP_TO_CN",
        "pipeline_stage": "draft_stage_b",
        "chapters": [
            {
                "chapter_id": chapter_id,
                "chapter_label": chapter_id,
                "source_path": f"input_jp/{chapter_id}.md",
                "segments": [
                    {
                        "segment_id": sid,
                        "source_text": src,
                        "draft_text": dst,
                        "status": "machine_translated",
                    }
                    for sid, src, dst in rows
                ],
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


def _write_run_meta(run_root: Path) -> None:
    run_root.mkdir(parents=True, exist_ok=True)
    (run_root / "run_metadata.json").write_text(
        json.dumps({"run_id": run_root.name, "phase": "draft"}),
        encoding="utf-8",
    )
    (run_root / "run_progress.json").write_text(
        json.dumps({"status": "completed", "total_segments": 1, "completed_segments": 1}),
        encoding="utf-8",
    )


@pytest.fixture()
def fixture_repo(tmp_path: Path) -> Path:
    run_root = tmp_path / "workspace" / "runs" / "run_test_draft_stage_b_50ch"
    _write_run_meta(run_root)
    _write_segments(
        run_root / "segments.json",
        "ch-001",
        [
            ("ch-001-seg-001", "サンプル", "示例残留カナ"),
            ("ch-001-seg-002", "テスト", "测试文"),
        ],
    )
    audit_dir = tmp_path / "workspace" / "consistency_audit"
    audit_dir.mkdir(parents=True)
    glossary_audit = {
        "findings": [
            {
                "kind": "shared_target",
                "blocking": False,
                "target_term": "阿尔法团",
                "source_terms": ["アルファ団", "α団"],
                "segment_ids": ["ch-001-seg-001"],
                "chapters": ["ch-001"],
            }
        ]
    }
    structure_audit = {
        "findings": [
            {
                "kind": "source_residual",
                "blocking": False,
                "segment_ids": ["ch-001-seg-001"],
                "chapters": ["ch-001"],
                "hint": "japanese_kana_present",
            }
        ]
    }
    (audit_dir / "glossary_conflict_audit.json").write_text(
        json.dumps(glossary_audit, ensure_ascii=False),
        encoding="utf-8",
    )
    (audit_dir / "draft_structure_audit.json").write_text(
        json.dumps(structure_audit, ensure_ascii=False),
        encoding="utf-8",
    )
    plan = build_local_fix_plan(glossary_audit, structure_audit)
    (audit_dir / "local_fix_plan.json").write_text(
        json.dumps(plan, ensure_ascii=False),
        encoding="utf-8",
    )
    index_dir = tmp_path / "workspace" / "indexes"
    index_dir.mkdir(parents=True)
    manifest_dir = tmp_path / "workspace" / "manifests"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "chapter_manifest.json").write_text(
        json.dumps({"stats": {"chapters_indexed": 1, "full_coverage": True}}),
        encoding="utf-8",
    )
    (index_dir / "segment_index.json").write_text(
        json.dumps({"stats": {"segments_indexed": 2, "missing_segments_count": 0}}),
        encoding="utf-8",
    )
    (index_dir / "entity_index.json").write_text(json.dumps({"stats": {"entities_indexed": 0}}), encoding="utf-8")
    return tmp_path


def test_select_arbitration_candidates_filters_kinds() -> None:
    audit = {
        "findings": [
            {"kind": "unlisted_high_freq", "blocking": False},
            {"kind": "shared_target", "blocking": False, "target_term": "X", "segment_ids": []},
            {"kind": "divergent_translation", "blocking": False, "source_term": "Y", "segment_ids": []},
        ]
    }
    candidates = select_arbitration_candidates(audit)
    assert {c["kind"] for c in candidates} == {"shared_target", "divergent_translation"}


def test_parse_arbitration_response_accepts_json_block() -> None:
    raw = 'Here is the answer:\n{"canonical_target":"示例王国","rationale":"glossary","confidence":"high"}'
    parsed = parse_arbitration_response(raw)
    assert parsed["parse_status"] == "ok"
    assert parsed["canonical_target"] == "示例王国"


def test_arbitration_dry_run_respects_cap() -> None:
    audit = {
        "findings": [
            {"kind": "shared_target", "blocking": False, "target_term": f"T{i}", "segment_ids": []}
            for i in range(5)
        ]
    }
    candidates = select_arbitration_candidates(audit)
    guard = CostGuard(CostGuardConfig(max_test_cost_usd=1.0))
    provider = FakeProvider(cost_guard=guard)
    report = run_arbitration(candidates, provider=provider, max_api_calls=2, dry_run=True)
    assert report["arbitrated_count"] == 2
    assert report["budget_exhausted"] is True


def test_retranslate_dry_run_checkpoint(fixture_repo: Path) -> None:
    plan = json.loads((fixture_repo / "workspace/consistency_audit/local_fix_plan.json").read_text())
    guard = CostGuard(CostGuardConfig(max_test_cost_usd=1.0))
    provider = FakeProvider(cost_guard=guard)
    result = run_consistency_retranslate(
        plan,
        fixture_repo,
        provider=provider,
        max_api_calls=5,
        limit=1,
        dry_run=True,
    )
    assert result["batch_completed"] == 1
    assert result["status"] in ("partial", "closed")
    cp = json.loads(
        (fixture_repo / "workspace/consistency_audit/retranslate_progress.json").read_text()
    )
    assert "ch-001-seg-001" in cp["completed_segment_ids"]


def test_retranslate_real_apply_updates_draft(fixture_repo: Path) -> None:
    plan = json.loads((fixture_repo / "workspace/consistency_audit/local_fix_plan.json").read_text())
    guard = CostGuard(CostGuardConfig(max_test_cost_usd=1.0))
    provider = FakeProvider(cost_guard=guard)
    run_consistency_retranslate(
        plan,
        fixture_repo,
        provider=provider,
        max_api_calls=2,
        limit=2,
        dry_run=False,
    )
    seg_path = fixture_repo / "workspace/runs/run_test_draft_stage_b_50ch/segments.json"
    doc = json.loads(seg_path.read_text())
    draft = doc["chapters"][0]["segments"][0]["draft_text"]
    assert draft.startswith("[fake]")


def test_fix_plan_status_partial_after_pilot() -> None:
    plan = {"stats": {"term_fix_count": 0, "deferred_count": 1, "retranslate_segment_count": 10}}
    status = build_fix_plan_status(plan, {"completed_segments": 2, "remaining_segments": 8, "status": "partial"})
    assert status["retranslate_tasks"]["status"] == "partial"
    assert status["retranslate_tasks"]["pilot_validated"] is True
    assert status["deferred"]["status"] == "closed"


def test_consistency_retranslate_planner_implemented() -> None:
    status = {
        "current_phase": "consistency",
        "next_task": "consistency_retranslate",
        "paused": False,
        "detail": {},
    }
    plan = plan_next_task(status, mode="real", budgets={"max_api_calls": 5, "max_segments": 20})
    assert plan.implemented is True
    assert plan.task_type == "consistency_retranslate"
    assert "--real-api" in plan.command
    assert "--max-api-calls" in plan.command


def test_arbitrate_planner_dry_run() -> None:
    status = {
        "current_phase": "consistency",
        "next_task": "consistency_arbitrate",
        "paused": False,
        "detail": {},
    }
    plan = plan_next_task(status, mode="dry_run", budgets={"max_api_calls": 3})
    assert plan.implemented is True
    assert "--dry-run" in plan.command


def test_build_draft_consistency_report_fixture(fixture_repo: Path) -> None:
    guard = CostGuard(CostGuardConfig(max_test_cost_usd=1.0))
    provider = FakeProvider(cost_guard=guard)
    audit = json.loads((fixture_repo / "workspace/consistency_audit/glossary_conflict_audit.json").read_text())
    arb = run_arbitration(select_arbitration_candidates(audit), provider=provider, dry_run=True)
    out = fixture_repo / "workspace/consistency_audit/arbitration_report.json"
    out.write_text(json.dumps(arb, ensure_ascii=False), encoding="utf-8")
    plan = json.loads((fixture_repo / "workspace/consistency_audit/local_fix_plan.json").read_text())
    rt = run_consistency_retranslate(plan, fixture_repo, provider=provider, limit=1, dry_run=True)
    status = build_fix_plan_status(plan, rt)
    (fixture_repo / "workspace/consistency_audit/fix_plan_status.json").write_text(
        json.dumps(status, ensure_ascii=False),
        encoding="utf-8",
    )
    report = build_draft_consistency_report(fixture_repo)
    assert report["status"] == "PASS"
    assert report["blocking_conflicts"] == 0
    assert report["recommendation"] == "ready_for_final_export"


def test_arbitrate_conflicts_cli(tmp_path: Path, monkeypatch) -> None:
    audit_dir = tmp_path / "workspace" / "consistency_audit"
    audit_dir.mkdir(parents=True)
    (audit_dir / "glossary_conflict_audit.json").write_text(
        json.dumps({"findings": []}),
        encoding="utf-8",
    )
    spec = importlib.util.spec_from_file_location(
        "arbitrate_conflicts", REPO_ROOT / "scripts" / "arbitrate_conflicts.py"
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rc = mod.main(["--repo-root", str(tmp_path), "--dry-run", "--json"])
    assert rc == 0
    assert (audit_dir / "arbitration_report.json").is_file()
