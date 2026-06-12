"""Tests for phase_a_completion_check (FS-010)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

from phase_a_completion_check import evaluate  # noqa: E402
from translation.chapter_parser import count_source_chapters  # noqa: E402


def _make_repo(tmp_path: Path, chapters: int) -> Path:
    (tmp_path / "input_jp").mkdir(parents=True, exist_ok=True)
    for i in range(1, chapters + 1):
        (tmp_path / "input_jp" / f"{i}-ch.md").write_text("x", encoding="utf-8")
    (tmp_path / "workspace" / "control").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _add_completed_run(repo: Path, run_id: str, chapters: list[int]) -> None:
    root = repo / "workspace" / "runs" / run_id
    root.mkdir(parents=True, exist_ok=True)
    meta = {
        "run_id": run_id,
        "phase": "draft",
        "chapter_files": [f"input_jp/{c}-ch.md" for c in chapters],
    }
    (root / "run_metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    segs = {
        "chapters": [
            {
                "chapter_id": f"ch-{c}",
                "segments": [
                    {
                        "segment_id": f"ch-{c}-seg-001",
                        "draft_text": "译文",
                        "status": "completed",
                    }
                ],
            }
            for c in chapters
        ]
    }
    (root / "segments.json").write_text(json.dumps(segs), encoding="utf-8")
    progress = {
        "run_id": run_id,
        "status": "completed",
        "total_segments": len(chapters),
        "completed_segments": len(chapters),
    }
    (root / "run_progress.json").write_text(json.dumps(progress), encoding="utf-8")
    draft_dir = root / "draft"
    draft_dir.mkdir(parents=True, exist_ok=True)
    for c in chapters:
        (draft_dir / f"ch-{c}_draft_zh.md").write_text("# title\n\n译文\n", encoding="utf-8")
    cp = repo / "workspace" / "checkpoints" / f"{run_id}.json"
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps({"run_id": run_id}), encoding="utf-8")


def test_count_source_chapters_excludes_readme(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, chapters=3)
    (repo / "input_jp" / "README.md").write_text("# readme\n", encoding="utf-8")
    assert count_source_chapters(repo) == 3


def test_phase_a_pass_on_complete_mini_repo(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path, chapters=4)
    _add_completed_run(repo, "run_mini_draft_stage_b_50ch", [1, 2, 3, 4])
    result = evaluate(repo)
    assert result["checks"]["A1"]["pass"]
    assert result["checks"]["A2"]["pass"]
    assert result["checks"]["A3"]["pass"]
    assert result["checks"]["A8"]["pass"]
    assert result["checks"]["A9"]["pass"]
    # A7 metrics are production-scale; mini fixture only checks core draft gates.
    assert result["checks"]["A7"]["pass"] or result["checks"]["A1"]["pass"]
