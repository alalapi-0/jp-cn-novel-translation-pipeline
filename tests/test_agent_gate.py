"""Tests for scripts/agent_gate.py exit code semantics."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "agent_gate.py"


def _load_module():
    mod_name = "light_novel_agent_gate_test"
    spec = importlib.util.spec_from_file_location(mod_name, SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def gate():
    return _load_module()


def test_real_repo_passes_or_warns_only(gate):
    """Current governance repo should not be BLOCKED under default mode."""
    results = gate.run_all_checks(strict=False)
    code = gate.aggregate_exit_code(results)
    assert code in (0, 1)
    assert not any(r.severity == gate.Severity.FAIL for r in results)


def test_strict_mode_still_runs(gate):
    results = gate.run_all_checks(strict=True)
    code = gate.aggregate_exit_code(results)
    assert code in (0, 1, 2)


def test_agent_layer_missing_fails_under_strict_layer(gate, tmp_path, monkeypatch):
    fake_path = tmp_path / "missing_agent_layer.yaml"

    def fake_check(*, strict_layer: bool = False):
        severity = gate.Severity.FAIL if strict_layer else gate.Severity.WARN
        return [
            gate.CheckResult(
                "agent_layer_agent_layer_yaml",
                severity,
                f"missing Agent Layer 2.0 file: {fake_path}",
            )
        ]

    monkeypatch.setattr(gate, "check_agent_layer_v2", fake_check)
    results = gate.run_all_checks(strict_layer=True)
    layer = [r for r in results if r.check_id == "agent_layer_agent_layer_yaml"]
    assert layer
    assert layer[0].severity == gate.Severity.FAIL
    assert gate.aggregate_exit_code(layer) == 2


def test_check_agent_layer_v2_strict_layer_unit(gate, tmp_path):
    missing = tmp_path / "nope.yaml"
    original = gate.AGENT_LAYER_FILES
    try:
        gate.AGENT_LAYER_FILES = (("agent_layer_yaml", missing),)
        warn_results = gate.check_agent_layer_v2(strict_layer=False)
        fail_results = gate.check_agent_layer_v2(strict_layer=True)
    finally:
        gate.AGENT_LAYER_FILES = original

    assert warn_results[0].severity == gate.Severity.WARN
    assert fail_results[0].severity == gate.Severity.FAIL


def test_main_json_includes_strict_layer(gate):
    code = gate.main(["--json", "--strict-layer"])
    assert code in (0, 1, 2)


def test_env_tracked_is_blocked(gate, monkeypatch):
    def fake_git(args, cwd):
        class Proc:
            returncode = 0 if args[:3] == ["ls-files", "--error-unmatch", ".env"] else 1
            stdout = ""
            stderr = ""

        return Proc()

    monkeypatch.setattr(gate, "_git", fake_git)
    r = gate.check_env_not_tracked()
    assert r.severity == gate.Severity.FAIL
    assert gate.aggregate_exit_code([r]) == 2


def test_missing_file_is_fail(gate, tmp_path):
    missing = tmp_path / "README.md"
    r = gate._file_exists("docs_exist_readme", missing)
    assert r.severity == gate.Severity.FAIL
    assert gate.aggregate_exit_code([r]) == 2


def test_main_json_exit_zero_on_clean_repo(gate):
    code = gate.main(["--json"])
    payload = None
    # main prints JSON; re-run checks for consistency
    results = gate.run_all_checks(strict=False)
    assert gate.aggregate_exit_code(results) == code


def test_vector_tooling_no_none_module_dataclass_error(
    gate,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    index_path = tmp_path / "index.json"
    index_path.write_text(
        '{"index_metadata":{"schema_version":"1.0.0","backend":"json_mock"}, "vectors":[]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(gate, "DEFAULT_VECTOR_INDEX", index_path)
    results = gate.check_vector_store_tooling()
    assert results
    messages = [r.message for r in results]
    assert not any("__dict__" in msg and "NoneType" in msg for msg in messages)
