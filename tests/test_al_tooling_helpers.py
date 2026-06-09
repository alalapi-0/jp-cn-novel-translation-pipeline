"""AL-019: tests for tool_probe, user_view_test, gate helpers, translation scripts."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def test_tool_probe_build_report():
    tp = _load("tp_test", REPO_ROOT / "scripts" / "tool_probe.py")
    report = tp.build_report()
    assert report["status"] in ("passed", "partial")
    assert "local_tools" in report


def test_user_view_static_checks():
    uv = _load("uv_test", REPO_ROOT / "scripts" / "user_view_test.py")
    report = uv.run_checks()
    assert report["checks"]
    assert "playwright_config" in [c["name"] for c in report["checks"]]


def test_gate_triage_empty():
    gt = _load("gt_test", REPO_ROOT / "scripts" / "gate_triage.py")
    out = gt.triage_gate_result({"status": "passed", "failed": []})
    assert out["severity_summary"]["p0"] == 0


def test_suggest_next_after_al013():
    sn = _load("sn_test", REPO_ROOT / "scripts" / "suggest_next_al_round.py")
    done = {f"AL-{n:03d}" for n in range(1, 15)} | {"AL-002", "AL-028"}
    assert sn.suggest_next(done) == "AL-015"


def test_chapter_integrity_fixture():
    ci = _load("ci_test", REPO_ROOT / "scripts" / "check_chapter_integrity.py")
    doc = json.loads((REPO_ROOT / "data/examples/review_segments.fixture.json").read_text())
    assert not ci.validate_segments(doc)


def test_check_prompts_refs_pass():
    code = _load("cpr_test", REPO_ROOT / "scripts" / "check_prompts_refs.py").main()
    assert code == 0
