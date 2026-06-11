"""Tests for FS-015: term usage index + conflict marking.

Acceptance (docs/final_state_round_task_list.md FS-015):
- index supports incremental update (unchanged files reused);
- conflict statistics match fixture expectations;
- output goes to workspace/indexes/ (gitignored - asserted here).

Fixtures use fictional sample terms only; outputs carry segment_ids and
counts, never text (asserted).
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
from glossary.usage_index import (  # noqa: E402
    build_usage_index,
    detect_conflicts,
    scan_segments_file,
)

SCRIPT = REPO_ROOT / "scripts" / "build_term_usage_index.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("light_novel_usage_index_cli", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["light_novel_usage_index_cli"] = mod
    spec.loader.exec_module(mod)
    return mod


def _terms() -> list[GlossaryEntry]:
    return [
        GlossaryEntry(source_term="サンプル王国", target_term="示例王国", category="place_name"),
        GlossaryEntry(source_term="サンプルギルド", target_term="示例公会", category="organization_name"),
        # shared target with ギルド on purpose (同译多源)
        GlossaryEntry(source_term="サンプル組合", target_term="示例公会", category="organization_name"),
        # no target yet -> never divergent-flagged
        GlossaryEntry(source_term="サンプルスキル", target_term="", category="skill_name"),
    ]


def _write_segments(path: Path, chapter_id: str, rows: list[tuple[str, str, str]]) -> None:
    """rows: [(segment_id, source_text, draft_text)]"""
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
    # ch-001: kingdom translated consistently twice; guild divergent once of two
    _write_segments(
        base / "run_a" / "segments.json",
        "ch-001",
        [
            ("ch-001-seg-001", "サンプル王国の朝", "示例王国的早晨"),
            ("ch-001-seg-002", "サンプル王国とサンプルギルド", "示例王国与示例公会"),
            ("ch-001-seg-003", "サンプルギルドの受付", "另译公会的前台"),  # divergent
        ],
    )
    # ch-002: kingdom divergent in both segments (ratio 1.0)
    _write_segments(
        base / "run_b" / "segments.json",
        "ch-002",
        [
            ("ch-002-seg-001", "サンプル王国の夜", "示例皇国的夜晚"),  # divergent
            ("ch-002-seg-002", "サンプル王国の城", "示例皇国的城"),  # divergent
        ],
    )
    return base


# ---------------------------------------------------------------------------
# scan + stats
# ---------------------------------------------------------------------------


def test_scan_counts_hits_and_divergence(runs_dir):
    bucket = scan_segments_file(runs_dir / "run_a" / "segments.json", _terms())
    kingdom = bucket["サンプル王国"]
    assert kingdom["source_hits"] == 2
    assert kingdom["target_hits"] == 2
    assert kingdom["co_hits"] == 2
    assert kingdom["divergent"] == 0
    guild = bucket["サンプルギルド"]
    assert guild["source_hits"] == 2
    assert guild["co_hits"] == 1
    assert guild["divergent"] == 1
    assert guild["divergent_segment_ids"] == ["ch-001-seg-003"]


def test_scan_chapter_range_filter(runs_dir):
    files = sorted(runs_dir.glob("run_*/segments.json"))
    full = build_usage_index(_terms(), files)
    assert full["stats"]["chapters_covered"] == 2
    only1 = build_usage_index(_terms(), files, chapter_min=1, chapter_max=1)
    assert only1["stats"]["chapters_covered"] == 1
    assert "ch-002" not in only1["terms"]["サンプル王国"]["chapters"]


def test_no_text_leaks_into_index(runs_dir):
    files = sorted(runs_dir.glob("run_*/segments.json"))
    index = build_usage_index(_terms(), files)
    raw = json.dumps(index, ensure_ascii=False)
    assert "早晨" not in raw and "受付" not in raw  # no draft/source text


# ---------------------------------------------------------------------------
# conflicts
# ---------------------------------------------------------------------------


def test_conflicts_match_fixture_expectations(runs_dir):
    files = sorted(runs_dir.glob("run_*/segments.json"))
    index = build_usage_index(_terms(), files)
    conflicts = index["conflicts"]
    kinds = {(c["kind"], c.get("source_term") or c.get("target_term")) for c in conflicts}

    # 同源多译: kingdom 2/4 divergent (ratio .5) and guild 1/2 (ratio .5)
    assert ("divergent_translation", "サンプル王国") in kinds
    assert ("divergent_translation", "サンプルギルド") in kinds
    # 同译多源: 示例公会 shared by two source terms
    assert ("shared_target", "示例公会") in kinds

    kingdom = next(c for c in conflicts if c.get("source_term") == "サンプル王国")
    assert kingdom["source_hits"] == 4
    assert kingdom["divergent"] == 2
    assert kingdom["ratio"] == 0.5
    shared = next(c for c in conflicts if c["kind"] == "shared_target")
    assert shared["source_terms"] == ["サンプルギルド", "サンプル組合"]


def test_divergent_requires_min_hits_and_target():
    terms = _terms()
    merged = {
        "サンプル王国": {
            "source_hits": 1,
            "target_hits": 0,
            "co_hits": 0,
            "divergent": 1,
            "chapters": {},
            "divergent_segment_ids": ["ch-001-seg-001"],
        }
    }
    # below min_source_hits=2 -> no divergent conflict
    conflicts = detect_conflicts(terms, merged)
    assert all(c["kind"] != "divergent_translation" for c in conflicts)


# ---------------------------------------------------------------------------
# incremental update
# ---------------------------------------------------------------------------


def test_incremental_reuses_unchanged_files(runs_dir):
    files = sorted(runs_dir.glob("run_*/segments.json"))
    first = build_usage_index(_terms(), files)
    assert first["stats"]["files_scanned"] == 2
    assert first["stats"]["files_reused"] == 0

    second = build_usage_index(_terms(), files, previous_index=first)
    assert second["stats"]["files_scanned"] == 0
    assert second["stats"]["files_reused"] == 2
    assert second["terms"] == first["terms"]

    # touch one file with changed content -> only that file re-scanned
    target = runs_dir / "run_b" / "segments.json"
    _write_segments(
        target,
        "ch-002",
        [("ch-002-seg-001", "サンプル王国の夜", "示例王国的夜晚")],  # now consistent
    )
    os.utime(target, (target.stat().st_atime + 5, target.stat().st_mtime + 5))
    third = build_usage_index(_terms(), files, previous_index=second)
    assert third["stats"]["files_scanned"] == 1
    assert third["stats"]["files_reused"] == 1
    assert third["terms"]["サンプル王国"]["divergent"] == 0  # fixed upstream


def test_chapter_dedupe_newest_file_wins(runs_dir, tmp_path):
    files = sorted(runs_dir.glob("run_*/segments.json"))
    # a newer run re-translates ch-002 consistently
    newer = runs_dir / "run_c" / "segments.json"
    _write_segments(
        newer,
        "ch-002",
        [("ch-002-seg-001", "サンプル王国の夜", "示例王国的夜晚")],
    )
    old_b = runs_dir / "run_b" / "segments.json"
    os.utime(newer, (old_b.stat().st_atime + 100, old_b.stat().st_mtime + 100))

    index = build_usage_index(_terms(), files + [newer])
    kingdom = index["terms"]["サンプル王国"]
    # ch-002 owned by run_c: 1 co_hit, 0 divergent (run_b superseded)
    assert kingdom["chapters"]["ch-002"] == {
        "source_hits": 1,
        "target_hits": 1,
        "co_hits": 1,
        "divergent": 0,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_json_and_incremental(runs_dir, tmp_path, capsys):
    cli = _load_script()
    glossary = tmp_path / "glossary.yaml"
    from glossary import GlossaryStore

    store = GlossaryStore(glossary)
    for t in _terms():
        store.add(t)
    out = tmp_path / "indexes" / "term_usage_index.json"

    code = cli.main(
        [
            "--glossary", str(glossary),
            "--output", str(out),
            "--runs-dir", str(runs_dir),
            "--chapter-range", "1-50",
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
            "--glossary", str(glossary),
            "--output", str(out),
            "--runs-dir", str(runs_dir),
            "--chapter-range", "1-50",
            "--json",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["files_reused"] == 2  # incremental on second run


def test_cli_missing_glossary_exit_2(tmp_path, capsys):
    cli = _load_script()
    code = cli.main(["--glossary", str(tmp_path / "nope.yaml"), "--json"])
    capsys.readouterr()
    assert code == 2


def test_workspace_indexes_gitignored():
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "workspace/indexes/" in gitignore
