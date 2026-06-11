"""Tests for FS-014: glossary import/export (CSV / YAML / JSON).

Acceptance (docs/final_state_round_task_list.md FS-014):
- three-format roundtrip (export -> import -> compare lossless) passes;
- on import conflict, locked terms stay unchanged and are counted in the
  conflict report;
- import never silently overwrites approved_by_user terms.

Fixtures use fictional sample terms only.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from glossary import (  # noqa: E402
    GlossaryIOError,
    GlossaryStore,
    detect_format,
    export_glossary,
    import_glossary,
    read_entries,
)

FORMATS = ("csv", "yaml", "json")


@pytest.fixture()
def seeded(tmp_path) -> GlossaryStore:
    store = GlossaryStore(tmp_path / "glossary.yaml")
    store.add(
        {
            "source_term": "サンプル王国",
            "target_term": "示例王国",
            "reading": "サンプルおうこく",
            "category": "place_name",
            "description": "虚构示例",
            "first_seen_chapter": 1,
            "confidence": 0.95,
            "aliases": ["サンプル国", "S国"],
            "notes": "备注",
        }
    )
    store.add(
        {
            "source_term": "サンプル・タロウ",
            "target_term": "示例太郎",
            "category": "person_name",
            # nullable fields stay None on purpose (roundtrip check)
        }
    )
    store.add(
        {
            "source_term": "サンプルスキル",
            "target_term": "",
            "category": "skill_name",
            "confidence": 0.5,
        }
    )
    return store


def _comparable(store: GlossaryStore) -> list[dict]:
    return [e.to_dict() for e in sorted(store.entries(), key=lambda e: e.source_term)]


# ---------------------------------------------------------------------------
# roundtrip
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("fmt", FORMATS)
def test_roundtrip_lossless(seeded: GlossaryStore, tmp_path, fmt):
    out = tmp_path / f"export.{fmt}"
    count = export_glossary(seeded, out)
    assert count == 3

    target = GlossaryStore(tmp_path / f"reimport_{fmt}.yaml")
    report = import_glossary(target, out)
    assert report.total == 3
    assert report.added == 3
    assert report.conflict_count == 0
    assert _comparable(target) == _comparable(seeded)


@pytest.mark.parametrize("fmt", FORMATS)
def test_reimport_into_same_store_is_noop(seeded: GlossaryStore, tmp_path, fmt):
    out = tmp_path / f"export.{fmt}"
    export_glossary(seeded, out)
    report = import_glossary(seeded, out)
    assert report.added == 0 and report.updated == 0
    assert report.unchanged == 3


def test_roundtrip_preserves_state_flags(seeded: GlossaryStore, tmp_path):
    seeded.lock("サンプル・タロウ")
    seeded.approve("サンプル王国")
    seeded.mark_conflict("サンプルスキル")
    out = tmp_path / "export.csv"
    export_glossary(seeded, out)
    target = GlossaryStore(tmp_path / "reimport.yaml")
    import_glossary(target, out)
    assert target.get("サンプル・タロウ").locked is True
    assert target.get("サンプル王国").approved_by_user is True
    assert target.get("サンプルスキル").conflict is True


# ---------------------------------------------------------------------------
# import merge behavior
# ---------------------------------------------------------------------------


def test_import_reports_added_and_updated(seeded: GlossaryStore, tmp_path):
    out = tmp_path / "delta.yaml"
    other = GlossaryStore(tmp_path / "other.yaml")
    other.add({"source_term": "サンプル王国", "target_term": "示例王国v2", "category": "place_name"})
    other.add({"source_term": "サンプル新顔", "target_term": "示例新人", "category": "person_name"})
    export_glossary(other, out)

    report = import_glossary(seeded, out)
    assert report.added == 1  # 新顔
    assert report.updated == 1  # 王国 target changed
    assert seeded.get("サンプル王国").target_term == "示例王国v2"


def test_import_conflict_keeps_locked_and_reports(seeded: GlossaryStore, tmp_path):
    seeded.lock("サンプル王国")
    out = tmp_path / "delta.json"
    other = GlossaryStore(tmp_path / "other.yaml")
    other.add({"source_term": "サンプル王国", "target_term": "入侵译名", "category": "place_name"})
    export_glossary(other, out)

    report = import_glossary(seeded, out)
    assert report.skipped_locked == 1
    assert report.conflict_count == 1
    conflict = report.conflicts[0]
    assert conflict["reason"] == "locked"
    assert conflict["kept_target"] == "示例王国"
    assert seeded.get("サンプル王国").target_term == "示例王国"  # unchanged


def test_import_never_silently_overwrites_approved(seeded: GlossaryStore, tmp_path):
    seeded.approve("サンプル・タロウ")
    out = tmp_path / "delta.csv"
    other = GlossaryStore(tmp_path / "other.yaml")
    other.add({"source_term": "サンプル・タロウ", "target_term": "机器太郎", "category": "person_name"})
    export_glossary(other, out)

    report = import_glossary(seeded, out)
    assert report.skipped_approved == 1
    assert report.conflict_count == 1
    assert report.conflicts[0]["reason"] == "approved_by_user"
    assert seeded.get("サンプル・タロウ").target_term == "示例太郎"


def test_import_identical_approved_counts_unchanged(seeded: GlossaryStore, tmp_path):
    seeded.approve("サンプル・タロウ")
    out = tmp_path / "same.yaml"
    export_glossary(seeded, out)
    report = import_glossary(seeded, out)
    assert report.skipped_approved == 0
    assert report.unchanged == 3


# ---------------------------------------------------------------------------
# format handling
# ---------------------------------------------------------------------------


def test_detect_format_variants(tmp_path):
    assert detect_format("a.csv") == "csv"
    assert detect_format("a.yaml") == "yaml"
    assert detect_format("a.yml") == "yaml"
    assert detect_format("a.json") == "json"
    with pytest.raises(GlossaryIOError):
        detect_format("a.xlsx")


def test_read_entries_missing_file(tmp_path):
    with pytest.raises(GlossaryIOError):
        read_entries(tmp_path / "nope.yaml")


def test_csv_nullable_roundtrip(seeded: GlossaryStore, tmp_path):
    """None fields survive CSV roundtrip as None (not '')."""
    out = tmp_path / "export.csv"
    export_glossary(seeded, out)
    entries = {e.source_term: e for e in read_entries(out)}
    taro = entries["サンプル・タロウ"]
    assert taro.reading is None
    assert taro.description is None
    assert taro.first_seen_chapter is None
    assert taro.confidence is None
    assert taro.notes is None
    kingdom = entries["サンプル王国"]
    assert kingdom.first_seen_chapter == 1
    assert kingdom.confidence == 0.95
    assert kingdom.aliases == ["サンプル国", "S国"]


def test_export_report_counts(seeded: GlossaryStore, tmp_path):
    seeded.delete("サンプルスキル")  # soft delete
    assert export_glossary(seeded, tmp_path / "a.yaml") == 2
    assert export_glossary(seeded, tmp_path / "b.yaml", include_deleted=True) == 3
