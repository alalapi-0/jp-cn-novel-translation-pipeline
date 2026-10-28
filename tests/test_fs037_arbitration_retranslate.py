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
    assert report["arbitrated_count"] == report["api_calls"] == 0
    assert report["simulated_count"] == 2 and report["preview_truncated"] is True


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
    assert result["batch_completed"] == result["api_calls"] == 0
    assert result["simulated_segments"] == 1 and result["status"] == "simulated"
    cp = json.loads(
        Path(result["checkpoint_path"]).read_text()
    )
    assert cp["completed_segment_ids"] == []
    assert "ch-001-seg-001" in cp["simulated_segment_ids"]
    assert not (fixture_repo / "workspace/consistency_audit/retranslate_progress.json").exists()


def test_known_fake_provider_cannot_apply_real_draft(fixture_repo: Path) -> None:
    plan = json.loads((fixture_repo / "workspace/consistency_audit/local_fix_plan.json").read_text())
    guard = CostGuard(CostGuardConfig(max_test_cost_usd=1.0))
    provider = FakeProvider(cost_guard=guard)
    result = run_consistency_retranslate(
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
    assert draft == '示例残留カナ'
    assert result['dry_run'] is True and result['completed_segments'] == 0


def test_fix_plan_status_partial_after_pilot() -> None:
    plan = {"stats": {"term_fix_count": 0, "deferred_count": 1, "retranslate_segment_count": 10}}
    status = build_fix_plan_status(plan, {"completed_segments": 2, "remaining_segments": 8, "status": "partial"})
    assert status["retranslate_tasks"]["status"] == "partial"
    assert status["retranslate_tasks"]["partial_execution_reported"] is True
    assert status["retranslate_tasks"]["pilot_validated"] is False
    assert status["retranslate_tasks"]["pilot_validation_status"] == "UNVERIFIED"
    assert status["deferred"]["status"] == "pending" and status["all_closed"] is False


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
    assert report["status"] == "SIMULATED"
    assert report["blocking_conflicts"] == 0
    assert report["recommendation"] != "ready_for_final_export"


@pytest.mark.parametrize('index_version,audit_version',[(3,3),(4,3)])
def test_stale_index_or_structure_audit_cannot_indicate_export_ready(fixture_repo: Path,index_version: int,audit_version: int) -> None:
    from consistency.segment_index import build_segment_index
    index=fixture_repo/'workspace/indexes/segment_index.json'
    value=build_segment_index(fixture_repo);value['schema_version']=index_version
    index.write_text(json.dumps(value),encoding='utf-8')
    audit=fixture_repo/'workspace/consistency_audit/draft_structure_audit.json'
    audit.write_text(json.dumps({'inputs':{'segment_index_schema_version':audit_version},'findings':[]}),encoding='utf-8')
    plan=fixture_repo/'workspace/consistency_audit/local_fix_plan.json'
    plan.write_text(json.dumps({'stats':{'term_fix_count':0,'retranslate_segment_count':0,'deferred_count':0}}),encoding='utf-8')
    report=build_draft_consistency_report(fixture_repo)
    assert report['status']!='PASS'
    assert report['recommendation']!='ready_for_final_export'


def test_current_index_and_audit_are_recognized_in_report(fixture_repo: Path) -> None:
    from consistency.draft_structure_audit import audit_draft_structure
    from consistency.segment_index import build_segment_index
    index=fixture_repo/'workspace/indexes/segment_index.json'
    value=build_segment_index(fixture_repo)
    index.write_text(json.dumps(value),encoding='utf-8')
    audit=fixture_repo/'workspace/consistency_audit/draft_structure_audit.json'
    audit.write_text(json.dumps(audit_draft_structure(value,fixture_repo)),encoding='utf-8')
    report=build_draft_consistency_report(fixture_repo)
    levels=report['progressive_disclosure']
    assert levels['segment_index']['known_clean'] is True
    assert levels['level_2_structure']['index_schema_supported'] is True
    assert levels['level_2_structure']['index_content_matches'] is True
    assert levels['segment_index']['source_freshness_status']=='UNVERIFIED'
    assert levels['level_0_manifest']['covers_source'] is None
    assert levels['level_0_manifest']['source_freshness_status']=='UNVERIFIED'


def test_rebuilt_index_invalidates_structure_audit_of_previous_content(fixture_repo: Path) -> None:
    from consistency.draft_structure_audit import audit_draft_structure
    from consistency.segment_index import build_segment_index
    original=build_segment_index(fixture_repo)
    audit=audit_draft_structure(original,fixture_repo);audit['findings']=[]
    run=fixture_repo/'workspace/runs/run_test_draft_stage_b_50ch/segments.json'
    data=json.loads(run.read_text(encoding='utf-8'))
    data['chapters'][0]['segments'][0]['draft_text']='synthetic revised draft'
    run.write_text(json.dumps(data),encoding='utf-8')
    current=build_segment_index(fixture_repo,previous_index=original)
    (fixture_repo/'workspace/indexes/segment_index.json').write_text(json.dumps(current),encoding='utf-8')
    (fixture_repo/'workspace/consistency_audit/draft_structure_audit.json').write_text(json.dumps(audit),encoding='utf-8')
    (fixture_repo/'workspace/consistency_audit/local_fix_plan.json').write_text(json.dumps({'stats':{
        'term_fix_count':0,'retranslate_segment_count':0,'deferred_count':0}}),encoding='utf-8')
    report=build_draft_consistency_report(fixture_repo)
    assert report['progressive_disclosure']['level_2_structure']['index_content_matches'] is False
    assert report['status']!='PASS' and report['recommendation']!='ready_for_final_export'


def test_matching_saved_index_and_audit_do_not_prove_source_freshness(fixture_repo: Path) -> None:
    from consistency.draft_structure_audit import audit_draft_structure
    from consistency.segment_index import build_segment_index
    run=fixture_repo/'workspace/runs/run_test_draft_stage_b_50ch/segments.json'
    data=json.loads(run.read_text(encoding='utf-8'))
    data['chapters'][0]['segments'][0]['draft_text']='合成译文'
    run.write_text(json.dumps(data),encoding='utf-8')
    index=build_segment_index(fixture_repo);audit=audit_draft_structure(index,fixture_repo)
    (fixture_repo/'workspace/indexes/segment_index.json').write_text(json.dumps(index),encoding='utf-8')
    (fixture_repo/'workspace/consistency_audit/draft_structure_audit.json').write_text(json.dumps(audit),encoding='utf-8')
    (fixture_repo/'workspace/consistency_audit/local_fix_plan.json').write_text(json.dumps({'stats':{
        'term_fix_count':0,'retranslate_segment_count':0,'deferred_count':0}}),encoding='utf-8')
    for changed in (False,True):
        if changed:
            data['chapters'][0]['segments'][0]['draft_text']='另一份合成译文'
            run.write_text(json.dumps(data),encoding='utf-8')
        report=build_draft_consistency_report(fixture_repo)
        levels=report['progressive_disclosure']
        assert levels['level_2_structure']['index_content_matches'] is True
        assert levels['segment_index']['source_freshness_status']=='UNVERIFIED'
        assert report['status']=='INCOMPLETE'
        assert report['recommendation']!='ready_for_final_export'


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
    assert (audit_dir / "arbitration_report.simulation.json").is_file()
    assert not (audit_dir / "arbitration_report.json").exists()


def _phase_b():
    path = REPO_ROOT / "scripts" / "phase_b_completion_check.py"
    spec = importlib.util.spec_from_file_location("phase_b_truth_fixture", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_incomplete_report_invalid_index_and_zero_budget_do_not_pass(tmp_path, monkeypatch):
    gate = _phase_b()
    report = {
        "status": "INCOMPLETE",
        "recommendation": "verify_current_sources_before_final_export",
        "blocking_conflicts": 0,
        "progressive_disclosure": {
            "level_0_manifest": {"covers_source": False},
            "segment_index": {"known_clean": False, "source_freshness_status": "UNVERIFIED"},
        },
    }
    artifacts = {
        "chapter_manifest.json": {"stats": {"chapters_indexed": 2, "full_coverage": False}},
        "segment_index.json": {"stats": {"missing_segments_count": 0}},
        "entity_index.json": {"stats": {}},
        "glossary_conflict_audit.json": {"findings": []},
        "fix_plan_status.json": {
            "retranslate_tasks": {"status": "partial", "pilot_validated": True},
            "term_fixes": {"status": "closed"},
            "deferred": {"status": "closed"},
            "all_closed": False,
        },
        "arbitration_report.json": {"api_calls": 1, "max_api_calls": 0},
    }
    monkeypatch.setattr(gate, "count_source_chapters", lambda _: 2)
    monkeypatch.setattr(gate, "collect_status", lambda _: {
        "current_phase": "synthetic", "next_task": None, "draft_progress": {},
    })
    monkeypatch.setattr(gate, "_load_orphan_eval", lambda: {"decision": "synthetic"})
    monkeypatch.setattr(gate, "build_draft_consistency_report", lambda _: report)
    monkeypatch.setattr(gate, "_artifact", lambda _, _directory, name: artifacts.get(name))
    report_path = tmp_path / "workspace" / "consistency_audit" / "draft_consistency_report.json"
    report_path.parent.mkdir(parents=True)
    report_path.write_text(json.dumps(report), encoding="utf-8")

    result = gate.evaluate(tmp_path)
    false_passes = [name for name in ("B1", "B2", "B6", "B7", "B8") if result["checks"][name]["pass"]]
    assert false_passes == []
    assert not result["overall_pass"]


def _complete_phase_b_fixture(tmp_path, monkeypatch):
    """Synthetic hypothetical verified report for exercising the gate's positive path."""
    from consistency.conflict_audit import audit_glossary_conflicts
    from consistency.entity_index import build_entity_index
    from consistency.manifest import build_chapter_manifest
    from consistency.segment_index import build_segment_index

    source = tmp_path / "input_jp" / "001-synthetic.md"
    source.parent.mkdir(parents=True)
    source.write_text("# Synthetic\n\nSynthetic source.\n", encoding="utf-8")
    run_root = tmp_path / "workspace" / "runs" / "run_phase_b_fixture"
    _write_run_meta(run_root)
    segments = run_root / "segments.json"
    _write_segments(segments, "ch-001", [("ch-001-seg-001", "source", "draft")])
    doc = json.loads(segments.read_text(encoding="utf-8"))
    doc["chapters"][0]["source_path"] = "input_jp/001-synthetic.md"
    segments.write_text(json.dumps(doc), encoding="utf-8")
    manifest = build_chapter_manifest(tmp_path, total_expected=1)
    index = build_segment_index(tmp_path)
    entity_index = build_entity_index([], [segments])
    glossary_audit = audit_glossary_conflicts([], entity_index)
    plan = build_local_fix_plan({"findings": []}, {"findings": []})
    fix_status = build_fix_plan_status(plan)
    report = {
        "status": "PASS", "recommendation": "ready_for_final_export", "blocking_conflicts": 0,
        "generated_at": "synthetic", "progressive_disclosure": {
            "level_0_manifest": {"covers_source": True, "source_freshness_status": "VERIFIED"},
            "level_1_entity_index": {}, "level_2_glossary_conflicts": {},
            "level_2_structure": {}, "level_3_fix_plan": {}, "level_4_arbitration": {},
            "level_5_retranslate": {"remaining_segments": 0},
            "segment_index": {"source_freshness_status": "VERIFIED"},
        },
    }
    artifacts = {
        "manifests/chapter_manifest.json": manifest,
        "indexes/segment_index.json": index,
        "indexes/entity_index.json": entity_index,
        "consistency_audit/glossary_conflict_audit.json": glossary_audit,
        "consistency_audit/local_fix_plan.json": plan,
        "consistency_audit/fix_plan_status.json": fix_status,
        "consistency_audit/arbitration_report.json": {
            "api_calls": 0, "provider_invocations_used": 0,
            "max_api_calls": 0, "budget_exhausted": False,
        },
        "consistency_audit/draft_consistency_report.json": report,
    }
    for relative, data in artifacts.items():
        path = tmp_path / "workspace" / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data), encoding="utf-8")
    gate = _phase_b()
    monkeypatch.setattr(gate, "collect_status", lambda _: {
        "current_phase": "synthetic", "next_task": None, "draft_progress": {},
    })
    monkeypatch.setattr(gate, "_load_orphan_eval", lambda: {"decision": "synthetic"})
    monkeypatch.setattr(gate, "build_draft_consistency_report", lambda _: report)
    return gate, report


