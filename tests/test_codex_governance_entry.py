"""Codex entry regressions use disposable commands, never live tool probes."""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def fixture_runner(tmp_path: Path, failure: str = "", code: int = 0):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile(ROOT / "scripts/run_tooling_checks.sh", scripts / "run_tooling_checks.sh")
    runtime = tmp_path / ".venv/bin"
    runtime.mkdir(parents=True)
    interpreter = runtime / "python"
    interpreter.write_text(
        f"#!{sys.executable}\n"
        "import sys,json,os\nfrom pathlib import Path\n"
        "assert os.environ.get('REAL_API_TESTS_ENABLED') == 'false'\n"
        "p=Path('commands.jsonl')\n"
        "with p.open('a') as f:f.write(json.dumps(sys.argv[1:])+'\\n')\n"
        f"raise SystemExit({code} if sys.argv[1]=={failure!r} else 0)\n"
    )
    interpreter.chmod(0o755)
    return scripts / "run_tooling_checks.sh"


def test_codex_keeps_quality_checks_without_cursor_probes(tmp_path: Path):
    runner = fixture_runner(tmp_path)
    result = subprocess.run(["sh", str(runner), "--surface", "codex"], cwd=tmp_path, capture_output=True)
    assert result.returncode == 0
    commands = [json.loads(x) for x in (tmp_path / "commands.jsonl").read_text().splitlines()]
    assert commands == [["scripts/agent_gate.py"], ["scripts/validate_agent_report.py"],
                        ["scripts/check_prompts_refs.py"], ["scripts/check_protocol_standard.py"],
                        ["-m", "pytest", "tests/", "-q"]]


def test_non_gate_failure_is_not_silently_treated_as_warning(tmp_path: Path):
    runner = fixture_runner(tmp_path, "scripts/validate_agent_report.py", 1)
    result = subprocess.run(["sh", str(runner), "--surface", "codex"], cwd=tmp_path, capture_output=True)
    assert result.returncode == 1
    commands = [json.loads(x) for x in (tmp_path / "commands.jsonl").read_text().splitlines()]
    assert commands[-1] == ["scripts/validate_agent_report.py"]


def test_only_documented_gate_warning_can_continue(tmp_path: Path):
    runner = fixture_runner(tmp_path, "scripts/agent_gate.py", 1)
    result = subprocess.run(["sh", str(runner), "--surface", "codex"], cwd=tmp_path, capture_output=True)
    assert result.returncode == 0
    assert json.loads((tmp_path / "commands.jsonl").read_text().splitlines()[-1]) == ["-m", "pytest", "tests/", "-q"]


def test_invalid_surface_does_not_start_any_probe(tmp_path: Path):
    runner = fixture_runner(tmp_path)
    result = subprocess.run(["sh", str(runner), "--surface", "unknown"], cwd=tmp_path, capture_output=True)
    assert result.returncode == 2
    assert not (tmp_path / "commands.jsonl").exists()


def test_state_is_strict_yaml_and_preserves_paused_history():
    text = (ROOT / "governance/round_state.yaml").read_text()
    for event in yaml.parse(text):
        assert not isinstance(event, yaml.AliasEvent)
        assert getattr(event, "anchor", None) is None
    state = yaml.safe_load(text)
    assert state["latest_stats"]["scheduler_paused"] is True
    assert state["latest_stats"]["next_round_id"] is None
    current = state["codex_governance"]
    assert current["task_id"] == "ALL-PROJECTS-CODEX-GOVERNANCE-V1"
    assert current["current_work"]["next_action"]
    declaration = yaml.safe_load((ROOT / "hub.connection.yaml").read_text())
    assert declaration["project_id"] == "light-novel"
    assert declaration["source_refs"] == [{"id": "state", "path": "governance/round_state.yaml", "format": "yaml", "role": "current_state"}]
    assert declaration["metric_export"] == {
        "entry": "scripts/export_hub_metric_snapshot.py",
        "snapshot": ".hub/status.json",
    }
    assert "progress.milestones" not in declaration["mapping"]
    assert declaration["unknown_fields"]["progress.milestones"]
