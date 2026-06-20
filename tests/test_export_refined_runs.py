"""Tests for staged export of refined runs."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_exporter():
    spec = importlib.util.spec_from_file_location(
        "export_refined_runs_test",
        REPO_ROOT / "scripts" / "export_refined_runs.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def _make_run(tmp_path: Path, run_id: str, offset: int, chapters: list[dict]) -> None:
    run_root = tmp_path / "workspace" / "runs" / run_id
    run_root.mkdir(parents=True)
    (run_root / "run_metadata.json").write_text(
        json.dumps({"run_id": run_id, "chapter_offset": offset}),
        encoding="utf-8",
    )
    (run_root / "segments.json").write_text(
        json.dumps({"chapters": chapters}),
        encoding="utf-8",
    )


def test_export_up_to_offset_fixture(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOW_LEGACY_REFINEMENT", "1")
    exp = _load_exporter()
    _make_run(
        tmp_path,
        "run_001_draft_stage_b_50ch",
        0,
        [
            {
                "chapter_id": "ch-001",
                "chapter_label": "第一章",
                "segments": [
                    {"segment_id": "s1", "draft_text": "d1", "refined_text": "r1"},
                ],
            }
        ],
    )
    _make_run(
        tmp_path,
        "run_002_draft_stage_b_50ch",
        50,
        [
            {
                "chapter_id": "ch-051",
                "chapter_label": "第五十一",
                "segments": [
                    {"segment_id": "s2", "draft_text": "d2", "refined_text": "r2"},
                ],
            }
        ],
    )

    out_dir = tmp_path / "fixture_export"
    summary = exp.export_all(
        tmp_path,
        require_refined=True,
        up_to_offset=0,
        output_root=out_dir,
    )
    assert summary["chapters_exported"] == 1
    assert (out_dir / "translated" / "chapter_001_cn.md").is_file()
    assert not (out_dir / "translated" / "chapter_051_cn.md").is_file()


def test_export_skips_failed_segments(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOW_LEGACY_REFINEMENT", "1")
    exp = _load_exporter()
    _make_run(
        tmp_path,
        "run_001_draft_stage_b_50ch",
        0,
        [
            {
                "chapter_id": "ch-001",
                "chapter_label": "第一章",
                "segments": [
                    {"segment_id": "s1", "draft_text": "d1", "refined_text": "r1", "status": "failed"},
                ],
            }
        ],
    )
    out_dir = tmp_path / "fixture_export"
    summary = exp.export_all(tmp_path, require_refined=True, output_root=out_dir)
    assert summary["chapters_exported"] == 0
    assert summary["chapters_incomplete"] == 1


def test_export_idempotent_preserves_human_edited(tmp_path, monkeypatch):
    monkeypatch.setenv("ALLOW_LEGACY_REFINEMENT", "1")
    exp = _load_exporter()
    _make_run(
        tmp_path,
        "run_001_draft_stage_b_50ch",
        0,
        [
            {
                "chapter_id": "ch-001",
                "chapter_label": "第一章",
                "segments": [
                    {"segment_id": "s1", "draft_text": "d1", "refined_text": "r1"},
                ],
            }
        ],
    )
    out_dir = tmp_path / "fixture_export"
    zh_path = out_dir / "translated" / "chapter_001_cn.md"
    zh_path.parent.mkdir(parents=True)
    zh_path.write_text("# 第一章\n\n<!-- human-edited -->\n手工译文\n", encoding="utf-8")

    summary = exp.export_all(tmp_path, require_refined=True, output_root=out_dir, overwrite=False)
    assert summary["chapters_skipped_human_edited"] == 1
    assert "human-edited" in zh_path.read_text(encoding="utf-8")
