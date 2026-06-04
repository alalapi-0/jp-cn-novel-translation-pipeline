"""Round 55 CI workflow and package script wiring."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def test_package_json_tooling_scripts():
    data = json.loads((REPO_ROOT / "package.json").read_text(encoding="utf-8"))
    scripts = data.get("scripts", {})
    assert "check:tooling" in scripts
    assert "test:ui" in scripts


def test_ci_workflow_references_tooling():
    workflows = list((REPO_ROOT / ".github" / "workflows").glob("*.yml"))
    assert workflows, "expected at least one workflow under .github/workflows"
    combined = "\n".join(p.read_text(encoding="utf-8") for p in workflows)
    assert "check:tooling" in combined
    assert "test:ui" in combined
