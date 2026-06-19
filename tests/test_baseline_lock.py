"""Tests for FS-038 baseline lock and write protection."""

from __future__ import annotations

import importlib.util
import json
import os
import stat
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from translation.baseline_guard import (  # noqa: E402
    BaselineWriteError,
    apply_baseline_readonly,
    assert_baseline_writable,
    baseline_dir,
    baseline_metadata_path,
    is_baseline_locked,
)
from translation.baseline_lock import check_prerequisites, lock_baseline  # noqa: E402
from translation.chapter_parser import ParsedChapter, Segment  # noqa: E402
from translation.exporter import export_chapter_markdown  # noqa: E402

LOCK_SCRIPT = REPO_ROOT / "scripts" / "lock_baseline.py"


def _write_source(repo: Path, num: int) -> None:
    path = repo / "input_jp" / f"{num:03d}-sample.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"# 第{num}话\n\n源段落。\n", encoding="utf-8")


def _write_completed_run(repo: Path, run_id: str, chapters: list[int]) -> None:
    root = repo / "workspace" / "runs" / run_id
    root.mkdir(parents=True, exist_ok=True)
    total_segments = 0
    seg_doc = {"chapters": []}
    for num in chapters:
        segments = [
            {
                "segment_id": f"ch-{num}-seg-001",
                "source_text": "源",
                "draft_text": "译",
                "status": "machine_translated",
            }
        ]
        total_segments += len(segments)
        seg_doc["chapters"].append(
            {
                "chapter_id": f"ch-{num}",
                "chapter_label": f"第{num}话",
                "source_path": f"input_jp/{num:03d}-sample.md",
                "segments": segments,
            }
        )
    (root / "segments.json").write_text(json.dumps(seg_doc, ensure_ascii=False), encoding="utf-8")
    (root / "run_metadata.json").write_text(
        json.dumps({"run_id": run_id, "phase": "draft", "chapter_offset": min(chapters) - 1}),
        encoding="utf-8",
    )
    (root / "run_progress.json").write_text(
        json.dumps(
            {
                "status": "completed",
                "total_segments": total_segments,
                "completed_segments": total_segments,
            }
        ),
        encoding="utf-8",
    )


def _write_phase_reports(repo: Path) -> None:
    audit = repo / "workspace" / "consistency_audit"
    audit.mkdir(parents=True, exist_ok=True)
    (audit / "draft_consistency_report.json").write_text(
        json.dumps({"status": "pass", "blocking_conflicts": 0, "recommendation": "ready_for_baseline_lock"}),
        encoding="utf-8",
    )
    manifests = repo / "workspace" / "manifests"
    manifests.mkdir(parents=True, exist_ok=True)
    (manifests / "chapter_manifest.json").write_text(
        json.dumps({"stats": {"chapters_indexed": 2, "full_coverage": True}}),
        encoding="utf-8",
    )
    indexes = repo / "workspace" / "indexes"
    indexes.mkdir(parents=True, exist_ok=True)
    (indexes / "segment_index.json").write_text(
        json.dumps({"stats": {"missing_segments_count": 0}}),
        encoding="utf-8",
    )
    (indexes / "entity_index.json").write_text(json.dumps({"stats": {"entities_indexed": 1}}), encoding="utf-8")
    (audit / "glossary_conflict_audit.json").write_text(json.dumps({"findings": []}), encoding="utf-8")
    (audit / "fix_plan_status.json").write_text(
        json.dumps(
            {
                "term_fixes": {"status": "closed"},
                "deferred": {"status": "closed"},
                "retranslate_tasks": {"status": "closed"},
            }
        ),
        encoding="utf-8",
    )
    (audit / "arbitration_report.json").write_text(json.dumps({"api_calls": 0, "max_api_calls": 0}), encoding="utf-8")


def _stub_phase_gates(monkeypatch: pytest.MonkeyPatch, *, phase_a: bool, phase_b: bool) -> None:
    import translation.baseline_lock as bl

    monkeypatch.setattr(
        bl,
        "check_prerequisites",
        lambda repo_root: {
            "phase_a_pass": phase_a,
            "phase_b_pass": phase_b,
            "phase_a_failed": [] if phase_a else ["A1"],
            "phase_b_failed": [] if phase_b else ["B1"],
            "total_source_chapters": 2,
        },
    )


