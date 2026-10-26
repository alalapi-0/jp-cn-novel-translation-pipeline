"""Source-denominator and unknown-lineage regressions; all data is synthetic."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import importlib.util

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from quality_review.checkers import check_segment_alignment
from quality_review import runner, workbench_adapter
from workbench import project_registry as registry
from workbench.dry_run_generate import source_segments_from_sample


def document():
    return {"project_id": "synthetic-book", "language_direction": "JP_TO_CN", "chapter_id": "ch-test",
            "expected_segment_ids": ["s1", "s2"], "paragraphs": [{"paragraph_id": "p1", "segments": [
                {"segment_id": "s1", "source_text": "風が吹く。", "target_text": "风吹过。"},
                {"segment_id": "s2", "source_text": "雨が降る。", "target_text": "雨落下。"}]}]}


@pytest.mark.parametrize("damage,rule", [
    ("duplicate", "duplicate_target_id"), ("empty", "empty_target"),
    ("extra", "unexpected_target_id"), ("unknown_expected", "unknown_expected_source"),
    ("changed_source", "source_revision_mismatch"), ("invalid_expected", "invalid_expected_id"),
])
def test_complete_looking_outputs_do_not_hide_source_integrity_failure(damage, rule):
    doc = document(); rows = doc["paragraphs"][0]["segments"]
    if damage == "duplicate": rows.append(deepcopy(rows[0]))
    elif damage == "empty": rows[0]["target_text"] = ""
    elif damage == "extra": rows.append({**rows[0], "segment_id": "s-extra"})
    elif damage == "unknown_expected": del doc["expected_segment_ids"]
    elif damage == "invalid_expected": doc["expected_segment_ids"] = [[]]
    else:
        doc["source_expected_sha256"] = {"s1": hashlib.sha256("別の原文".encode()).hexdigest()}
    issues = check_segment_alignment(doc)
    assert any(i.evidence.get("rule") == rule for i in issues)
    assert all(i.issue_type == "SEGMENT_ALIGNMENT_ERROR" for i in issues)


def test_missing_entire_output_uses_fixed_source_denominator():
    doc = document(); doc["paragraphs"][0]["segments"].pop()
    assert any(i.segment_id == "s2" and i.issue_type == "SEGMENT_ALIGNMENT_ERROR"
               for i in check_segment_alignment(doc))


def test_real_project_never_reads_synthetic_glossary_fallback(monkeypatch):
    def forbidden(path): raise AssertionError("real project attempted fixture read")
    monkeypatch.setattr(runner, "load_json", forbidden)
    report = workbench_adapter.run_review_for_workbench(project_id="real-book", language_direction="JP_TO_CN",
                segments=[{"id": "s1", "source": "風が吹く。", "draft": "风吹过。"}])
    assert report.summary["glossary_source"] == "none_no_project_glossary"
    assert any(i.evidence.get("rule") == "unknown_expected_source" for i in report.issues)


def test_imported_source_scope_survives_missing_outputs_and_source_edits(tmp_path):
    source = [{"id": "s1", "source": "風が吹く。"}, {"id": "s2", "source": "雨が降る。"}]
    original = registry.create_project_manifest(tmp_path, project_id="source-scope", name="合成",
                    language_direction="JP_TO_CN", segments=source)
    before = deepcopy(original.source_inventory)
    changed = registry.update_project_segments(tmp_path, "source-scope", [{**source[0], "draft": "风吹过。"}])
    assert changed.source_inventory == before
    report = workbench_adapter.run_review_for_workbench(project_id=changed.project_id,
        language_direction=changed.language_direction, segments=list(changed.segments), source_inventory=changed.source_inventory)
    assert any(i.evidence.get("rule") == "missing_target_id" and i.segment_id == "s2" for i in report.issues)
    changed = registry.update_project_segments(tmp_path, "source-scope", [{**source[0], "source": "雪が降る。", "draft": "雪落下。"},
                                                                                        {**source[1], "draft": ""}])
    report = workbench_adapter.run_review_for_workbench(project_id=changed.project_id,
        language_direction=changed.language_direction, segments=list(changed.segments), source_inventory=changed.source_inventory)
    assert {i.evidence.get("rule") for i in report.issues} >= {"source_revision_mismatch", "empty_target"}


def test_legacy_scope_is_unknown_without_rewriting_or_reconstructing(tmp_path):
    payload = {"project_id": "legacy", "name": "Legacy", "language_direction": "JP_TO_CN", "segments": [
        {"id": "s1", "source": "風が吹く。", "draft": "风吹过。", "status": "human_reviewed"}]}
    manifest = registry.save_project_manifest(tmp_path, payload)
    before = manifest.path.read_bytes()
    report = workbench_adapter.run_review_for_workbench(project_id=manifest.project_id,
        language_direction=manifest.language_direction, segments=list(manifest.segments), source_inventory=manifest.source_inventory)
    assert manifest.source_inventory is None and manifest.path.read_bytes() == before
    assert report.review_status == "review_needed"
    assert report.to_dict()["review_actor_type"] == "machine" and report.to_dict()["approval_state"] == "not_granted"


@pytest.mark.parametrize("direction", ["JP_TO_CN", "CN_TO_JP"])
def test_source_import_uses_all_input_before_output_and_supports_both_directions(tmp_path, direction):
    source = source_segments_from_sample("一段\n\n二段\n\n三段\n\n四段")
    assert len(source) == 4
    registry.create_project_manifest(tmp_path, project_id="import", name="Import", language_direction=direction)
    result = registry.update_project_segments(tmp_path, "import", [{**r, "draft": "合成目标"} for r in source[:3]], source_segments=source)
    entries = registry.validated_source_entries(result.source_inventory, language_direction=direction)
    assert len(entries) == 4
    report = workbench_adapter.run_review_for_workbench(project_id=result.project_id,
        language_direction=direction, segments=list(result.segments), source_inventory=result.source_inventory)
    assert any(i.segment_id == "seg-004" and i.evidence.get("rule") == "missing_target_id" for i in report.issues)


def test_inventory_corruption_cannot_be_replaced_by_present_targets():
    source = [{"id": "s1", "source": "風が吹く。"}]
    inventory = registry.build_source_inventory(source, language_direction="JP_TO_CN")
    for bad in (None, {**inventory, "inventory_sha256": "0" * 64},
                {**inventory, "entries": inventory["entries"] * 2}):
        report = workbench_adapter.run_review_for_workbench(project_id="real-book", language_direction="JP_TO_CN",
            segments=[{**source[0], "draft": "风吹过。"}], source_inventory=bad)
        assert any(i.evidence.get("rule") == "unknown_expected_source" for i in report.issues)
        assert report.review_status == "review_needed"
    with pytest.raises(ValueError):
        registry.build_source_inventory([{"id": "s1", "source": ""}], language_direction="JP_TO_CN")


def test_source_change_and_empty_target_are_independent_failures():
    doc = document(); doc["paragraphs"][0]["segments"][0]["target_text"] = ""
    doc["source_expected_sha256"] = {"s1": "0" * 64}
    assert {i.evidence.get("rule") for i in check_segment_alignment(doc)} >= {"source_revision_mismatch", "empty_target"}


def test_generic_runner_and_cli_custom_input_never_inherit_demo_terms(tmp_path, monkeypatch, capsys):
    original = runner.load_json
    def guarded(path):
        assert path != runner.DEFAULT_GLOSSARY, "custom source inherited demo glossary"
        return original(path)
    monkeypatch.setattr(runner, "load_json", guarded)
    report = runner.run_review(segments_doc=document())
    assert report.summary["glossary_source"] == "none_no_project_glossary"
    fixture = tmp_path / "synthetic-custom.json"; fixture.write_text(json.dumps(document()))
    script = Path(__file__).resolve().parents[1] / "scripts/run_quality_review.py"
    spec = importlib.util.spec_from_file_location("coverage_cli_test", script)
    module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
    assert module.main(["--segments", str(fixture), "--json"]) == 1
    result = json.loads(capsys.readouterr().out)
    assert result["summary"]["glossary_source"] == "none_no_project_glossary"
    assert result["review_actor_type"] == "machine" and result["approval_state"] == "not_granted"
