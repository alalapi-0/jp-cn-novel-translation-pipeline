"""Tests for FS-012: scripts/migrate_assets_to_configs.py.

Acceptance (docs/final_state_round_task_list.md FS-012):
- dry-run report lists entry count / conflict count / dropped fields = 0;
- after real run the glossary loader reads back all migrated entries;
- source asset files are never modified or deleted.

All fixtures use fictional sample terms only.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "migrate_assets_to_configs.py"


def _load_module():
    mod_name = "light_novel_migrate_assets_test"
    spec = importlib.util.spec_from_file_location(mod_name, SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def migrator():
    return _load_module()


def _write_asset(path: Path, candidates: list[dict]) -> None:
    payload = {
        "schema_version": 1,
        "asset_kind": "translation_memory",
        "approved_pairs": [{"source": "サンプル原文", "target": "示例译文"}],
        "segment_map": [],
        "term_candidates": candidates,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


@pytest.fixture()
def assets_dir(tmp_path):
    d = tmp_path / "assets"
    d.mkdir()
    _write_asset(
        d / "a.json",
        [
            {"source": "サンプル王国", "target": "示例王国", "kind": "bracket_label", "evidence_segment_id": "seg-1"},
            {"source": "サンプルギルド", "target": "示例公会", "kind": "bracket_label", "evidence_segment_id": "seg-2"},
        ],
    )
    _write_asset(
        d / "b.json",
        [
            # duplicate: same source + same target
            {"source": "サンプル王国", "target": "示例王国", "kind": "bracket_label", "evidence_segment_id": "seg-3"},
            # conflict: same source + different target
            {"source": "サンプルギルド", "target": "示例行会", "kind": "bracket_label", "evidence_segment_id": "seg-4"},
            # malformed candidate without source -> ignored
            {"target": "孤儿目标", "kind": "bracket_label"},
        ],
    )
    return d


def test_dry_run_stats_and_no_write(migrator, assets_dir, tmp_path):
    out = tmp_path / "out"
    summary = migrator.migrate(assets_dir=assets_dir, output_dir=out, dry_run=True, write_report=False)
    assert summary["status"] == "PASS"
    assert summary["candidates_total"] == 4  # malformed one filtered out
    assert summary["entries_migrated"] == 2
    assert summary["duplicates_merged"] == 1
    assert summary["conflicts"] == 1
    assert summary["dropped_fields"] == 0
    assert not out.exists(), "dry-run must not write output"


def test_real_run_writes_and_verifies(migrator, assets_dir, tmp_path):
    out = tmp_path / "out"
    summary = migrator.migrate(assets_dir=assets_dir, output_dir=out, dry_run=False, write_report=False)
    assert summary["status"] == "PASS"
    assert summary["verified"] is True
    glossary = yaml.safe_load((out / "glossary.yaml").read_text(encoding="utf-8"))
    assert len(glossary["entries"]) == summary["entries_migrated"] == 2
    chars = yaml.safe_load((out / "character_profile.yaml").read_text(encoding="utf-8"))
    assert chars["characters"] == []


def test_conflict_keeps_first_target_and_records_note(migrator, assets_dir, tmp_path):
    out = tmp_path / "out"
    migrator.migrate(assets_dir=assets_dir, output_dir=out, dry_run=False, write_report=False)
    glossary = yaml.safe_load((out / "glossary.yaml").read_text(encoding="utf-8"))
    guild = next(e for e in glossary["entries"] if e["source_term"] == "サンプルギルド")
    assert guild["target_term"] == "示例公会"  # first seen wins
    assert guild["notes"] and "示例行会" in guild["notes"]  # loser recorded


def test_no_field_dropped_evidence_in_description(migrator, assets_dir, tmp_path):
    out = tmp_path / "out"
    migrator.migrate(assets_dir=assets_dir, output_dir=out, dry_run=False, write_report=False)
    glossary = yaml.safe_load((out / "glossary.yaml").read_text(encoding="utf-8"))
    for entry in glossary["entries"]:
        assert "kind=" in entry["description"]
        assert "evidence=" in entry["description"]


def test_sources_never_modified(migrator, assets_dir, tmp_path):
    before = {p.name: p.read_bytes() for p in assets_dir.glob("*.json")}
    migrator.migrate(assets_dir=assets_dir, output_dir=tmp_path / "out", dry_run=False, write_report=False)
    after = {p.name: p.read_bytes() for p in assets_dir.glob("*.json")}
    assert before == after


def test_migrated_glossary_passes_schema(migrator, assets_dir, tmp_path):
    import jsonschema

    out = tmp_path / "out"
    migrator.migrate(assets_dir=assets_dir, output_dir=out, dry_run=False, write_report=False)
    schema = json.loads((REPO_ROOT / "schemas" / "glossary.schema.json").read_text(encoding="utf-8"))
    data = yaml.safe_load((out / "glossary.yaml").read_text(encoding="utf-8"))
    jsonschema.Draft7Validator(schema).validate(data)


def test_missing_assets_dir_exit_2(migrator, tmp_path):
    code = migrator.main(["--assets-dir", str(tmp_path / "nope"), "--dry-run", "--no-report", "--json"])
    assert code == 2


def test_cli_dry_run_on_real_assets(migrator, capsys):
    """Real workspace assets present in this repo: dry-run must PASS with 0 dropped fields."""
    if not (REPO_ROOT / "workspace" / "assets" / "translation_memory").is_dir():
        pytest.skip("real assets not present")
    code = migrator.main(["--dry-run", "--no-report", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["dropped_fields"] == 0
    assert payload["entries_migrated"] <= payload["candidates_total"]


def test_validate_configs_allow_missing(tmp_path):
    """--allow-missing skips absent files in real-data dirs (FS-012 companion)."""
    mod_name = "light_novel_validate_configs_fs012"
    spec = importlib.util.spec_from_file_location(mod_name, REPO_ROOT / "scripts" / "validate_configs.py")
    assert spec and spec.loader
    vc = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = vc
    spec.loader.exec_module(vc)

    only_glossary = tmp_path / "partial"
    only_glossary.mkdir()
    src = (REPO_ROOT / "configs" / "glossary.yaml").read_text(encoding="utf-8")
    (only_glossary / "glossary.yaml").write_text(src, encoding="utf-8")

    strict = vc.validate_all(only_glossary)
    assert strict["status"] == "FAIL"
    lenient = vc.validate_all(only_glossary, allow_missing=True)
    assert lenient["status"] == "PASS"
    skipped = [r for r in lenient["results"] if r.get("skipped")]
    assert len(skipped) == 4
