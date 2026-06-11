"""Compact micro-round progress synchronization tests."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "scripts"))

SPEC = importlib.util.spec_from_file_location(
    "run_micro_round_for_test",
    REPO_ROOT / "scripts" / "run_micro_round.py",
)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_final_progress_overwrites_stale_periodic_card(tmp_path: Path) -> None:
    run_root = tmp_path / "run"
    run_root.mkdir()
    (run_root / "micro_round_progress.json").write_text(
        json.dumps(
            {
                "status": "in_progress",
                "progress": "400/408",
                "api_calls": 6,
            }
        ),
        encoding="utf-8",
    )
    budget = MODULE.RunBudget(max_api_calls=10, max_segments=0)
    budget.api_calls_used = 7
    budget.segments_used = 128

    path = MODULE.write_final_micro_round_progress(
        run_root,
        round_id="D-MR-058",
        run_id="run-example",
        status="completed",
        progress={"completed_segments": 408, "total_segments": 408},
        checkpoint={"spent_usd": 0.0100095},
        summary_api_calls=7,
        run_budget=budget,
    )

    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["status"] == "completed"
    assert payload["progress"] == "408/408"
    assert payload["api_calls"] == 7
    assert payload["cost_usd"] == 0.010009
    assert payload["segments_per_call"] == 58.29
    assert payload["budget"]["segments_used"] == 128