def test_lock_rejects_when_phase_b_incomplete(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for num in (1, 2):
        _write_source(tmp_path, num)
    _write_completed_run(tmp_path, "run_test_draft_stage_b_50ch", [1, 2])
    _stub_phase_gates(monkeypatch, phase_a=True, phase_b=False)
    with pytest.raises(RuntimeError, match="Phase A/B prerequisites"):
        lock_baseline(tmp_path, dry_run=True)


def test_lock_dry_run_then_real_lock(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for num in (1, 2):
        _write_source(tmp_path, num)
    _write_completed_run(tmp_path, "run_test_draft_stage_b_50ch", [1, 2])
    _write_phase_reports(tmp_path)
    _stub_phase_gates(monkeypatch, phase_a=True, phase_b=True)

    dry = lock_baseline(tmp_path, dry_run=True)
    assert dry["status"] == "dry_run"
    assert dry["chapter_count"] == 2
    assert not baseline_dir(tmp_path).exists()

    locked = lock_baseline(tmp_path, dry_run=False)
    assert locked["status"] == "locked"
    assert locked["chapter_count"] == 2
    assert is_baseline_locked(tmp_path)

    meta = json.loads(baseline_metadata_path(tmp_path).read_text(encoding="utf-8"))
    assert meta["locked"] is True
    assert len(meta["chapters"]) == 2
    assert meta["aggregate_hash"] == locked["aggregate_hash"]
    assert meta["consistency_report_ref"].endswith("draft_consistency_report.json")
    assert baseline_dir(tmp_path).joinpath("chapter_001_draft_zh.md").is_file()


def test_pipeline_refuses_baseline_write_when_locked(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for num in (1, 2):
        _write_source(tmp_path, num)
    _write_completed_run(tmp_path, "run_guard_draft_stage_b_50ch", [1, 2])
    _write_phase_reports(tmp_path)
    _stub_phase_gates(monkeypatch, phase_a=True, phase_b=True)
    lock_baseline(tmp_path, dry_run=False)

    chapter = ParsedChapter(
        chapter_id="ch-99",
        source_path="input_jp/099-sample.md",
        chapter_label="第99话",
        segments=[Segment(segment_id="ch-99-seg-001", source_text="a", draft_text="b")],
    )
    with pytest.raises(BaselineWriteError):
        export_chapter_markdown(chapter, baseline_dir(tmp_path), repo_root=tmp_path)


def test_readonly_bits_applied(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for num in (1, 2):
        _write_source(tmp_path, num)
    _write_completed_run(tmp_path, "run_ro_draft_stage_b_50ch", [1, 2])
    _write_phase_reports(tmp_path)
    _stub_phase_gates(monkeypatch, phase_a=True, phase_b=True)
    lock_baseline(tmp_path, dry_run=False)

    sample = next(baseline_dir(tmp_path).glob("chapter_*_draft_zh.md"))
    mode = sample.stat().st_mode
    assert not (mode & stat.S_IWUSR)
    assert mode & stat.S_IRUSR


def test_lock_cli_json_dry_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    for num in (1, 2):
        _write_source(tmp_path, num)
    _write_completed_run(tmp_path, "run_cli_draft_stage_b_50ch", [1, 2])
    _write_phase_reports(tmp_path)
    _stub_phase_gates(monkeypatch, phase_a=True, phase_b=True)
    monkeypatch.setenv("ALLOW_LEGACY_BASELINE_LOCK", "1")

    monkeypatch.setattr(
        "sys.argv",
        ["lock_baseline.py", "--dry-run", "--json", "--repo-root", str(tmp_path)],
    )
    spec = importlib.util.spec_from_file_location("lock_baseline_cli", LOCK_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lock_baseline_cli"] = mod
    spec.loader.exec_module(mod)
    assert mod.main() == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "dry_run"
    assert payload["chapter_count"] == 2


def test_lock_cli_disabled_without_legacy_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    monkeypatch.delenv("ALLOW_LEGACY_BASELINE_LOCK", raising=False)
    monkeypatch.setattr("sys.argv", ["lock_baseline.py", "--json", "--repo-root", str(tmp_path)])
    spec = importlib.util.spec_from_file_location("lock_baseline_cli_disabled", LOCK_SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["lock_baseline_cli_disabled"] = mod
    spec.loader.exec_module(mod)

    assert mod.main() == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "disabled"
    assert not (tmp_path / "draft_full_baseline").exists()


def test_assert_writable_allows_non_baseline_paths(tmp_path: Path) -> None:
    target = tmp_path / "workspace" / "runs" / "note.txt"
    target.parent.mkdir(parents=True, exist_ok=True)
    assert_baseline_writable(target, tmp_path)
    target.write_text("ok\n", encoding="utf-8")
