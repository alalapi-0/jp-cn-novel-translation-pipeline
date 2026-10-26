"""Malformed complete responses must never mutate drafts or successful state."""
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from translation.chapter_parser import ParsedChapter, Segment
from translation import draft_runner
from translation.response_extractor import ExtractedItem, extract_translations
from translation.validator import validate_draft_items


@pytest.mark.parametrize("items", [
    [{"segment_id": "s1", "translation": ""}, {"segment_id": "s2", "translation": "第二段"}],
    [{"segment_id": "s1", "translation": None}, {"segment_id": "s2", "translation": "第二段"}],
    [{"segment_id": "s1", "translation": 123}, {"segment_id": "s2", "translation": "第二段"}],
    [{"segment_id": "s1", "translation": "第一段"}, {"segment_id": "s1", "translation": "另一段"},
     {"segment_id": "s2", "translation": "第二段"}],
    [{"segment_id": "s1", "translation": "第一段"}, {"segment_id": "s2", "translation": "第二段"},
     {"segment_id": "extra", "translation": "额外"}],
    [{"segment_id": "s1", "translation": "第一段"}, {"segment_id": "s2", "translation": "第二段"}, 123],
    [{"segment_id": "s1", "translation": "第一段"}],
])
def test_complete_but_invalid_response_is_atomic(items):
    batch = [Segment("s1", "第一段です。"), Segment("s2", "第二段です。", "原有人工修改", "human_edited")]
    chapter = ParsedChapter("ch-synthetic", "synthetic", "合成", batch)
    before = [vars(s).copy() for s in batch]
    ok, _ = draft_runner._apply_items(chapter, batch, json.dumps({"items": items}))
    assert ok is False
    assert [vars(s) for s in batch] == before


def test_extractor_retains_duplicate_records_as_failure_evidence():
    result = extract_translations(json.dumps({"items": [
        {"segment_id": "s1", "translation": "第一版"},
        {"segment_id": "s1", "translation": "第二版"}]}), ["s1"])
    assert len(result.items) == 2
    assert result.parse_status != "ok"
    assert "duplicate_segment_id:s1" in result.parse_errors


def test_validator_rejects_duplicate_ids_and_invalid_source_contract():
    item = ExtractedItem("s1", "第一段")
    for items, expected, lengths in (([item, item], ["s1"], {"s1": 5}),
                                      ([item], ["s1", "s1"], {"s1": 5}),
                                      ([item], [], {}), ([item], ["s1"], {"s1": 0}),
                                      ([item], [[]], {}), ([ExtractedItem([], "bad")], ["s1"], {"s1": 5})):
        validation = validate_draft_items(items, expected, lengths)
        assert not validation.passed
        assert any(i.severity == "error" for i in validation.issues)


def test_length_heuristic_is_visible_warning_and_never_semantic_approval():
    batch = [Segment("s1", "あ" * 100)]
    chapter = ParsedChapter("ch-synthetic", "synthetic", "合成", batch)
    warnings = []
    ok, _ = draft_runner._apply_items(chapter, batch, json.dumps({
        "items": [{"segment_id": "s1", "translation": "短"}]}), warnings=warnings)
    assert ok and batch[0].status == "machine_translated"
    assert warnings and warnings[0]["code"] == "length_ratio"
    assert warnings[0]["severity"] == "warning"
    assert "human" not in batch[0].status and "approved" not in batch[0].status


