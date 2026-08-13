"""Tests for scripts/write_agent_report.py."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "write_agent_report.py"
SCHEMA = REPO_ROOT / "schemas" / "agent_round_report.schema.json"


def _load_module():
    mod_name = "light_novel_write_agent_report_test"
    spec = importlib.util.spec_from_file_location(mod_name, SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def writer():
    return _load_module()


def test_build_template_has_required_fields(writer):
    report = writer.build_template(round_id="AL-TEST", goal="unit test")
    ok, errors = writer.validate_report_dict(report)
    assert ok, errors
    assert report["round_id"] == "AL-TEST"
    assert report["severity_summary"]["p0"] == 0
    assert report["policy_version"] == "git_safe_cohort_delivery_v1"
    assert report["cohort_status"] == "work_in_progress"
    assert report["git_delivery"] == {
        "status": "work_in_progress",
        "remote_sha_verified": False,
        "completion_authority": "fresh_remote_sha_and_ignored_delivery_receipt",
    }
    assert report["next_recommended_round"] == ""


def test_merge_report_nested_severity(writer):
    base = writer.build_template(round_id="AL-001", goal="a")
    merged = writer.merge_report(base, {"severity_summary": {"p3": 2}, "goal": "b"})
    assert merged["goal"] == "b"
    assert merged["severity_summary"]["p3"] == 2
    assert merged["severity_summary"]["p0"] == 0


def test_write_and_validate_roundtrip(writer, tmp_path, monkeypatch):
    out = tmp_path / "report.json"
    audit = tmp_path / "audit.jsonl"
    monkeypatch.setattr(writer, "DEFAULT_REPORT", out)
    monkeypatch.setattr(writer, "AUDIT_LOG", audit)

    code = writer.main(
        [
            "--round-id",
            "AL-013",
            "--goal",
            "writer helper test",
            "--next",
            "AL-014",
            "--cohort-status",
            "not_applicable",
            "--write",
            "--append-audit",
            "test audit line",
            "--json",
        ]
    )
    assert code == 0
    assert out.is_file()
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["round_id"] == "AL-013"
    assert data["policy_version"] == "git_safe_cohort_delivery_v1"
    assert data["cohort_status"] == "not_applicable"
    assert data["git_delivery"]["status"] == "not_applicable"
    assert data["git_delivery"]["remote_sha_verified"] is False
    audit_line = json.loads(audit.read_text(encoding="utf-8").strip().splitlines()[-1])
    assert audit_line["summary"] == "test audit line"


def test_merge_json_file(writer, tmp_path):
    patch_path = tmp_path / "patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "tools_used": [{"tool": "shell", "purpose": "test", "result": "ok"}],
                "changed_files": ["scripts/foo.py"],
            }
        ),
        encoding="utf-8",
    )
    out = tmp_path / "out.json"
    code = writer.main(
        [
            "--round-id",
            "AL-013",
            "--goal",
            "merge test",
            "--merge",
            str(patch_path),
            "--output",
            str(out),
            "--write",
        ]
    )
    assert code == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["tools_used"][0]["tool"] == "shell"
    assert "scripts/foo.py" in data["changed_files"]