def test_phase_b_accepts_matching_synthetic_snapshot_and_zero_usage(tmp_path, monkeypatch):
    gate, _ = _complete_phase_b_fixture(tmp_path, monkeypatch)
    result = gate.evaluate(tmp_path)
    assert result["overall_pass"] and result["failed_criteria"] == []


def test_glossary_binding_ignores_only_volatile_entity_rebuild_details(tmp_path, monkeypatch):
    from consistency.entity_index import entity_index_digest
    _complete_phase_b_fixture(tmp_path, monkeypatch)
    path = tmp_path / "workspace" / "indexes" / "entity_index.json"
    first = json.loads(path.read_text(encoding="utf-8"))
    reused = json.loads(json.dumps(first))
    reused["generated_at"] = "later synthetic time"
    reused["stats"]["files_scanned"] = 0
    reused["stats"]["files_reused"] = reused["stats"]["files_total"]
    assert entity_index_digest(first) == entity_index_digest(reused)
    reused["dependency_sha256"] = "f" * 64
    assert entity_index_digest(first) != entity_index_digest(reused)


def test_fix_status_cannot_close_with_result_from_another_plan():
    from translation.source_versions import value_sha
    plan = build_local_fix_plan({"findings": []}, {"findings": []})
    plan["retranslate_tasks"] = [{"segment_ids": ["ch-001-seg-001"]}]
    plan["stats"]["retranslate_task_count"] = 1
    plan["stats"]["retranslate_segment_count"] = 1
    result = {"status": "closed", "completed_segments": 1, "remaining_segments": 0,
              "plan_sha256": "0" * 64}
    rejected = build_fix_plan_status(plan, result)
    assert rejected["retranslation_result_matches_plan"] is False and rejected["all_closed"] is False
    result["plan_sha256"] = value_sha(plan)
    accepted = build_fix_plan_status(plan, result)
    assert accepted["retranslation_result_matches_plan"] is True and accepted["all_closed"] is True


