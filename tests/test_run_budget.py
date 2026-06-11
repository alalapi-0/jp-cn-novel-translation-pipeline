"""Wall-time enforcement tests for supervised translation runs."""

from __future__ import annotations

import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from translation.draft_runner import (  # noqa: E402
    RunBudget,
    _bound_provider_timeout,
    run_draft_stage_b,
)


def test_provider_timeout_is_bounded_by_remaining_wall_budget() -> None:
    class Provider:
        timeout_sec = None

    provider = Provider()
    budget = RunBudget(
        max_wall_seconds=900,
        started_at=time.monotonic(),
    )

    timeout = _bound_provider_timeout(
        provider,
        budget,
        outer_attempts_remaining=3,
    )

    assert timeout is not None
    assert 1 <= timeout <= 60
    assert provider.timeout_sec == timeout


def test_exhausted_wall_budget_does_not_call_provider(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("CONTROLLED_RUN_ENABLED", "true")
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "false")
    input_dir = tmp_path / "input_jp"
    input_dir.mkdir()
    (input_dir / "001-test.md").write_text(
        "# Test\n\n## Section\n\nFirst paragraph.\n",
        encoding="utf-8",
    )

    class Provider:
        provider_id = "stub"
        model_name = "stub-model"
        network_calls = 0

        def __init__(self, cost_guard=None):
            self.cost_guard = cost_guard

        def generate(self, messages, options=None):
            self.network_calls += 1
            raise AssertionError("provider must not be called after wall budget exhaustion")

    holder: dict[str, Provider] = {}

    def factory(guard):
        holder["provider"] = Provider(cost_guard=guard)
        return holder["provider"]

    summary, run_root = run_draft_stage_b(
        repo_root=tmp_path,
        input_dir=input_dir,
        limit_chapters=1,
        run_id="wall-budget-exhausted",
        provider_factory=factory,
        run_budget=RunBudget(max_wall_seconds=1, started_at=0),
    )

    assert holder["provider"].network_calls == 0
    assert summary.tick_paused is True
    assert (run_root / "run_progress.json").is_file()
