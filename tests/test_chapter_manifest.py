"""Tests for FS-031: chapter manifest builder.

Acceptance:
- full coverage of numbered chapters in fixture repos;
- missing / duplicate chapters listed explicitly;
- incremental rebuild reuses unchanged segment files;
- manifest never contains source_text or draft_text.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from consistency.manifest import (  # noqa: E402
    build_chapter_manifest,
    discover_source_files,
    manifest_summary,
    scan_segments_file,
)

SCRIPT = REPO_ROOT / "scripts" / "build_chapter_manifest.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("light_novel_chapter_manifest_cli", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["light_novel_chapter_manifest_cli"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_source(repo: Path, num: int, *, title: str = "标题") -> Path:
    path = repo / "input_jp" / f"{num:03d}-sample.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# {title}\n\n正文段落。\n", encoding="utf-8")
    return path


def _write_completed_run(
    repo: Path,
    run_id: str,
    chapters: list[tuple[int, int, str]],
) -> Path:
    """chapters: [(num, segment_count, draft_status_suffix)]"""
    root = repo / "workspace" / "runs" / run_id
    root.mkdir(parents=True, exist_ok=True)
    meta = {
        "run_id": run_id,
        "phase": "draft",
        "chapter_files": [f"input_jp/{num:03d}-sample.md" for num, _, _ in chapters],
    }
    (root / "run_metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    seg_doc = {"chapters": []}
    total_segments = 0
    for num, seg_count, _ in chapters:
        segments = []
        for idx in range(1, seg_count + 1):
            segments.append(
                {
                    "segment_id": f"ch-{num}-seg-{idx:03d}",
                    "source_text": f"源文{idx}",
                    "draft_text": f"译文{idx}",
                    "status": "machine_translated",
                }
            )
        total_segments += len(segments)
        seg_doc["chapters"].append(
            {
                "chapter_id": f"ch-{num}",
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


def _assert_no_body_text(manifest: dict) -> None:
    blob = json.dumps(manifest, ensure_ascii=False)
    assert "source_text" not in blob
    assert "draft_text" not in blob
    assert "正文段落" not in blob
    assert "源文" not in blob
    assert "译文" not in blob


@pytest.fixture()
def mini_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    for num in (1, 2, 3, 4):
        _write_source(repo, num)
    _write_completed_run(repo, "run_mini_draft_stage_b_50ch", [(1, 2, ""), (2, 1, ""), (3, 3, ""), (4, 1, "")])
    return repo


def test_scan_segments_file_metadata_only(mini_repo: Path) -> None:
    seg_path = mini_repo / "workspace" / "runs" / "run_mini_draft_stage_b_50ch" / "segments.json"
    bucket = scan_segments_file(seg_path, run_id="run_mini_draft_stage_b_50ch")
    assert bucket[1]["segment_count"] == 2
    assert bucket[1]["draft_status"] == "complete"
    assert "source_text" not in json.dumps(bucket)


def test_full_coverage_mini_repo(mini_repo: Path) -> None:
    manifest = build_chapter_manifest(mini_repo, total_expected=4)
    _assert_no_body_text(manifest)
    assert manifest["stats"]["full_coverage"]
    assert manifest["stats"]["chapters_indexed"] == 4
    assert manifest["stats"]["missing_source_chapters"] == []
    assert manifest["stats"]["missing_draft_chapters"] == []
    assert manifest["stats"]["duplicate_source_chapters"] == []
    assert manifest["chapters"]["ch-1"]["segment_count"] == 2
    assert manifest["chapters"]["ch-1"]["source_run_id"] == "run_mini_draft_stage_b_50ch"


def test_missing_and_duplicate_explicit(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_source(repo, 1)
    _write_source(repo, 2)
    # duplicate chapter number 2
    dup = repo / "input_jp" / "002-alt.md"
    dup.write_text("# alt\n\nx\n", encoding="utf-8")
    _write_completed_run(repo, "run_partial_draft_stage_b_50ch", [(1, 1, "")])
    manifest = build_chapter_manifest(repo, total_expected=3)
    assert manifest["stats"]["missing_source_chapters"] == [3]
    assert manifest["stats"]["missing_draft_chapters"] == [2]
    assert 2 in manifest["stats"]["duplicate_source_chapters"]
    assert "002-alt.md" in json.dumps(manifest["stats"]["duplicate_source_details"])


def test_incremental_reuses_unchanged_files(mini_repo: Path) -> None:
    run_dirs = [mini_repo / "workspace" / "runs"]
    first = build_chapter_manifest(mini_repo, total_expected=4, run_dirs=run_dirs)
    assert first["stats"]["segment_files_scanned"] >= 1
    second = build_chapter_manifest(
        mini_repo, previous_index=first, total_expected=4, run_dirs=run_dirs
    )
    assert second["stats"]["segment_files_reused"] >= 1
    assert second["stats"]["segment_files_scanned"] == 0
    assert second["chapters"]["ch-1"]["content_hash"] == first["chapters"]["ch-1"]["content_hash"]


def test_incremental_rescans_changed_file(mini_repo: Path) -> None:
    run_dirs = [mini_repo / "workspace" / "runs"]
    first = build_chapter_manifest(mini_repo, total_expected=4, run_dirs=run_dirs)
    seg_path = mini_repo / "workspace" / "runs" / "run_mini_draft_stage_b_50ch" / "segments.json"
    doc = json.loads(seg_path.read_text(encoding="utf-8"))
    doc["chapters"][0]["segments"].append(
        {
            "segment_id": "ch-1-seg-003",
            "source_text": "新段",
            "draft_text": "新译",
            "status": "machine_translated",
        }
    )
    seg_path.write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    second = build_chapter_manifest(
        mini_repo, previous_index=first, total_expected=4, run_dirs=run_dirs
    )
    assert second["stats"]["segment_files_scanned"] >= 1
    assert second["chapters"]["ch-1"]["segment_count"] == 3


def test_discover_source_excludes_readme(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_source(repo, 1)
    (repo / "input_jp" / "README.md").write_text("# readme\n", encoding="utf-8")
    sources = discover_source_files(repo)
    assert list(sources) == [1]


def test_cli_json_and_incremental(mini_repo: Path, tmp_path: Path, capsys) -> None:
    mod = _load_script()
    out = tmp_path / "chapter_manifest.json"
    cli_args = [
        "--repo-root",
        str(mini_repo),
        "--output",
        str(out),
        "--runs-dir",
        str(mini_repo / "workspace" / "runs"),
        "--json",
    ]
    rc = mod.main(cli_args)
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASS"
    assert payload["chapters_indexed"] == 4

    rc2 = mod.main(cli_args)
    assert rc2 == 0
    payload2 = json.loads(capsys.readouterr().out)
    assert payload2["segment_files_reused"] >= 1


def test_manifest_summary_warn_on_gaps(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    _write_source(repo, 1)
    manifest = build_chapter_manifest(repo, total_expected=2)
    summary = manifest_summary(manifest)
    assert summary["status"] == "WARN"
    assert summary["missing_draft_chapters"] == [1]
    assert summary["missing_source_chapters"] == [2]