def test_fix_status_uses_actual_plan_items_and_rejects_unknown_locations():
    plan = build_local_fix_plan({"findings": []}, {"findings": []})
    plan["term_fixes"].append({"segment_ids": ["ch-001-seg-001"]})
    plan["deferred"].append({"segment_ids": []})
    status = build_fix_plan_status(plan)
    assert status["term_fixes"]["status"] == "pending"
    assert status["deferred"]["status"] == "pending"
    assert status["all_closed"] is False
    unresolved = build_local_fix_plan({"findings": []}, {"findings": []})
    unresolved["retranslate_tasks"].append({"segment_ids": []})
    unresolved["stats"]["retranslate_task_count"] = 1
    result = build_fix_plan_status(unresolved)
    assert result["retranslate_tasks"]["status"] == "unknown"
    assert result["all_closed"] is False
    missing = build_fix_plan_status({"stats": {"term_fix_count": 0, "deferred_count": 0},
                                     "retranslate_tasks": []})
    assert missing["term_fixes"]["status"] == "unknown"
    assert missing["deferred"]["status"] == "unknown" and missing["all_closed"] is False


@pytest.mark.parametrize("mutation, failed", [
    ("stale_saved_report", "B7"),
    ("unverified_source", "B7"),
    ("unverified_manifest", "B7"),
    ("prior_usage_exceeds_zero_cap", "B8"),
    ("cumulative_usage_unknown", "B8"),
    ("entity_index_different_segments", "B3"),
    ("stale_glossary_after_entity_change", "B4"),
    ("glossary_counts_disagree", "B4"),
    ("stale_fix_plan", "B6"),
    ("forged_closed_with_pending_items", "B6"),
])
def test_phase_b_rejects_stale_or_unaccounted_evidence(tmp_path, monkeypatch, mutation, failed):
    gate, report = _complete_phase_b_fixture(tmp_path, monkeypatch)
    audit = tmp_path / "workspace" / "consistency_audit"
    if mutation == "stale_saved_report":
        saved = {**report, "blocking_conflicts": 1}
        (audit / "draft_consistency_report.json").write_text(json.dumps(saved), encoding="utf-8")
    elif mutation == "unverified_source":
        report["progressive_disclosure"]["segment_index"]["source_freshness_status"] = "UNVERIFIED"
        (audit / "draft_consistency_report.json").write_text(json.dumps(report), encoding="utf-8")
    elif mutation == "unverified_manifest":
        report["progressive_disclosure"]["level_0_manifest"]["source_freshness_status"] = "UNVERIFIED"
        (audit / "draft_consistency_report.json").write_text(json.dumps(report), encoding="utf-8")
    elif mutation in {"entity_index_different_segments", "stale_glossary_after_entity_change"}:
        path = tmp_path / "workspace" / "indexes" / "entity_index.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if mutation == "entity_index_different_segments":
            next(iter(data["files"].values()))["fingerprint"] = "sha256:" + "0" * 64
        else:
            data["dependency_sha256"] = "f" * 64
        path.write_text(json.dumps(data), encoding="utf-8")
    elif mutation == "glossary_counts_disagree":
        path = audit / "glossary_conflict_audit.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["findings"].append({"kind": "synthetic", "blocking": True})
        path.write_text(json.dumps(data), encoding="utf-8")
    elif mutation == "stale_fix_plan":
        path = audit / "local_fix_plan.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["retranslate_tasks"].append({"segment_ids": ["ch-001-seg-001"]})
        data["stats"]["retranslate_segment_count"] = 1
        path.write_text(json.dumps(data), encoding="utf-8")
    elif mutation == "forged_closed_with_pending_items":
        from translation.source_versions import value_sha
        path = audit / "local_fix_plan.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["term_fixes"].append({"segment_ids": ["ch-001-seg-001"]})
        data["deferred"].append({"segment_ids": []})
        path.write_text(json.dumps(data), encoding="utf-8")
        status_path = audit / "fix_plan_status.json"
        status = json.loads(status_path.read_text(encoding="utf-8"))
        status["plan_sha256"] = value_sha(data)
        status_path.write_text(json.dumps(status), encoding="utf-8")
    else:
        path = audit / "arbitration_report.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        if mutation == "prior_usage_exceeds_zero_cap":
            data["provider_invocations_used"] = 1
        else:
            del data["provider_invocations_used"]
        path.write_text(json.dumps(data), encoding="utf-8")
    result = gate.evaluate(tmp_path)
    assert not result["checks"][failed]["pass"]
    assert not result["overall_pass"]
