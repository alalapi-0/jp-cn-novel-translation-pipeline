"""Tests for FS-034: glossary conflict audit.

Acceptance (docs/final_state_round_task_list.md FS-034):
- locked / approved violations are blocking;
- divergent_translation, shared_target, unlisted_high_freq are non-blocking;
- stats reproducible for same inputs;
- report includes chapter / segment locations; no body text.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from glossary import GlossaryEntry  # noqa: E402
from consistency.conflict_audit import (  # noqa: E402
    BLOCKING_RULES,
    audit_glossary_conflicts,
    audit_summary,
    chapters_from_segment_ids,
)
from consistency.entity_index import build_entity_index  # noqa: E402

SCRIPT = REPO_ROOT / "scripts" / "audit_glossary_conflicts.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("light_novel_conflict_audit_cli", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["light_novel_conflict_audit_cli"] = mod
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
                    {"segment_id": sid, "source_text": src, "draft_text": dst, "status": "machine_translated"}
                    for sid, src, dst in rows
                ],
            }
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")


@pytest.fixture()
def runs_dir(tmp_path) -> Path:
    base = tmp_path / "runs"
    _write_segments(
        base / "run_a" / "segments.json",
        "ch-001",
        [
            ("ch-001-seg-001", "サンプル王国の朝とアルファ団", "示例王国的早晨与阿尔法团"),
            ("ch-001-seg-002", "サンプル王国とサンプルギルド、アルファ団", "示例王国与示例公会、阿尔法团"),
            ("ch-001-seg-003", "サンプルギルドの受付", "另译公会的前台"),
        ],
    )
    _write_segments(
        base / "run_b" / "segments.json",
        "ch-002",
        [
            ("ch-002-seg-001", "サンプル王国の夜、アルファ団", "示例皇国的夜晚、阿尔法团"),
            ("ch-002-seg-002", "サンプル王国の城", "示例皇国的城"),
        ],
    )
    return base


def _entity_terms(*, locked_kingdom: bool = False, approved_guild: bool = False) -> list[GlossaryEntry]:
    return [
        GlossaryEntry(
            source_term="サンプル王国",
            target_term="示例王国",
            category="place_name",
            locked=locked_kingdom,
        ),
        GlossaryEntry(
            source_term="サンプルギルド",
            target_term="示例公会",
            category="organization_name",
            approved_by_user=approved_guild,
        ),
        GlossaryEntry(
            source_term="サンプル組合",
            target_term="示例公会",
            category="organization_name",
        ),
    ]


def _build_fixture_index(runs_dir: Path, terms: list[GlossaryEntry]) -> dict:
    files = sorted(runs_dir.glob("run_*/segments.json"))
    return build_entity_index(terms, files, all_terms=terms)


def test_chapters_from_segment_ids():
    assert chapters_from_segment_ids(["ch-001-seg-001", "ch-002-seg-003"]) == ["ch-001", "ch-002"]


def test_blocking_rules_documented():
    assert BLOCKING_RULES["locked_violation"] == "blocking"
    assert BLOCKING_RULES["approved_violation"] == "blocking"
    assert BLOCKING_RULES["divergent_translation"] == "non-blocking"
    assert BLOCKING_RULES["unlisted_high_freq"] == "non-blocking"


def test_locked_violation_is_blocking(runs_dir):
    terms = _entity_terms(locked_kingdom=True)
    index = _build_fixture_index(runs_dir, terms)
    report = audit_glossary_conflicts(terms, index, generated_at="FIXED")
    locked = [f for f in report["findings"] if f["kind"] == "locked_violation"]
    assert len(locked) == 1
    assert locked[0]["blocking"] is True
    assert locked[0]["source_term"] == "サンプル王国"
    assert "ch-001" in locked[0]["chapters"] or "ch-002" in locked[0]["chapters"]
    assert locked[0]["segment_ids"]
    assert report["stats"]["blocking_count"] >= 1


def test_approved_violation_is_blocking(runs_dir):
    terms = _entity_terms(approved_guild=True)
    index = _build_fixture_index(runs_dir, terms)
    report = audit_glossary_conflicts(terms, index, generated_at="FIXED")
    approved = [f for f in report["findings"] if f["kind"] == "approved_violation"]
    assert len(approved) == 1
    assert approved[0]["blocking"] is True
    assert approved[0]["source_term"] == "サンプルギルド"


def test_divergent_and_shared_non_blocking_without_protection(runs_dir):
    terms = _entity_terms()
    index = _build_fixture_index(runs_dir, terms)
    report = audit_glossary_conflicts(terms, index, generated_at="FIXED")
    divergent = [f for f in report["findings"] if f["kind"] == "divergent_translation"]
    shared = [f for f in report["findings"] if f["kind"] == "shared_target"]
    assert divergent and all(not f["blocking"] for f in divergent)
    assert shared and all(not f["blocking"] for f in shared)
    assert report["stats"]["blocking_count"] == 0
    assert audit_summary(report)["status"] == "PASS"


def test_unlisted_high_freq_non_blocking_with_locations(runs_dir):
    terms = _entity_terms()
    index = _build_fixture_index(runs_dir, terms)
    report = audit_glossary_conflicts(terms, index, generated_at="FIXED")
    unlisted = [f for f in report["findings"] if f["kind"] == "unlisted_high_freq"]
    assert unlisted
    assert unlisted[0]["source_term"] == "アルファ団"
    assert not unlisted[0]["blocking"]
    assert unlisted[0]["chapters"]
    assert unlisted[0]["segment_ids"]


def test_protected_terms_not_double_counted_as_divergent(runs_dir):
    terms = _entity_terms(locked_kingdom=True)
    index = _build_fixture_index(runs_dir, terms)
    report = audit_glossary_conflicts(terms, index, generated_at="FIXED")
    kingdom_divergent = [
        f
        for f in report["findings"]
        if f["kind"] == "divergent_translation" and f.get("source_term") == "サンプル王国"
    ]
    assert not kingdom_divergent


def test_audit_is_reproducible(runs_dir):
    terms = _entity_terms(locked_kingdom=True)
    index = _build_fixture_index(runs_dir, terms)
    first = audit_glossary_conflicts(terms, index, generated_at="FIXED")
    second = audit_glossary_conflicts(terms, deepcopy(index), generated_at="FIXED")
    assert first == second


def test_no_body_text_in_report(runs_dir):
    terms = _entity_terms(locked_kingdom=True)
    index = _build_fixture_index(runs_dir, terms)
    report = audit_glossary_conflicts(terms, index, generated_at="FIXED")
    raw = json.dumps(report, ensure_ascii=False)
    assert "早晨" not in raw
    assert "受付" not in raw
    assert "source_text" not in raw
    assert "draft_text" not in raw


def test_term_usage_index_covers_non_entity_locked(tmp_path):
    terms = [
        GlossaryEntry(
            source_term="固定用語",
            target_term="固定译名",
            category="other",
            locked=True,
        )
    ]
    entity_index = {
        "schema_version": 1,
        "generated_at": "FIXED",
        "stats": {"entities_indexed": 0, "unlisted_candidate_count": 0},
        "entities": {},
        "conflicts": [],
        "unlisted_high_freq": [],
    }
    term_usage_index = {
        "schema_version": 1,
        "generated_at": "FIXED",
        "terms": {
            "固定用語": {
                "source_hits": 3,
                "divergent": 1,
                "divergent_segment_ids": ["ch-010-seg-001"],
                "mappings": {"固定译名": {"count": 2}, "错误译名": {"count": 1}},
            }
        },
    }
    report = audit_glossary_conflicts(
        terms,
        entity_index,
        term_usage_index=term_usage_index,
        generated_at="FIXED",
    )
    locked = [f for f in report["findings"] if f["kind"] == "locked_violation"]
    assert len(locked) == 1
    assert locked[0]["segment_ids"] == ["ch-010-seg-001"]
    assert locked[0]["chapters"] == ["ch-010"]


def test_cli_json(tmp_path, runs_dir, capsys):
    cli = _load_script()
    glossary = tmp_path / "glossary.yaml"
    from glossary import GlossaryStore

    store = GlossaryStore(glossary)
    for t in _entity_terms():
        store.add(t)

    entity_out = tmp_path / "indexes" / "entity_index.json"
    entity_out.parent.mkdir(parents=True, exist_ok=True)
    index = _build_fixture_index(runs_dir, _entity_terms())
    entity_out.write_text(json.dumps(index, ensure_ascii=False), encoding="utf-8")

    audit_out = tmp_path / "audit" / "glossary_conflict_audit.json"
    code = cli.main(
        [
            "--glossary",
            str(glossary),
            "--entity-index",
            str(entity_out),
            "--output",
            str(audit_out),
            "--skip-term-usage-index",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "PASS"
    assert payload["findings_total"] >= 1
    assert audit_out.is_file()


def test_cli_missing_entity_index_exit_2(tmp_path, capsys):
    cli = _load_script()
    glossary = tmp_path / "glossary.yaml"
    from glossary import GlossaryStore

    GlossaryStore(glossary).add(
        GlossaryEntry(source_term="x", target_term="y", category="other")
    )
    code = cli.main(
        [
            "--glossary",
            str(glossary),
            "--entity-index",
            str(tmp_path / "missing.json"),
            "--skip-term-usage-index",
            "--json",
        ]
    )
    capsys.readouterr()
    assert code == 2
