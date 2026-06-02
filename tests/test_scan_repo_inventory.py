from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "scan_repo_inventory.py"


def _load():
    name = "scan_repo_inventory_test"
    spec = importlib.util.spec_from_file_location(name, SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def scanner():
    return _load()


def test_build_payload_schema(scanner):
    payload = scanner.build_payload()
    assert payload["schema_version"] == "1.0"
    assert "generated_at" in payload
    assert "inventory" in payload
    assert "counts_summary" in payload
    assert "environment" in payload
    assert payload["counts_summary"]["scripts"] >= 1
    assert payload["counts_summary"]["tests"] >= 1
    assert "python" in payload["environment"]


def test_main_writes_inventory(scanner, tmp_path, monkeypatch):
    inv = tmp_path / "inv.json"
    ex = tmp_path / "ex.json"
    report = tmp_path / "audit.md"
    monkeypatch.setattr(scanner, "INVENTORY_PATH", inv)
    monkeypatch.setattr(scanner, "EXAMPLE_PATH", ex)
    monkeypatch.setattr(scanner, "AUDIT_REPORT_PATH", report)
    code = scanner.main(["--no-report", "--json"])
    assert code == 0
    data = json.loads(inv.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0"
    assert ex.is_file()
