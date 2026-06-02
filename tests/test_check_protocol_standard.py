from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "check_protocol_standard.py"


def _load():
    name = "check_protocol_standard_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def checker():
    return _load()


def test_real_repo_passes_or_warns(checker):
    results = checker.run_all_checks()
    code = checker.aggregate_exit_code(results)
    assert code in (0, 1)
    assert not any(r.severity == checker.Severity.FAIL for r in results)


def test_version_mismatch_fails(checker, monkeypatch, tmp_path):
    proto = tmp_path / "p.yaml"
    proj = tmp_path / "j.yaml"
    proto.write_text('protocol:\n  version: "0.1.0"\n', encoding="utf-8")
    proj.write_text('protocol_standard:\n  version: "0.3.0"\n', encoding="utf-8")
    monkeypatch.setattr(checker, "PROTOCOL_PATH", proto)
    monkeypatch.setattr(checker, "PROJECT_PATH", proj)
    r = checker.check_protocol_version_alignment()
    assert r.severity == checker.Severity.FAIL
