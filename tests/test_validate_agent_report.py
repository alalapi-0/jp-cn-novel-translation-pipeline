"""Tests for scripts/validate_agent_report.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "validate_agent_report.py"
SCHEMA = REPO_ROOT / "schemas" / "agent_round_report.schema.json"
LATEST = REPO_ROOT / "reports" / "latest-agent-report.json"


def _load_module():
    mod_name = "light_novel_validate_agent_report_test"
    spec = importlib.util.spec_from_file_location(mod_name, SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def validator():
    return _load_module()


def test_latest_report_validates(validator):
    ok, errors = validator.validate_report(LATEST, SCHEMA)
    assert ok, errors


def test_missing_required_field_fails(validator, tmp_path):
    report = {
        "round_id": "AL-TEST",
        "timestamp": "2026-06-09T12:00:00Z",
        "agent": "test",
        "agent_surface": "cursor",
        "mode": "audit",
        "goal": "test",
        "tool_probe_status": "passed",
        "gate_status": "warning",
    }
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    ok, errors = validator.validate_report(path, SCHEMA)
    assert not ok
    assert any("severity_summary" in e for e in errors)


def test_main_json_pass_on_latest(validator):
    code = validator.main(["--json"])
    assert code in (0, 1)


def test_invalid_json_exit_two(validator, tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text("{not json", encoding="utf-8")
    code = validator.main(["--report", str(bad), "--json"])
    assert code == 2
