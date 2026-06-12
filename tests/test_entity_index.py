"""Tests for FS-033: entity index builder.

Acceptance (docs/final_state_round_task_list.md FS-033):
- same-source multi-translation / same-target multi-source detectable on fixtures;
- top-N unlisted high-frequency terms generated;
- incremental update reuses unchanged files;
- output under workspace/indexes/ (gitignored); no body text in index.
"""

from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from glossary import GlossaryEntry  # noqa: E402
from consistency.entity_index import (  # noqa: E402
    build_entity_index,
    filter_entity_terms,
    infer_target_variant,
    rank_unlisted_high_freq,
    scan_entity_file,
)

SCRIPT = REPO_ROOT / "scripts" / "build_entity_index.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("light_novel_entity_index_cli", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["light_novel_entity_index_cli"] = mod
    spec.loader.exec_module(mod)
    return mod


def _terms() -> list[GlossaryEntry]:
    return [
        GlossaryEntry(source_term="サンプル王国", target_term="示例王国", category="place_name"),
        GlossaryEntry(source_term="サンプルギルド", target_term="示例公会", category="organization_name"),
        GlossaryEntry(source_term="サンプル組合", target_term="示例公会", category="organization_name"),
        GlossaryEntry(source_term="サンプルスキル", target_term="", category="skill_name"),
        GlossaryEntry(source_term="ignored_system", target_term="忽略", category="system_term"),
    ]


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


def test_filter_entity_terms_excludes_non_entity_categories():
    filtered = filter_entity_terms(_terms())
    categories = {t.category for t in filtered}
    assert "system_term" not in categories
    assert "place_name" in categories


def test_scan_entity_mappings_and_unlisted(runs_dir):
    path = runs_dir / "run_a" / "segments.json"
    scan = scan_entity_file(path, filter_entity_terms(_terms()), all_terms=_terms())
    kingdom = scan["entities"]["サンプル王国"]
    assert kingdom["source_hits"] == 2
    assert kingdom["mappings"]["示例王国"]["count"] == 2
    guild = scan["entities"]["サンプルギルド"]
    assert guild["divergent"] == 1
    assert guild["mappings"]["另译公会"]["count"] == 1
    assert "アルファ団" in scan["unlisted"]
    assert scan["unlisted"]["アルファ団"]["source_hits"] >= 2


def test_infer_target_variant_prefers_longest_cjk():
    assert infer_target_variant(
        "サンプル王国の夜",
        "示例皇国的夜晚",
        source_term="サンプル王国",
        canonical_target="示例王国",
    ) == "示例皇国"


def test_conflicts_match_fixture_expectations(runs_dir):
    files = sorted(runs_dir.glob("run_*/segments.json"))
    index = build_entity_index(_terms(), files, all_terms=_terms())
    conflicts = index["conflicts"]
    kinds = {(c["kind"], c.get("source_term") or c.get("target_term")) for c in conflicts}
    assert ("divergent_translation", "サンプル王国") in kinds
    assert ("divergent_translation", "サンプルギルド") in kinds
    assert ("shared_target", "示例公会") in kinds

    kingdom = index["entities"]["サンプル王国"]
    assert kingdom["mappings"]["示例王国"]["count"] == 2
    assert kingdom["mappings"]["示例皇国"]["count"] == 2


def test_unlisted_high_freq_top_n(runs_dir):
    files = sorted(runs_dir.glob("run_*/segments.json"))
    index = build_entity_index(_terms(), files, all_terms=_terms(), top_n_unlisted=5)
    unlisted = index["unlisted_high_freq"]
    assert unlisted
    assert unlisted[0]["source_term"] == "アルファ団"
    assert unlisted[0]["source_hits"] >= 3
    assert "阿尔法团" in unlisted[0]["inferred_targets"]


def test_rank_unlisted_respects_min_hits():
    ranked = rank_unlisted_high_freq(
        {
            "once": {"source_hits": 1, "chapters": {"ch-001": 1}, "inferred_targets": {}, "sample_segment_ids": []},
            "twice": {"source_hits": 2, "chapters": {"ch-001": 2}, "inferred_targets": {}, "sample_segment_ids": []},
        },
        top_n=10,
        min_hits=2,
    )
    assert len(ranked) == 1
    assert ranked[0]["source_term"] == "twice"


def test_no_text_leaks_into_index(runs_dir):
    files = sorted(runs_dir.glob("run_*/segments.json"))
    index = build_entity_index(_terms(), files, all_terms=_terms())
    raw = json.dumps(index, ensure_ascii=False)
    assert "早晨" not in raw
    assert "受付" not in raw
    assert "source_text" not in raw
    assert "draft_text" not in raw


def test_incremental_reuses_unchanged_files(runs_dir):
    files = sorted(runs_dir.glob("run_*/segments.json"))
    first = build_entity_index(_terms(), files, all_terms=_terms())
    assert first["stats"]["files_scanned"] == 2
    assert first["stats"]["files_reused"] == 0

    second = build_entity_index(_terms(), files, previous_index=first, all_terms=_terms())
    assert second["stats"]["files_scanned"] == 0
    assert second["stats"]["files_reused"] == 2
    assert second["entities"] == first["entities"]

    target = runs_dir / "run_b" / "segments.json"
    _write_segments(
        target,
        "ch-002",
        [("ch-002-seg-001", "サンプル王国の夜", "示例王国的夜晚")],
    )
    os.utime(target, (target.stat().st_atime + 5, target.stat().st_mtime + 5))
    third = build_entity_index(_terms(), files, previous_index=second, all_terms=_terms())
    assert third["stats"]["files_scanned"] == 1
    assert third["stats"]["files_reused"] == 1
    assert third["entities"]["サンプル王国"]["divergent"] == 0


def test_by_category_grouping(runs_dir):
    files = sorted(runs_dir.glob("run_*/segments.json"))
    index = build_entity_index(_terms(), files, all_terms=_terms())
    assert "サンプル王国" in index["by_category"]["place_name"]
    assert "サンプルギルド" in index["by_category"]["organization_name"]


def test_cli_json_and_incremental(runs_dir, tmp_path, capsys):
    cli = _load_script()
    glossary = tmp_path / "glossary.yaml"
    from glossary import GlossaryStore

    store = GlossaryStore(glossary)
    for t in _terms():
        store.add(t)
    out = tmp_path / "indexes" / "entity_index.json"

    code = cli.main(
        [
            "--glossary",
            str(glossary),
            "--output",
            str(out),
            "--runs-dir",
            str(runs_dir),
            "--chapter-range",
            "1-50",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "PASS"
    assert payload["files_scanned"] == 2
    assert out.is_file()

    code = cli.main(
        [
            "--glossary",
            str(glossary),
            "--output",
            str(out),
            "--runs-dir",
            str(runs_dir),
            "--chapter-range",
            "1-50",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["files_reused"] == 2


def test_cli_missing_glossary_exit_2(tmp_path, capsys):
    cli = _load_script()
    code = cli.main(["--glossary", str(tmp_path / "nope.yaml"), "--json"])
    capsys.readouterr()
    assert code == 2


def test_workspace_indexes_gitignored():
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "workspace/indexes/" in gitignore
