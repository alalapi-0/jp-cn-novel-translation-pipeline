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
CURRENT = REPO_ROOT / "reports" / "current-cohort-report.json"
LEGACY = REPO_ROOT / "reports" / "latest-agent-report.json"


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


def test_current_cohort_report_validates(validator):
    ok, errors = validator.validate_report(CURRENT, SCHEMA)
    assert ok, errors


def test_pre_policy_legacy_report_is_grandfathered_but_not_the_default(validator):
    ok, errors = validator.validate_report(LEGACY, SCHEMA)
    assert ok, errors
    assert validator.DEFAULT_REPORT == CURRENT


def test_backdated_current_shape_cannot_use_legacy_compatibility(validator, tmp_path):
    report = {
        "round_id": "FS-BACKDATED",
        "timestamp": "2026-08-12T23:59:59Z",
        "agent": "test",
        "agent_surface": "codex",
        "mode": "implement",
        "goal": "test",
        "changed_files": ["src/undelivered.py"],
        "tool_probe_status": "not_run",
        "gate_status": "passed",
        "severity_summary": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "overall_status": "completed",
        "next_recommended_round": "FS-NEXT",
    }
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert validator.validate_with_jsonschema(report, schema)

    path = tmp_path / "backdated-current.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    ok, errors = validator.validate_report(path, SCHEMA)
    assert not ok
    assert errors


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


def test_main_json_pass_on_current_cohort_report(validator):
    code = validator.main(["--json"])
    assert code == 0


def test_current_candidate_requires_changed_files_and_matching_status(validator, tmp_path):
    report = {
        "round_id": "FS-TEST",
        "timestamp": "2026-08-13T01:00:00Z",
        "agent": "test",
        "agent_surface": "codex",
        "mode": "implement",
        "goal": "test",
        "policy_version": "git_safe_cohort_delivery_v1",
        "cohort_status": "candidate_ready_for_delivery",
        "git_delivery": {
            "status": "work_in_progress",
            "remote_sha_verified": False,
            "completion_authority": "fresh_remote_sha_and_ignored_delivery_receipt",
        },
        "changed_files": [],
        "tool_probe_status": "not_run",
        "gate_status": "passed",
        "severity_summary": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "next_recommended_round": "",
    }
    path = tmp_path / "inconsistent.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    ok, errors = validator.validate_report(path, SCHEMA)
    assert not ok
    assert any("must match" in error for error in errors)
    assert any("changed_files" in error for error in errors)


def test_current_timestamp_requires_delivery_policy(validator, tmp_path):
    report = {
        "round_id": "FS-TEST",
        "timestamp": "2026-08-13T01:00:00Z",
        "agent": "test",
        "agent_surface": "codex",
        "mode": "implement",
        "goal": "test",
        "tool_probe_status": "not_run",
        "gate_status": "passed",
        "severity_summary": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
    }
    path = tmp_path / "missing-policy.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    ok, errors = validator.validate_report(path, SCHEMA)
    assert not ok
    assert any("git_safe_cohort_delivery_v1" in error for error in errors)
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    assert {"policy_version", "cohort_status", "git_delivery"} <= set(
        schema["required"]
    )


def test_not_applicable_cannot_hide_git_safe_changes(validator, tmp_path):
    report = {
        "round_id": "FS-TEST",
        "timestamp": "2026-08-13T01:00:00Z",
        "agent": "test",
        "agent_surface": "codex",
        "mode": "implement",
        "goal": "test",
        "policy_version": "git_safe_cohort_delivery_v1",
        "cohort_status": "not_applicable",
        "git_delivery": {
            "status": "not_applicable",
            "remote_sha_verified": False,
            "completion_authority": "fresh_remote_sha_and_ignored_delivery_receipt",
        },
        "changed_files": ["src/hidden.py"],
        "tool_probe_status": "not_run",
        "gate_status": "passed",
        "severity_summary": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "next_recommended_round": "FS-NEXT",
    }
    path = tmp_path / "hidden-change.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    ok, errors = validator.validate_report(path, SCHEMA)
    assert not ok
    assert any("not_applicable" in error for error in errors)


def test_invalid_json_exit_two(validator, tmp_path):
    bad = tmp_path / "broken.json"
    bad.write_text("{not json", encoding="utf-8")
    code = validator.main(["--report", str(bad), "--json"])
    assert code == 2


def test_current_candidate_report_cannot_name_next_before_remote_delivery(validator, tmp_path):
    report = {
        "round_id": "FS-TEST",
        "timestamp": "2026-08-13T01:00:00Z",
        "agent": "test",
        "agent_surface": "codex",
        "mode": "implement",
        "goal": "test",
        "policy_version": "git_safe_cohort_delivery_v1",
        "cohort_status": "candidate_ready_for_delivery",
        "git_delivery": {
            "status": "candidate_ready_for_delivery",
            "remote_sha_verified": False,
            "completion_authority": "fresh_remote_sha_and_ignored_delivery_receipt",
        },
        "changed_files": ["src/example.py"],
        "tool_probe_status": "not_run",
        "gate_status": "passed",
        "severity_summary": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "next_recommended_round": "FS-NEXT",
    }
    path = tmp_path / "premature.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    ok, errors = validator.validate_report(path, SCHEMA)
    assert not ok
    assert any("next cohort" in error for error in errors)


def test_current_report_cannot_self_attest_remote_completion(validator, tmp_path):
    report = {
        "round_id": "FS-TEST",
        "timestamp": "2026-08-13T01:00:00Z",
        "agent": "test",
        "agent_surface": "codex",
        "mode": "implement",
        "goal": "test",
        "policy_version": "git_safe_cohort_delivery_v1",
        "cohort_status": "candidate_ready_for_delivery",
        "git_delivery": {
            "status": "candidate_ready_for_delivery",
            "remote_sha_verified": True,
            "completion_authority": "fresh_remote_sha_and_ignored_delivery_receipt",
        },
        "changed_files": ["src/example.py"],
        "tool_probe_status": "not_run",
        "gate_status": "passed",
        "severity_summary": {"p0": 0, "p1": 0, "p2": 0, "p3": 0},
        "next_recommended_round": "",
        "overall_status": "completed",
    }
    path = tmp_path / "forged-complete.json"
    path.write_text(json.dumps(report), encoding="utf-8")
    ok, errors = validator.validate_report(path, SCHEMA)
    assert not ok
    assert any("remote SHA" in error or "complete" in error for error in errors)
