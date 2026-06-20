"""FS-042: refine diff builder and build_refine_diff CLI tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from refinement.diff_builder import (  # noqa: E402
    MODIFICATION_LENGTH_EXPANSION,
    MODIFICATION_MINOR_WORDING,
    MODIFICATION_PENDING,
    MODIFICATION_PUNCTUATION,
    MODIFICATION_SKIPPED_HUMAN,
    MODIFICATION_SUBSTANTIAL,
    MODIFICATION_UNCHANGED,
    build_refine_diff,
    build_refine_diff_for_run,
    classify_modification,
    compute_segment_metrics,
)


def _load_build_script():
    spec = importlib.util.spec_from_file_location(
        "build_refine_diff_test",
        REPO_ROOT / "scripts" / "build_refine_diff.py",
    )
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _fixture_doc() -> dict:
    return {
        "run_id": "test_refine_diff_run",
        "chapters": [
            {
                "chapter_id": "ch-171",
                "segments": [
                    {
                        "segment_id": "ch-171-seg-001",
                        "draft_text": "魔法结晶发出了光芒。",
                        "refined_text": "魔法结晶发出了光芒！",
                    },
                    {
                        "segment_id": "ch-171-seg-002",
                        "draft_text": "她抬头望向天空。",
                        "refined_text": "她抬头望向天空，心中满是疑问。",
                    },
                    {
                        "segment_id": "ch-171-seg-003",
                        "draft_text": "完全相同的句子。",
                        "refined_text": "完全相同的句子。",
                    },
                    {
                        "segment_id": "ch-171-seg-004",
                        "draft_text": "等待润色的段落。",
                    },
                    {
                        "segment_id": "ch-171-seg-005",
                        "draft_text": "人工锁定段落。",
                        "human_edited": True,
                    },
                ],
            }
        ],
    }


def test_classify_modification_categories() -> None:
    assert classify_modification(baseline="abc", refined="abc") == MODIFICATION_UNCHANGED
    assert (
        classify_modification(baseline="你好，世界。", refined="你好，世界！")
        == MODIFICATION_PUNCTUATION
    )
    assert (
        classify_modification(baseline="短句。", refined="这是一个明显更长的改写句子。")
        == MODIFICATION_LENGTH_EXPANSION
    )
    assert classify_modification(baseline="x", refined="", has_refined=False) == MODIFICATION_PENDING
    assert (
        classify_modification(baseline="locked", refined="", human_edited=True, has_refined=False)
        == MODIFICATION_SKIPPED_HUMAN
    )


def test_compute_segment_metrics_reproducible() -> None:
    baseline = "她抬头望向天空。"
    refined = "她抬头望向天空，心中满是疑问。"
    first = compute_segment_metrics(baseline=baseline, refined=refined)
    second = compute_segment_metrics(baseline=baseline, refined=refined)
    assert first == second
    assert first["diff_ratio"] == round(1.0 - first["similarity_ratio"], 6)
    assert first["modification_type"] in {
        MODIFICATION_MINOR_WORDING,
        MODIFICATION_SUBSTANTIAL,
        MODIFICATION_LENGTH_EXPANSION,
    }


def test_build_refine_diff_summary_and_segments() -> None:
    diff_doc, change_log = build_refine_diff(_fixture_doc(), run_id="test_refine_diff_run")
    stats = diff_doc["summary"]
    assert stats["total_segments"] == 5
    assert stats["changed_segments"] >= 2
    assert stats["unchanged_segments"] == 1
    assert stats["pending_segments"] == 1
    assert stats["skipped_human_edited_segments"] == 1
    assert set(stats["category_counts"]) >= {
        MODIFICATION_UNCHANGED,
        MODIFICATION_PENDING,
        MODIFICATION_SKIPPED_HUMAN,
    }

    seg_by_id = {s["segment_id"]: s for s in change_log["segments"]}
    assert seg_by_id["ch-171-seg-001"]["modification_type"] == MODIFICATION_PUNCTUATION
    assert seg_by_id["ch-171-seg-003"]["modification_type"] == MODIFICATION_UNCHANGED
    assert seg_by_id["ch-171-seg-004"]["modification_type"] == MODIFICATION_PENDING
    assert seg_by_id["ch-171-seg-005"]["modification_type"] == MODIFICATION_SKIPPED_HUMAN
    assert "baseline_text" not in seg_by_id["ch-171-seg-001"]
    assert diff_doc["segments"][0]["baseline_text"]
    assert diff_doc["segments"][0]["unified_diff"]


def test_build_refine_diff_is_deterministic() -> None:
    doc = _fixture_doc()
    diff_a, log_a = build_refine_diff(doc, run_id="x", generated_at="2026-06-12T00:00:00+00:00")
    diff_b, log_b = build_refine_diff(doc, run_id="x", generated_at="2026-06-12T00:00:00+00:00")
    assert diff_a["summary"] == diff_b["summary"]
    assert log_a["segments"] == log_b["segments"]


def test_build_refine_diff_for_run_writes_gitignored_artifacts(tmp_path: Path) -> None:
    run_id = "run_test_refine_diff"
    run_root = tmp_path / "workspace" / "runs" / run_id
    run_root.mkdir(parents=True)
    (run_root / "segments.json").write_text(
        json.dumps(_fixture_doc(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (run_root / "run_metadata.json").write_text(
        json.dumps({"run_id": run_id}, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    summary = build_refine_diff_for_run(run_root)
    assert summary["run_id"] == run_id
    assert (run_root / "draft_vs_refined_diff.json").is_file()
    assert (run_root / "change_log.json").is_file()

    diff_payload = json.loads((run_root / "draft_vs_refined_diff.json").read_text(encoding="utf-8"))
    log_payload = json.loads((run_root / "change_log.json").read_text(encoding="utf-8"))
    assert diff_payload["artifact"] == "draft_vs_refined_diff"
    assert log_payload["artifact"] == "refine_change_log"
    assert diff_payload["summary"]["avg_diff_ratio"] == log_payload["summary"]["avg_diff_ratio"]


def test_build_refine_diff_cli_json(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ALLOW_LEGACY_REFINEMENT", "1")
    mod = _load_build_script()
    run_id = "run_cli_refine_diff"
    run_root = tmp_path / "workspace" / "runs" / run_id
    run_root.mkdir(parents=True)
    (run_root / "segments.json").write_text(json.dumps(_fixture_doc()), encoding="utf-8")

    code = mod.main(["--run-dir", str(run_root), "--repo-root", str(tmp_path), "--json"])
    assert code == 0


def test_build_refine_diff_cli_missing_run(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ALLOW_LEGACY_REFINEMENT", "1")
    mod = _load_build_script()
    code = mod.main(
        [
            "--run-id",
            "missing_run",
            "--repo-root",
            str(tmp_path),
            "--json",
        ]
    )
    assert code == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "missing_segments"


def test_build_refine_diff_from_refine_pilot_fixture() -> None:
    fixture_path = REPO_ROOT / "tests" / "fixtures" / "refine_pilot_segments.json"
    doc = json.loads(fixture_path.read_text(encoding="utf-8"))
    doc["chapters"][0]["segments"][0]["refined_text"] = "魔法结晶发出了更柔和的光芒。"
    doc["chapters"][0]["segments"][2]["refined_text"] = "「真的没事吗？」"
    diff_doc, change_log = build_refine_diff(doc, run_id="pilot")
    assert diff_doc["summary"]["total_segments"] == 3
    assert len(change_log["segments"]) == 3
    changed_types = {s["modification_type"] for s in change_log["segments"] if s["changed"]}
    assert changed_types
    assert MODIFICATION_SKIPPED_HUMAN in {
        s["modification_type"] for s in change_log["segments"]
    }
