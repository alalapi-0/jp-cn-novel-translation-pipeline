"""Tests for scripts/vector_db_inspect.py (mock JSON index)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "vector_db_inspect.py"
EXAMPLE_INDEX = REPO_ROOT / "data" / "examples" / "vector_index_mock.example.json"
EXAMPLE_MANIFEST = REPO_ROOT / "data" / "examples" / "vector_source_manifest.example.json"


def _load():
    name = "vector_db_inspect_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def inspect_mod():
    return _load()


def test_missing_index_soft_warning(inspect_mod, tmp_path):
    missing = tmp_path / "index.json"
    report, _, _ = inspect_mod.run_inspection(missing, None)
    code = inspect_mod.aggregate_exit_code(report.findings)
    assert code == 1
    assert any(f.code == "index_missing" for f in report.findings)


def test_empty_vectors_warning(inspect_mod, tmp_path):
    index_path = tmp_path / "index.json"
    index_path.write_text(
        json.dumps(
            {
                "index_metadata": {
                    "schema_version": "1.0.0",
                    "backend": "json_mock",
                    "project_id": "p1",
                    "language_direction": "jp_to_cn",
                    "embedding_model": "mock-384",
                    "embedding_dimension": 384,
                },
                "vectors": [],
            }
        ),
        encoding="utf-8",
    )
    report, _, _ = inspect_mod.run_inspection(index_path, None)
    assert report.vector_count == 0
    assert inspect_mod.aggregate_exit_code(report.findings) == 1
    assert any(f.code == "index_empty" for f in report.findings)


def test_example_index_detects_missing_metadata_and_orphans(inspect_mod):
    index_data, err = inspect_mod.load_json_file(EXAMPLE_INDEX)
    assert err is None
    manifest_data, err = inspect_mod.load_json_file(EXAMPLE_MANIFEST)
    assert err is None
    report = inspect_mod.inspect_index(
        index_data,
        index_path=EXAMPLE_INDEX,
        manifest_data=manifest_data,
        manifest_path=EXAMPLE_MANIFEST,
    )
    code = inspect_mod.aggregate_exit_code(report.findings)
    assert code == 1
    assert report.vector_count == 4
    assert report.missing_metadata_counts.get("model", 0) >= 1
    assert "emb-orphan-seg999" in report.orphan_vectors
    assert any(f.code == "metadata_field_missing" for f in report.findings)


def test_invalid_json_blocked(inspect_mod, tmp_path):
    bad = tmp_path / "index.json"
    bad.write_text("{not-json", encoding="utf-8")
    report, _, _ = inspect_mod.run_inspection(bad, None)
    assert inspect_mod.aggregate_exit_code(report.findings) == 2


def test_main_example_json_exit_warning(inspect_mod):
    code = inspect_mod.main(["--example", "--json"])
    assert code == 1


def test_clean_index_passes(inspect_mod, tmp_path):
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "project_id": "p1",
                "segments": [{"chapter_id": "ch01", "segment_id": "seg001"}],
            }
        ),
        encoding="utf-8",
    )
    index_path = tmp_path / "index.json"
    index_path.write_text(
        json.dumps(
            {
                "index_metadata": {
                    "schema_version": "1.0.0",
                    "backend": "json_mock",
                    "project_id": "p1",
                    "language_direction": "jp_to_cn",
                    "embedding_model": "mock-384",
                    "embedding_dimension": 384,
                },
                "vectors": [
                    {
                        "embedding_id": "emb-1",
                        "metadata": {
                            "project_id": "p1",
                            "language_direction": "jp_to_cn",
                            "chapter_id": "ch01",
                            "segment_id": "seg001",
                            "model": "mock-384",
                            "version": "1",
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    report, _, _ = inspect_mod.run_inspection(index_path, manifest_path)
    assert inspect_mod.aggregate_exit_code(report.findings) == 0
    assert report.orphan_vectors == []
