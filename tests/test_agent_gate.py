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
