"""Tests for FS-032: segment index builder.

Acceptance:
- missing / misalignment detection 100% recall on constructed fixtures;
- streaming build (metadata only, no body text in index);
- incremental rebuild reuses unchanged segment files;
- output path under workspace/indexes/ (gitignored).
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from consistency.segment_index import (  # noqa: E402
    build_segment_index,
    index_summary,
    iter_chapter_scans,
    parse_segment_id,
    scan_segments_file,
)

SCRIPT = REPO_ROOT / "scripts" / "build_segment_index.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("light_novel_segment_index_cli", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["light_novel_segment_index_cli"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_completed_run(
    repo: Path,
    run_id: str,
    chapters: list[tuple[int, list[tuple[str, str, str]]]],
) -> Path:
    """chapters: [(num, [(segment_id, source, draft), ...]), ...]"""
    root = repo / "workspace" / "runs" / run_id
    root.mkdir(parents=True, exist_ok=True)
    meta = {
        "run_id": run_id,
        "phase": "draft",
        "chapter_files": [f"input_jp/{num:03d}-sample.md" for num, _ in chapters],
    }
    (root / "run_metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    seg_doc = {"chapters": []}
    total_segments = 0
    for num, segs in chapters:
        segments = []
        for sid, source, draft in segs:
            segments.append(
                {
                    "segment_id": sid,
                    "source_text": source,
                    "draft_text": draft,
                    "status": "machine_translated",
                }
            )
        total_segments += len(segments)
        seg_doc["chapters"].append(
            {
                "chapter_id": f"ch-{num:03d}",
                "chapter_label": f"第{num}话",
                "source_path": f"input_jp/{num:03d}-sample.md",
                "segments": segments,
            }
        )
    seg_path = root / "segments.json"
    seg_path.write_text(json.dumps(seg_doc, ensure_ascii=False), encoding="utf-8")
    progress = {
        "run_id": run_id,
        "status": "completed",
        "total_segments": total_segments,
        "completed_segments": total_segments,
    }
    (root / "run_progress.json").write_text(json.dumps(progress), encoding="utf-8")
    return seg_path


def _assert_no_body_text(index: dict) -> None:
    blob = json.dumps(index, ensure_ascii=False)
    assert "source_text" not in blob
    assert "draft_text" not in blob
    assert "源文" not in blob
    assert "译文" not in blob


@pytest.fixture()
def clean_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    _write_completed_run(
        repo,
        "run_clean_draft_stage_b_50ch",
        [
            (
                1,
                [
                    ("ch-001-seg-001", "源文一", "译文一"),
                    ("ch-001-seg-002", "源文二", "译文二"),
                ],
            ),
            (2, [("ch-002-seg-001", "源文", "译文")]),
        ],
    )
    return repo


def test_parse_segment_id() -> None:
    assert parse_segment_id("ch-001-seg-003") == (1, 3)
    assert parse_segment_id("ch-1-seg-2") == (1, 2)
    assert parse_segment_id("bad-id") is None


def test_scan_metadata_only(clean_repo: Path) -> None:
    seg_path = clean_repo / "workspace" / "runs" / "run_clean_draft_stage_b_50ch" / "segments.json"
    bucket = scan_segments_file(seg_path, run_id="run_clean_draft_stage_b_50ch")
    assert bucket[1]["segments"]["ch-001-seg-001"]["source_length"] == 3
    assert bucket[1]["segments"]["ch-001-seg-001"]["draft_length"] == 3
    _assert_no_body_text(bucket)


def test_clean_index_pass(clean_repo: Path) -> None:
    index = build_segment_index(clean_repo)
    _assert_no_body_text(index)
    summary = index_summary(index)
    assert summary["status"] == "PASS"
    assert summary["segments_indexed"] == 3
    assert summary["missing_segments_count"] == 0
    assert summary["misalignment_count"] == 0
    assert index["segments"]["ch-001-seg-001"]["chapter_number"] == 1


def test_missing_segment_gap_recall(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_completed_run(
        repo,
        "run_gap_draft_stage_b_50ch",
        [
            (
                5,
                [
                    ("ch-005-seg-001", "a", "A"),
                    ("ch-005-seg-003", "c", "C"),
                ],
            ),
        ],
    )
    index = build_segment_index(repo)
    missing = index["issues"]["missing_segments"]
    assert len(missing) == 1
    assert missing[0]["segment_index"] == 2
    assert missing[0]["expected_segment_id"] == "ch-005-seg-002"
    assert index["chapters"]["ch-005"]["missing_segment_ids"] == ["ch-005-seg-002"]
    assert index_summary(index)["missing_segments_count"] == 1


def test_misalignment_chapter_mismatch_recall(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_completed_run(
        repo,
        "run_misalign_draft_stage_b_50ch",
        [
            (3, [("ch-004-seg-001", "x", "X")]),
        ],
    )
    index = build_segment_index(repo)
    mis = index["issues"]["misalignments"]
    assert any(m["issue_type"] == "chapter_mismatch" for m in mis)
    assert index_summary(index)["misalignment_count"] >= 1


def test_misalignment_duplicate_and_order_recall(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_completed_run(
        repo,
        "run_dup_draft_stage_b_50ch",
        [
            (
                7,
                [
                    ("ch-007-seg-001", "a", "A"),
                    ("ch-007-seg-001", "b", "B"),
                    ("ch-007-seg-004", "c", "C"),
                ],
            ),
        ],
    )
    index = build_segment_index(repo)
    types = {m["issue_type"] for m in index["issues"]["misalignments"]}
    assert "duplicate_segment_id" in types
    assert "index_order_mismatch" in types
    missing = index["issues"]["missing_segments"]
    assert {m["segment_index"] for m in missing} == {2, 3}


def test_incremental_reuses_unchanged_files(clean_repo: Path) -> None:
    run_dirs = [clean_repo / "workspace" / "runs"]
    first = build_segment_index(clean_repo, run_dirs=run_dirs)
    assert first["stats"]["files_scanned"] >= 1
    second = build_segment_index(clean_repo, previous_index=first, run_dirs=run_dirs)
    assert second["stats"]["files_reused"] >= 1
    assert second["stats"]["files_scanned"] == 0


def test_streaming_iter_does_not_retain_text(clean_repo: Path) -> None:
    seg_path = clean_repo / "workspace" / "runs" / "run_clean_draft_stage_b_50ch" / "segments.json"
    buckets = list(iter_chapter_scans(seg_path, run_id="run_clean_draft_stage_b_50ch"))
    assert len(buckets) == 2
    for _, bucket in buckets:
        _assert_no_body_text(bucket)


def test_cli_json_and_output_path(clean_repo: Path, tmp_path: Path, capsys) -> None:
    mod = _load_script()
    out = tmp_path / "segment_index.json"
    cli_args = [
        "--repo-root",
        str(clean_repo),
        "--output",
        str(out),
        "--runs-dir",
        str(clean_repo / "workspace" / "runs"),
        "--json",
    ]
    rc = mod.main(cli_args)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASS"
    assert payload["segments_indexed"] == 3
    saved = json.loads(out.read_text(encoding="utf-8"))
    _assert_no_body_text(saved)


def test_output_under_gitignored_indexes() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "workspace/indexes/" in gitignore
