"""Tests for checkpoint → artifact hydration."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_hydrate():
    spec = importlib.util.spec_from_file_location(
        "hydrate_checkpoint_test",
        REPO_ROOT / "scripts" / "hydrate_checkpoint.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_plan_hydrate_from_checkpoint_and_draft(tmp_path: Path) -> None:
    hydrate = _load_hydrate()
    repo = tmp_path
    input_dir = repo / "input_jp"
    input_dir.mkdir(parents=True)
    (input_dir / "151-test.md").write_text(
        "# Title\n\n## Sub\n\nParagraph one.\n\nParagraph two.\n",
        encoding="utf-8",
    )

    run_id = "run_test_hydrate"
    run_root = repo / "workspace" / "runs" / run_id
    draft_dir = run_root / "draft"
    draft_dir.mkdir(parents=True)
    (draft_dir / "ch-151_draft_zh.md").write_text(
        "# Title / Sub\n\n<!-- ch-151-seg-001 -->\nDraft one.\n\n<!-- ch-151-seg-002 -->\nDraft two.\n",
        encoding="utf-8",
    )

    cp_dir = repo / "workspace" / "checkpoints"
    cp_dir.mkdir(parents=True)
    (cp_dir / f"{run_id}.json").write_text(
        json.dumps(
            {
                "run_id": run_id,
                "status": "in_progress",
                "completed_segments": ["ch-151-seg-001", "ch-151-seg-002"],
                "spent_usd": 0.5,
            }
        ),
        encoding="utf-8",
    )

    plan = hydrate.plan_hydrate(
        repo_root=repo,
        run_id=run_id,
        input_dir=input_dir,
        chapter_offset=0,
        limit_chapters=1,
    )
    assert plan["translated_segments"] == 2
    assert plan["chapter_offset"] == 0

    hydrate.apply_hydrate(plan, repo_root=repo, run_id=run_id, chapter_offset=0)
    segments = json.loads((run_root / "segments.json").read_text(encoding="utf-8"))
    segs = segments["chapters"][0]["segments"]
    assert segs[0]["draft_text"] == "Draft one."
    assert (run_root / "run_metadata.json").is_file()
    assert (run_root / "run_progress.json").is_file()


def test_plan_hydrate_drops_segments_outside_limit_window(tmp_path: Path) -> None:
    hydrate = _load_hydrate()
    repo = tmp_path
    input_dir = repo / "input_jp"
    input_dir.mkdir(parents=True)
    for num in range(1, 26):
        (input_dir / f"{num:03d}-ch.md").write_text(
            f"# Ch{num}\n\nPara one.\n\nPara two.\n",
            encoding="utf-8",
        )

    run_id = "run_window_trim"
    cp_dir = repo / "workspace" / "checkpoints"
    cp_dir.mkdir(parents=True)
    completed = ["ch-001-seg-001", "ch-020-seg-001", "ch-021-seg-001", "ch-025-seg-001"]
    (cp_dir / f"{run_id}.json").write_text(
        json.dumps({"run_id": run_id, "status": "in_progress", "completed_segments": completed}),
        encoding="utf-8",
    )

    plan = hydrate.plan_hydrate(
        repo_root=repo,
        run_id=run_id,
        input_dir=input_dir,
        chapter_offset=0,
        limit_chapters=20,
    )
    assert plan["dropped_checkpoint_segments"] == 2
    assert plan["completed_checkpoint_segments"] == 2
    chapter_ids = {ch.chapter_id for ch in plan["chapters"]}
    assert "ch-021" not in chapter_ids
    assert "ch-025" not in chapter_ids
    assert "ch-001" in chapter_ids
    assert "ch-020" in chapter_ids

    hydrate.apply_hydrate(plan, repo_root=repo, run_id=run_id, chapter_offset=0)
    cp_after = json.loads((cp_dir / f"{run_id}.json").read_text(encoding="utf-8"))
    assert "ch-021-seg-001" not in cp_after["completed_segments"]
    assert "ch-025-seg-001" not in cp_after["completed_segments"]
