"""Tests for FS-036: local fix plan and term-fix applier."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from consistency.conflict_audit import audit_glossary_conflicts  # noqa: E402
from consistency.draft_structure_audit import audit_draft_structure  # noqa: E402
from consistency.entity_index import build_entity_index  # noqa: E402
from consistency.local_fix_plan import (  # noqa: E402
    apply_term_fixes,
    build_local_fix_plan,
    preview_term_fixes,
)
from consistency.segment_index import build_segment_index  # noqa: E402
from glossary import GlossaryEntry  # noqa: E402
from scheduler.task_planner import plan_next_task  # noqa: E402

BUILD_SCRIPT = REPO_ROOT / "scripts" / "build_local_fix_plan.py"
APPLY_SCRIPT = REPO_ROOT / "scripts" / "apply_term_fixes.py"


def _load_script(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = mod
    spec.loader.exec_module(mod)
    return mod


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


def _write_run_meta(run_dir: Path, *, offset: int = 0) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "run_metadata.json").write_text(
        json.dumps({"run_id": run_dir.name, "phase": "draft", "chapter_offset": offset}),
        encoding="utf-8",
    )
    (run_dir / "run_progress.json").write_text(
        json.dumps({"run_id": run_dir.name, "status": "completed", "total_segments": 3, "completed_segments": 3}),
        encoding="utf-8",
    )


@pytest.fixture()
def fixture_repo(tmp_path: Path) -> Path:
    runs = tmp_path / "workspace" / "runs" / "run_fix_fixture"
    _write_run_meta(runs)
    _write_segments(
        runs / "segments.json",
        "ch-001",
        [
            ("ch-001-seg-001", "サンプル王国", "示例皇国的早晨"),
            ("ch-001-seg-002", "サンプルギルド", "另译公会的前台"),
            ("ch-001-seg-003", "アルファ団", "阿尔法团アルファ活动"),
        ],
    )
    return tmp_path


def _glossary_audit(repo: Path) -> dict:
    runs = repo / "workspace" / "runs"
    terms = [
        GlossaryEntry(source_term="サンプル王国", target_term="示例王国", category="place_name", locked=True),
        GlossaryEntry(source_term="サンプルギルド", target_term="示例公会", category="organization_name"),
    ]
    files = sorted(runs.glob("run_*/segments.json"))
    index = build_entity_index(terms, files, all_terms=terms)
    return audit_glossary_conflicts(terms, index, generated_at="FIXED")


def _structure_audit(repo: Path) -> dict:
    index = build_segment_index(repo)
    return audit_draft_structure(index, repo, generated_at="FIXED")


def test_locked_violation_becomes_term_fix(fixture_repo: Path) -> None:
    plan = build_local_fix_plan(_glossary_audit(fixture_repo), _structure_audit(fixture_repo))
    term_fixes = plan["term_fixes"]
    assert term_fixes
    locked = [f for f in term_fixes if f["kind"] == "locked_violation"]
    assert locked
    assert locked[0]["canonical_target"] == "示例王国"
    assert locked[0]["alternate_target"] == "示例皇国"
    assert "ch-001-seg-001" in locked[0]["segment_ids"]


def test_source_residual_becomes_retranslate_task(fixture_repo: Path) -> None:
    plan = build_local_fix_plan(_glossary_audit(fixture_repo), _structure_audit(fixture_repo))
    retranslate = plan["retranslate_tasks"]
    residual = [t for t in retranslate if t["kind"] == "source_residual"]
    assert residual
    assert residual[0]["segment_ids"]
    assert not residual[0]["blocking"]


def test_unlisted_high_freq_is_deferred_not_retranslate(fixture_repo: Path) -> None:
    plan = build_local_fix_plan(_glossary_audit(fixture_repo), _structure_audit(fixture_repo))
    deferred_kinds = {d["kind"] for d in plan["deferred"]}
    retranslate_kinds = {t["kind"] for t in plan["retranslate_tasks"]}
    if "unlisted_high_freq" in deferred_kinds:
        assert "unlisted_high_freq" not in retranslate_kinds


def test_plan_has_no_body_text(fixture_repo: Path) -> None:
    plan = build_local_fix_plan(_glossary_audit(fixture_repo), _structure_audit(fixture_repo))
    raw = json.dumps(plan, ensure_ascii=False)
    assert "draft_text" not in raw
    assert "source_text" not in raw
    assert "另译公会的前台" not in raw


def test_apply_term_fixes_dry_run_shows_diff(fixture_repo: Path) -> None:
    plan = build_local_fix_plan(_glossary_audit(fixture_repo), _structure_audit(fixture_repo))
    result = apply_term_fixes(plan, fixture_repo, dry_run=True)
    assert result["applied_count"] >= 1
    previews = preview_term_fixes(plan, fixture_repo)
    changed = [p for p in previews if p["changed"]]
    assert changed
    assert any("示例皇国" in p["diff"] and "示例王国" in p["diff"] for p in changed)


def test_apply_does_not_touch_source_or_checkpoint(fixture_repo: Path) -> None:
    seg_path = fixture_repo / "workspace" / "runs" / "run_fix_fixture" / "segments.json"
    progress_path = fixture_repo / "workspace" / "runs" / "run_fix_fixture" / "run_progress.json"
    before_seg = seg_path.read_text(encoding="utf-8")
    before_progress = progress_path.read_text(encoding="utf-8")
    source_snapshot = json.loads(before_seg)["chapters"][0]["segments"][0]["source_text"]

    plan = build_local_fix_plan(_glossary_audit(fixture_repo), _structure_audit(fixture_repo))
    apply_term_fixes(plan, fixture_repo, dry_run=False)

    after_doc = json.loads(seg_path.read_text(encoding="utf-8"))
    assert progress_path.read_text(encoding="utf-8") == before_progress
    seg0 = after_doc["chapters"][0]["segments"][0]
    assert seg0["source_text"] == source_snapshot
    assert "示例王国" in seg0["draft_text"]
    assert "示例皇国" not in seg0["draft_text"]


def test_build_local_fix_plan_cli(tmp_path: Path, fixture_repo: Path) -> None:
    glossary = _glossary_audit(fixture_repo)
    structure = _structure_audit(fixture_repo)
    glossary_path = tmp_path / "glossary_audit.json"
    structure_path = tmp_path / "structure_audit.json"
    glossary_path.write_text(json.dumps(glossary), encoding="utf-8")
    structure_path.write_text(json.dumps(structure), encoding="utf-8")

    mod = _load_script(BUILD_SCRIPT, "ln_build_fix_plan_cli")
    rc = mod.main(
        [
            "--glossary-audit",
            str(glossary_path),
            "--structure-audit",
            str(structure_path),
            "--output",
            str(tmp_path / "plan.json"),
            "--repo-root",
            str(fixture_repo),
            "--json",
        ]
    )
    assert rc == 0
    plan = json.loads((tmp_path / "plan.json").read_text(encoding="utf-8"))
    assert plan["stats"]["term_fix_count"] >= 1


def test_apply_term_fixes_cli_dry_run(fixture_repo: Path, tmp_path: Path) -> None:
    plan = build_local_fix_plan(_glossary_audit(fixture_repo), _structure_audit(fixture_repo))
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan), encoding="utf-8")

    mod = _load_script(APPLY_SCRIPT, "ln_apply_term_fixes_cli")
    rc = mod.main(
        [
            "--plan",
            str(plan_path),
            "--repo-root",
            str(fixture_repo),
            "--dry-run",
            "--json",
        ]
    )
    assert rc == 0


def test_consistency_phase_plans_build_fix_plan() -> None:
    status = {
        "current_phase": "consistency",
        "next_task": "draft_consistency_audit",
        "paused": False,
        "detail": {},
    }
    plan = plan_next_task(status, mode="dry_run")
    assert plan.implemented is True
    assert plan.task_type == "consistency_build_fix_plan"
    assert plan.command is not None
    assert plan.command[1].endswith("build_local_fix_plan.py")
    assert "--json" in plan.command


def test_consistency_apply_term_fixes_dry_run_by_default() -> None:
    status = {
        "current_phase": "consistency",
        "next_task": "consistency_apply_term_fixes",
        "paused": False,
        "detail": {},
    }
    plan = plan_next_task(status, mode="dry_run")
    assert plan.implemented is True
    assert plan.task_type == "consistency_apply_term_fixes"
    assert "--dry-run" in plan.command
    assert "--apply" not in plan.command


def test_consistency_retranslate_not_implemented() -> None:
    status = {
        "current_phase": "consistency",
        "next_task": "consistency_retranslate",
        "paused": False,
        "detail": {},
    }
    plan = plan_next_task(status)
    assert plan.implemented is False
    assert plan.task_type == "consistency_retranslate"
    assert "FS-037" in plan.reason
