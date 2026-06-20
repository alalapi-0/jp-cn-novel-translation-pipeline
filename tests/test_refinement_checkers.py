"""FS-043: refinement quality checker tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from refinement.checkers import (  # noqa: E402
    BLOCKING_CRITERIA,
    CHECKER_CHARACTER_VOICE,
    CHECKER_OVER_REFINEMENT,
    CHECKER_TERMINOLOGY,
    aggregate_exit_code,
    check_character_voice,
    check_over_refinement,
    check_terminology_preservation,
    run_refinement_checks,
    run_refinement_checks_for_run,
)
from refinement.diff_builder import build_refine_diff  # noqa: E402

FIXTURES = REPO_ROOT / "tests" / "fixtures"
PASS_SEGMENTS = FIXTURES / "refinement_check_segments_pass.json"
FAIL_SEGMENTS = FIXTURES / "refinement_check_segments_fail.json"
FIXTURE_GLOSSARY = FIXTURES / "refinement_check_glossary.yaml"
FIXTURE_CHARACTER = FIXTURES / "refinement_check_character_profile.yaml"


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _load_yaml(path: Path) -> dict:
    import yaml

    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _load_check_script():
    spec = importlib.util.spec_from_file_location(
        "check_refinement_quality_test",
        REPO_ROOT / "scripts" / "check_refinement_quality.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _segments_from_doc(doc: dict) -> list[dict]:
    return [
        {
            "segment_id": s["segment_id"],
            "chapter_id": ch.get("chapter_id", ""),
            "source_text": s.get("source_text", ""),
            "draft_text": s["draft_text"],
            "refined_text": s.get("refined_text", ""),
            "human_edited": False,
        }
        for ch in doc["chapters"]
        for s in ch["segments"]
    ]


def test_blocking_criteria_documented() -> None:
    assert set(BLOCKING_CRITERIA) == {
        CHECKER_OVER_REFINEMENT,
        CHECKER_TERMINOLOGY,
        CHECKER_CHARACTER_VOICE,
    }
    for rule in BLOCKING_CRITERIA.values():
        assert "BLOCK" in rule


def test_over_refinement_positive_fixture() -> None:
    doc = _load_json(PASS_SEGMENTS)
    _, change_log = build_refine_diff(doc)
    issues, summary = check_over_refinement(change_log["segments"])
    assert summary.status == "pass"
    assert summary.blocking_count == 0
    assert not issues


def test_over_refinement_negative_fixture() -> None:
    doc = _load_json(FAIL_SEGMENTS)
    _, change_log = build_refine_diff(doc)
    issues, summary = check_over_refinement(change_log["segments"])
    assert summary.status == "blocking"
    assert summary.blocking_count >= 1
    assert any(i.rule == "segment_over_refined" for i in issues)
    assert any(i.rule == "round_over_refined_fraction" for i in issues)


def test_terminology_positive_fixture() -> None:
    doc = _load_json(PASS_SEGMENTS)
    glossary = _load_yaml(FIXTURE_GLOSSARY)
    issues, summary = check_terminology_preservation(_segments_from_doc(doc), glossary)
    assert summary.status == "pass"
    assert not issues


def test_terminology_negative_fixture() -> None:
    doc = _load_json(FAIL_SEGMENTS)
    glossary = _load_yaml(FIXTURE_GLOSSARY)
    issues, summary = check_terminology_preservation(_segments_from_doc(doc), glossary)
    assert summary.status == "blocking"
    assert any(i.rule == "locked_term_altered" for i in issues)
    assert any(i.evidence.get("target_term") == "示例王国" for i in issues)


def test_character_voice_positive_fixture() -> None:
    doc = _load_json(PASS_SEGMENTS)
    character = _load_yaml(FIXTURE_CHARACTER)
    issues, summary = check_character_voice(_segments_from_doc(doc), character)
    assert summary.status == "pass"
    assert not issues


def test_character_voice_negative_fixture() -> None:
    doc = _load_json(FAIL_SEGMENTS)
    character = _load_yaml(FIXTURE_CHARACTER)
    issues, summary = check_character_voice(_segments_from_doc(doc), character)
    assert summary.status == "blocking"
    assert any(i.rule == "voice_marker_lost" for i in issues)
    assert any(i.evidence.get("marker") == "俺" for i in issues)


def test_run_refinement_checks_pass_aggregate() -> None:
    doc = _load_json(PASS_SEGMENTS)
    report = run_refinement_checks(
        doc,
        glossary_path=FIXTURE_GLOSSARY,
        character_path=FIXTURE_CHARACTER,
    )
    assert report.status == "pass"
    assert report.blocking_count == 0
    assert aggregate_exit_code(report) == 0
    assert len(report.checkers) == 3


def test_run_refinement_checks_fail_aggregate() -> None:
    doc = _load_json(FAIL_SEGMENTS)
    report = run_refinement_checks(
        doc,
        glossary_path=FIXTURE_GLOSSARY,
        character_path=FIXTURE_CHARACTER,
    )
    assert report.status == "blocking"
    assert report.blocking_count >= 3
    assert aggregate_exit_code(report) == 2
    checker_names = {c.checker for c in report.checkers if c.status == "blocking"}
    assert CHECKER_OVER_REFINEMENT in checker_names
    assert CHECKER_TERMINOLOGY in checker_names
    assert CHECKER_CHARACTER_VOICE in checker_names


def test_run_refinement_checks_for_run(tmp_path: Path) -> None:
    run_id = "run_refine_check_test"
    run_root = tmp_path / "workspace" / "runs" / run_id
    run_root.mkdir(parents=True)
    doc = _load_json(PASS_SEGMENTS)
    (run_root / "segments.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    (run_root / "run_metadata.json").write_text(json.dumps({"run_id": run_id}), encoding="utf-8")

    report = run_refinement_checks_for_run(
        run_root,
        repo_root=tmp_path,
        glossary_path=FIXTURE_GLOSSARY,
        character_path=FIXTURE_CHARACTER,
    )
    assert report.run_id == run_id
    assert report.status == "pass"


def test_check_refinement_quality_cli_pass_json(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOW_LEGACY_REFINEMENT", "1")
    mod = _load_check_script()
    code = mod.main(
        [
            "--segments",
            str(PASS_SEGMENTS),
            "--glossary",
            str(FIXTURE_GLOSSARY),
            "--character-profile",
            str(FIXTURE_CHARACTER),
            "--json",
        ]
    )
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "pass"
    assert payload["blocking_criteria"]


def test_check_refinement_quality_cli_fail_json(
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOW_LEGACY_REFINEMENT", "1")
    mod = _load_check_script()
    code = mod.main(
        [
            "--segments",
            str(FAIL_SEGMENTS),
            "--glossary",
            str(FIXTURE_GLOSSARY),
            "--character-profile",
            str(FIXTURE_CHARACTER),
            "--json",
        ]
    )
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "blocking"
    assert payload["blocking_count"] >= 1