@pytest.mark.parametrize("raw_override", ["duplicate", None, 123])
def test_invalid_response_never_enters_success_checkpoint(tmp_path, monkeypatch, raw_override):
    monkeypatch.setenv("CONTROLLED_RUN_ENABLED", "true")
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "false")
    monkeypatch.setattr(draft_runner, "MAX_API_RETRIES", 1)
    source = tmp_path / "input_jp"; source.mkdir()
    (source / "001-synthetic.md").write_text("# 合成\n\n第一段です。\n\n第二段です。")
    calls = []
    class Provider:
        provider_id = "synthetic"; model_name = "synthetic"; network_calls = 0
        def generate(self, messages, options=None):
            from providers.types import ModelResult
            calls.append("synthetic_call")
            rows = [{"segment_id": "ch-001-seg-001", "translation": "第一段"},
                    {"segment_id": "ch-001-seg-001", "translation": "重复"},
                    {"segment_id": "ch-001-seg-002", "translation": "第二段"}]
            result = ModelResult(provider_id=self.provider_id, model_name=self.model_name,
                                 raw_output=json.dumps({"items": rows}) if raw_override == "duplicate" else raw_override)
            result.mark_finished("ok"); return result
    summary, run = draft_runner.run_draft_stage_a(repo_root=tmp_path, input_dir=source,
                        limit_chapters=1, run_id="invalid-output", provider_factory=lambda guard: Provider())
    assert calls == ["synthetic_call"] and summary.aborted
    progress = json.loads((run / "run_progress.json").read_text())
    assert progress["status"] == "failed" and progress["completed_segments"] == 0
    metadata = json.loads((run / "run_metadata.json").read_text())
    assert metadata["summary"]["aborted"] and metadata["summary"]["translated_segments"] == 0
    # Failure exits publish failed progress/metadata rather than a success report.
    report = run / "draft_quality_report.json"
    assert not report.exists() or not json.loads(report.read_text())["passed"]
    records = json.loads((run / "segments.json").read_text())
    assert all(not s["draft_text"] for ch in records["chapters"] for s in ch["segments"])
    checkpoints = list((tmp_path / "workspace/checkpoints").glob("*.json"))
    assert checkpoints
    assert all("completed_segments" in json.loads(p.read_text()) for p in checkpoints)
    assert all(not json.loads(p.read_text())["completed_segments"] for p in checkpoints)


@pytest.mark.parametrize("raw", [None, 123])
def test_non_string_raw_response_is_structured_failure(raw):
    result = extract_translations(raw, ["s1"])
    assert result.parse_status == "failed" and result.parse_errors == ["invalid_raw_output_type"]
    batch = [Segment("s1", "合成")]
    chapter = ParsedChapter("ch-synthetic", "synthetic", "合成", batch)
    assert draft_runner._apply_items(chapter, batch, raw)[0] is False
    assert batch[0].draft_text == "" and batch[0].status == "pending"


def test_invalid_source_identity_cannot_throw_before_rejection():
    batch = [Segment([], "合成")]
    chapter = ParsedChapter("ch-synthetic", "synthetic", "合成", batch)
    assert draft_runner._apply_items(chapter, batch, "{}")[0] is False
    assert batch[0].status == "pending" and not batch[0].draft_text


def test_empty_source_run_cannot_pass_structural_quality(tmp_path):
    draft_runner._write_quality_reports(tmp_path, draft_runner.STAGE_A_SPEC,
                                       draft_runner.DraftRunSummary(run_id="empty"), [])
    assert json.loads((tmp_path / "draft_quality_report.json").read_text())["passed"] is False


def test_warning_survives_real_draft_entry_and_report(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROLLED_RUN_ENABLED", "true")
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "false")
    source = tmp_path / "input_jp"; source.mkdir()
    (source / "001-synthetic.md").write_text("# 合成\n\n" + "あ" * 100)
    class Provider:
        provider_id = "synthetic"; model_name = "synthetic"; network_calls = 0
        def generate(self, messages, options=None):
            from providers.types import ModelResult
            result = ModelResult(provider_id=self.provider_id, model_name=self.model_name,
                                 raw_output=json.dumps({"items": [{"segment_id": "ch-001-seg-001", "translation": "短"}]}))
            result.mark_finished("ok"); return result
    summary, run = draft_runner.run_draft_stage_a(repo_root=tmp_path, input_dir=source,
                        limit_chapters=1, run_id="length-warning", provider_factory=lambda guard: Provider())
    report = json.loads((run / "draft_quality_report.json").read_text())
    assert not summary.aborted and report["passed"]  # Structural completeness only.
    assert report["quality_scope"].endswith("semantic_review_pending")
    warning = report["chapter_results"][0]["validation_warnings"][0]
    assert warning["code"] == "length_ratio" and warning["severity"] == "warning"
