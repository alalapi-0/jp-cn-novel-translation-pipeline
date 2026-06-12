"""FS-041: supervised refine micro-round runner tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

SPEC = importlib.util.spec_from_file_location(
    "run_micro_round_refine_test",
    REPO_ROOT / "scripts" / "run_micro_round.py",
)
assert SPEC and SPEC.loader
RUN_MR = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(RUN_MR)

from translation.refine_runner import (  # noqa: E402
    _count_refine_totals,
    bootstrap_refine_run_from_baseline,
    run_refine_micro_round,
)
from providers.fake_provider import FakeProvider  # noqa: E402
from translation.draft_runner import RunBudget  # noqa: E402


def _write_baseline_chapter(
    baseline_dir: Path,
    chapter_num: int,
    segment_count: int,
) -> None:
    lines = [f"# Chapter {chapter_num}", ""]
    for i in range(1, segment_count + 1):
        lines.extend(
            [
                f"<!-- ch-{chapter_num:03d}-seg-{i:03d} -->",
                f"draft text {chapter_num}-{i}",
                "",
            ]
        )
    path = baseline_dir / f"chapter_{chapter_num:03d}_draft_zh.md"
    path.write_text("\n".join(lines), encoding="utf-8")


@pytest.fixture()
def refine_baseline_repo(tmp_path: Path) -> Path:
    baseline = tmp_path / "draft_full_baseline"
    baseline.mkdir()
    _write_baseline_chapter(baseline, 171, 4)
    _write_baseline_chapter(baseline, 172, 3)
    (tmp_path / "draft_full_baseline_metadata.json").write_text(
        json.dumps({"locked": True, "chapter_count": 2}),
        encoding="utf-8",
    )
    return tmp_path


def test_refine_dry_run_plan_from_baseline(
    refine_baseline_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(RUN_MR, "REPO_ROOT", refine_baseline_repo)
    code, payload = RUN_MR._run_refine_micro_round(
        round_id="R-MR-001",
        chapter_range="171-172",
        dry_run=True,
        real_api=False,
        fake_provider=True,
    )
    assert code == 0
    assert payload["phase"] == "refine"
    assert payload["mode"] == "dry_run"
    assert payload["total_segments"] == 7
    assert payload["input_source"] == "draft_full_baseline"
    assert payload["batch_count"] >= 1


def test_refine_fake_provider_e2e(refine_baseline_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("CONTROLLED_RUN_ENABLED", "1")
    monkeypatch.setenv("TRANSLATION_ROUND_ID", "R-MR-TEST")
    monkeypatch.setenv("MAX_TEST_COST_USD", "1.0")
    run_id = "micro_validate_refine_e2e"

    def factory(guard: object) -> FakeProvider:
        return FakeProvider(cost_guard=guard)  # type: ignore[arg-type]

    summary, run_root = run_refine_micro_round(
        repo_root=refine_baseline_repo,
        run_id=run_id,
        chapter_start=171,
        chapter_end=172,
        chapter_offset=170,
        provider_factory=factory,
        round_id="R-MR-TEST",
    )
    assert summary.refined_segments == 7
    assert summary.api_calls >= 1
    assert summary.provider_mode == "custom"
    doc = json.loads((run_root / "segments.json").read_text(encoding="utf-8"))
    _, refined = _count_refine_totals(doc)
    assert refined == 7
    progress = json.loads((run_root / "run_progress.json").read_text(encoding="utf-8"))
    assert progress["status"] == "completed"
    assert (run_root / "micro_round_progress.json").is_file()
    provenance = json.loads((run_root / "input_provenance.json").read_text(encoding="utf-8"))
    assert provenance["input_source"] == "draft_full_baseline"
    assert provenance["baseline_read_only"] is True


def test_refine_resume_no_duplicate_refine(
    refine_baseline_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.setenv("CONTROLLED_RUN_ENABLED", "1")
    monkeypatch.setenv("TRANSLATION_ROUND_ID", "R-MR-RESUME")
    monkeypatch.setenv("MAX_TEST_COST_USD", "1.0")
    run_id = "micro_validate_refine_resume"

    def factory(guard: object) -> FakeProvider:
        return FakeProvider(cost_guard=guard)  # type: ignore[arg-type]

    budget = RunBudget(max_segments=4, max_api_calls=0)
    first, _ = run_refine_micro_round(
        repo_root=refine_baseline_repo,
        run_id=run_id,
        chapter_start=171,
        chapter_end=172,
        chapter_offset=170,
        provider_factory=factory,
        run_budget=budget,
        round_id="R-MR-RESUME",
    )
    assert first.refined_segments == 4
    first_calls = first.api_calls

    budget2 = RunBudget(max_segments=10, max_api_calls=0)
    second, run_root = run_refine_micro_round(
        repo_root=refine_baseline_repo,
        run_id=run_id,
        chapter_start=171,
        chapter_end=172,
        chapter_offset=170,
        provider_factory=factory,
        run_budget=budget2,
        round_id="R-MR-RESUME",
    )
    assert second.refined_segments == 3
    assert second.api_calls < first_calls + second.refined_segments
    doc = json.loads((run_root / "segments.json").read_text(encoding="utf-8"))
    _, refined = _count_refine_totals(doc)
    assert refined == 7


def test_bootstrap_skips_when_run_exists(refine_baseline_repo: Path) -> None:
    run_id = "micro_validate_bootstrap_once"
    first = bootstrap_refine_run_from_baseline(
        refine_baseline_repo,
        run_id=run_id,
        chapter_start=171,
        chapter_end=172,
        chapter_offset=170,
    )
    mtime = (first / "segments.json").stat().st_mtime
    second = bootstrap_refine_run_from_baseline(
        refine_baseline_repo,
        run_id=run_id,
        chapter_start=171,
        chapter_end=172,
        chapter_offset=170,
    )
    assert first == second
    assert (second / "segments.json").stat().st_mtime == mtime


def test_run_micro_round_refine_cli_dry_run(
    refine_baseline_repo: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(RUN_MR, "REPO_ROOT", refine_baseline_repo)
    code, payload = RUN_MR.run_micro_round(
        phase="refine",
        round_id="R-MR-001",
        chapter_range="171-172",
        dry_run=True,
        fake_provider=True,
        real_api=False,
    )
    assert code == 0
    assert payload["total_segments"] == 7
