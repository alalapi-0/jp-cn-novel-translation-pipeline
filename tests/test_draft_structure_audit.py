"""Tests for FS-035: draft structure audit.

Acceptance (docs/final_state_round_task_list.md FS-035):
- four issue kinds with fixtures (missing_segment, misalignment, source_residual, format_anomaly);
- false-positive regression set (Chinese-only drafts must not trigger source_residual);
- severity grading in output; no body text in report;
- blocking = structural issues only.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from consistency.draft_structure_audit import (  # noqa: E402
    BLOCKING_RULES,
    SOURCE_RESIDUAL_FALSE_POSITIVES,
    SEVERITY_BY_KIND,
    audit_draft_structure,
    audit_summary,
    detect_format_anomaly,
    detect_source_residual,
    legacy_would_flag_source_residual,
)
from consistency.segment_index import build_segment_index  # noqa: E402

SCRIPT = REPO_ROOT / "scripts" / "audit_draft_structure.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("light_novel_draft_structure_cli", SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules["light_novel_draft_structure_cli"] = mod
    spec.loader.exec_module(mod)
    return mod


def _write_run(
    repo: Path,
    run_id: str,
    chapters: list[tuple[int, list[tuple[str, str, str]]]],
) -> None:
    root = repo / "workspace" / "runs" / run_id
    root.mkdir(parents=True, exist_ok=True)
    meta = {
        "run_id": run_id,
        "phase": "draft",
        "chapter_files": [f"input_jp/{num:03d}.md" for num, _ in chapters],
    }
    (root / "run_metadata.json").write_text(json.dumps(meta), encoding="utf-8")
    seg_doc = {"chapters": []}
    total = 0
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
        total += len(segments)
        seg_doc["chapters"].append(
            {
                "chapter_id": f"ch-{num:03d}",
                "source_path": f"input_jp/{num:03d}.md",
                "segments": segments,
            }
        )
    (root / "segments.json").write_text(json.dumps(seg_doc, ensure_ascii=False), encoding="utf-8")
    progress = {
        "run_id": run_id,
        "status": "completed",
        "total_segments": total,
        "completed_segments": total,
    }
    (root / "run_progress.json").write_text(json.dumps(progress), encoding="utf-8")


def _assert_no_body_text(report: dict) -> None:
    blob = json.dumps(report, ensure_ascii=False)
    assert "source_text" not in blob
    assert "draft_text" not in blob
    for sample in SOURCE_RESIDUAL_FALSE_POSITIVES:
        assert sample["draft"] not in blob


@pytest.fixture()
def clean_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_run(
        repo,
        "run_clean",
        [
            (
                1,
                [
                    ("ch-001-seg-001", "サンプル", "示例译文第一段。"),
                    ("ch-001-seg-002", "続き", "示例译文第二段。"),
                ],
            ),
        ],
    )
    return repo


def test_false_positive_regression_chinese_only_not_flagged():
    for sample in SOURCE_RESIDUAL_FALSE_POSITIVES:
        assert detect_source_residual(sample["draft"]) is None
        assert legacy_would_flag_source_residual(sample["draft"])


def test_source_residual_kana_positive():
    meta = detect_source_residual("他低声念道：「さようなら」然后离开了。")
    assert meta is not None
    assert meta["hint"] == "japanese_kana_present"
    assert meta["kana_run_count"] >= 1


def test_source_residual_single_kana_not_flagged():
    assert detect_source_residual("注：ー") is None


def test_format_anomaly_excessive_blank_lines():
    draft = "第一段。\n\n\n\n\n第二段。"
    meta = detect_format_anomaly(draft)
    assert meta is not None
    assert "excessive_blank_lines" in meta["hints"]


def test_missing_segment_blocking_finding(clean_repo: Path):
    _write_run(
        clean_repo,
        "run_gap",
        [
            (
                2,
                [
                    ("ch-002-seg-001", "a", "第一段"),
                    ("ch-002-seg-003", "c", "第三段漏了002"),
                ],
            ),
        ],
    )
    index = build_segment_index(clean_repo)
    report = audit_draft_structure(index, clean_repo)
    missing = [f for f in report["findings"] if f["kind"] == "missing_segment"]
    assert len(missing) == 1
    assert missing[0]["blocking"] is True
    assert missing[0]["severity"] == "blocking"
    assert missing[0]["expected_segment_id"] == "ch-002-seg-002"


def test_misalignment_blocking_finding(clean_repo: Path):
    _write_run(
        clean_repo,
        "run_misalign",
        [
            (
                3,
                [
                    ("ch-003-seg-001", "a", "ok"),
                    ("ch-004-seg-002", "b", "wrong chapter in id"),
                ],
            ),
        ],
    )
    index = build_segment_index(clean_repo)
    report = audit_draft_structure(index, clean_repo)
    mis = [f for f in report["findings"] if f["kind"] == "misalignment"]
    assert len(mis) >= 1
    assert all(f["blocking"] for f in mis)
    assert any(f.get("issue_subtype") == "chapter_mismatch" for f in mis)


def test_source_residual_finding_non_blocking(clean_repo: Path):
    _write_run(
        clean_repo,
        "run_residual",
        [
            (
                4,
                [
                    ("ch-004-seg-001", "jp", "残留テスト段落。"),
                ],
            ),
        ],
    )
    index = build_segment_index(clean_repo)
    report = audit_draft_structure(index, clean_repo)
    residual = [f for f in report["findings"] if f["kind"] == "source_residual"]
    assert len(residual) == 1
    assert residual[0]["blocking"] is False
    assert residual[0]["severity"] == "warning"
    assert residual[0]["segment_ids"] == ["ch-004-seg-001"]


def test_format_anomaly_info_severity(clean_repo: Path):
    _write_run(
        clean_repo,
        "run_format",
        [
            (
                5,
                [
                    ("ch-005-seg-001", "jp", "段落一。\n\n\n\n\n段落二。"),
                ],
            ),
        ],
    )
    index = build_segment_index(clean_repo)
    report = audit_draft_structure(index, clean_repo)
    fmt = [f for f in report["findings"] if f["kind"] == "format_anomaly"]
    assert len(fmt) == 1
    assert fmt[0]["blocking"] is False
    assert fmt[0]["severity"] == "info"


def test_missing_draft_blocking(clean_repo: Path):
    _write_run(
        clean_repo,
        "run_empty_draft",
        [
            (
                6,
                [
                    ("ch-006-seg-001", "jp", ""),
                ],
            ),
        ],
    )
    index = build_segment_index(clean_repo)
    report = audit_draft_structure(index, clean_repo)
    empty = [f for f in report["findings"] if f["kind"] == "missing_draft"]
    assert len(empty) == 1
    assert empty[0]["blocking"] is True


def test_severity_stats_and_no_body_text(clean_repo: Path):
    index = build_segment_index(clean_repo)
    report = audit_draft_structure(index, clean_repo)
    _assert_no_body_text(report)
    assert "by_severity" in report["stats"]
    assert report["severity_rules"] == SEVERITY_BY_KIND
    assert report["blocking_rules"] == BLOCKING_RULES


def test_audit_summary_pass_when_no_blocking(clean_repo: Path):
    index = build_segment_index(clean_repo)
    report = audit_draft_structure(index, clean_repo)
    summary = audit_summary(report)
    assert summary["status"] == "PASS"
    assert summary["blocking_count"] == 0


def test_audit_summary_warn_when_blocking(clean_repo: Path):
    _write_run(
        clean_repo,
        "run_block",
        [
            (
                7,
                [
                    ("ch-007-seg-001", "a", "x"),
                    ("ch-007-seg-003", "c", "gap"),
                ],
            ),
        ],
    )
    index = build_segment_index(clean_repo)
    report = audit_draft_structure(index, clean_repo)
    summary = audit_summary(report)
    assert summary["status"] == "WARN"
    assert summary["blocking_count"] >= 1


def test_cli_json_output(tmp_path: Path, clean_repo: Path, capsys):
    index = build_segment_index(clean_repo)
    index_path = tmp_path / "segment_index.json"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    out_path = tmp_path / "audit.json"

    mod = _load_script()
    rc = mod.main(
        [
            "--repo-root",
            str(clean_repo),
            "--segment-index",
            str(index_path),
            "--output",
            str(out_path),
            "--json",
        ]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "PASS"
    assert out_path.is_file()
    _assert_no_body_text(json.loads(out_path.read_text(encoding="utf-8")))


def test_deterministic_order(clean_repo: Path):
    _write_run(
        clean_repo,
        "run_multi",
        [
            (
                8,
                [
                    ("ch-008-seg-001", "a", "中文。"),
                    ("ch-008-seg-002", "b", "カタカナ残留"),
                    ("ch-008-seg-003", "c", "a\n\n\n\n\nb"),
                ],
            ),
        ],
    )
    index = build_segment_index(clean_repo)
    first = audit_draft_structure(index, clean_repo, generated_at="fixed")
    second = audit_draft_structure(index, clean_repo, generated_at="fixed")
    assert first["findings"] == second["findings"]
