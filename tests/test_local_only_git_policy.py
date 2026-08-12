import hashlib
import os
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
NEVER_COMMIT_CATEGORIES = [
    "real_source_text",
    "real_translation",
    "workspace_runtime_artifacts",
    "secrets",
]
WORKSPACE_VERIFY_COMMAND = "python3 scripts/workspace_file_baseline.py verify --json"
WORKSPACE_FILE_BASELINE_POLICY = {
    "root": "workspace",
    "manifest": ".agent_runtime/inspection_reports/workspace_file_baseline.json",
    "verifier": "scripts/workspace_file_baseline.py",
    "algorithm": "per_file_sha256",
    "workspace_sensitive_tools": {
        "verify_before": WORKSPACE_VERIFY_COMMAND,
        "verify_after": WORKSPACE_VERIFY_COMMAND,
    },
    "drift_is_blocking": True,
    "verifier_error_is_blocking": True,
    "auto_rebaseline": False,
    "create_or_rebaseline_requires_explicit_current_turn_user_authorization": True,
    "full_agent_gate": {
        "live_worktree_execution_prohibited": True,
        "allowed_only_in_disposable_isolated_copy": True,
        "isolated_workspace_reports_runtime_outputs_must_not_write_back": True,
    },
}
ACTIVE_POLICY_DOCUMENTS = [
    "README.md",
    "docs/TOOL_USAGE_POLICY.md",
    "docs/AGENT_RUNBOOK.md",
    "docs/next_agent_execution_protocol.md",
    "docs/non_goals_and_guardrails.md",
    "docs/agent_operating_manual.md",
    "docs/agent_tooling_strategy.md",
    "docs/agent_workflow/runner_agent.md",
    "docs/agent_workflow/continuous_multi_agent_loop.md",
    "docs/CODEX_HANDOFF.md",
    "docs/CODEX_HANDOFF.example.md",
    "docs/CODEX_USAGE.md",
    "docs/AGENT_REPORTING.md",
    "docs/PROMPTS.md",
    "docs/testing/PLAYWRIGHT_VERSION_ALIGNMENT.md",
    "docs/api_provider_strategy.md",
    "docs/cursor_browser_ui_runbook.md",
    "docs/runbooks/mcp_browser_tools_runbook.md",
    "docs/TOOL_INVENTORY.md",
    "docs/agent_gate_and_protocol_check.md",
    "docs/AGENT_ROADMAP.md",
    "docs/index.md",
    "docs/final_state_implementation_roadmap.md",
]
PROTECTED_STANDARD_SHA256 = "968cd20b88c8d4bde47de642e1d873d79e6d53c091ad867d5bd9d22068dcafef"


def load_yaml(relative_path: str) -> dict:
    return yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))


def test_project_declares_user_owned_local_only_finalization() -> None:
    project = load_yaml("project.yaml")
    policy = project["git_finalization_policy"]

    assert policy == {
        "mode": "local_only",
        "auto_stage": False,
        "auto_commit": False,
        "auto_push": False,
        "commit_requires_explicit_current_turn_user_request": True,
        "push_requires_explicit_current_turn_user_authorization": True,
        "push_retry_requires_new_current_turn_user_authorization": True,
        "authorization_sources": {
            "edit_or_build_request": False,
            "round_prompt": False,
        },
        "approved_round_local_completion_allowed": True,
        "dirty_worktree_warning_is_blocking": False,
        "actual_fail_or_blocked_is_blocking": True,
        "never_commit_categories": NEVER_COMMIT_CATEGORIES,
    }

    override = next(
        item
        for item in project["project_overrides"]
        if item["field"] == "agent_policy_standard.git_finalization"
    )
    assert "automatic stage, commit, and push" in override["standard_expectation"]
    assert "completes locally only" in override["override_value"]
    assert "separate explicit current-turn user instruction" in override["override_value"]
    assert override["owner"] == "user"
    assert (
        override["review_trigger"]
        == "Only when the user explicitly changes the local-only policy"
    )


def test_project_records_exact_portable_standard_overrides() -> None:
    project = load_yaml("project.yaml")
    overrides = {item["field"]: item for item in project["project_overrides"]}
    required = {
        "agent_policy_standard.automation_policy",
        "agent_reading_protocol.after_editing_checklist",
        "portability_guide.validation_steps",
        "sync_requirements.drift_detection",
        "governance_files[path=governance/repo_inventory.generated.json].update_frequency",
    }

    assert required <= overrides.keys()
    for field in required:
        override = overrides[field]
        assert override["standard_expectation"]
        assert override["override_value"]
        assert override["reason"]
        assert override["owner"] == "user"
        assert "explicitly changes" in override["review_trigger"]

    assert "disposable isolated copy" in overrides[
        "agent_policy_standard.automation_policy"
    ]["override_value"]
    for field in required - {"agent_policy_standard.automation_policy"}:
        assert any(
            marker in overrides[field]["override_value"]
            for marker in (
                "not implicit",
                "never implicit",
                "opt-in",
                "separately scoped",
                "explicitly owns",
            )
        )


def test_portable_standard_is_unchanged() -> None:
    standard = ROOT / "governance/repo_protocol_standard.yaml"
    assert hashlib.sha256(standard.read_bytes()).hexdigest() == PROTECTED_STANDARD_SHA256


def test_agent_policy_disables_automatic_git_finalization() -> None:
    agent_policy = load_yaml("governance/agent_policy.yaml")
    finalization = agent_policy["git_finalization"]

    assert finalization["mode"] == "local_only"
    assert finalization["automatic_stage"] is False
    assert finalization["automatic_commit"] is False
    assert finalization["automatic_push"] is False
    assert finalization["approved_round_local_completion_allowed"] is True
    assert finalization["commit_requires_explicit_current_turn_user_request"] is True
    assert finalization["push_requires_explicit_current_turn_user_authorization"] is True
    assert finalization["push_retry_requires_new_current_turn_user_authorization"] is True
    assert finalization["authorization_sources"] == {
        "edit_or_build_request": False,
        "round_prompt": False,
    }
    assert finalization["dirty_worktree"] == {
        "scoped_verified_task_changes_are_expected": True,
        "warning_is_blocking": False,
        "actual_fail_or_blocked_is_blocking": True,
    }
    assert finalization["never_commit_categories"] == NEVER_COMMIT_CATEGORIES

    assert agent_policy["commit_policy"]["automatic_stage"] is False
    assert agent_policy["commit_policy"]["automatic_commit"] is False
    assert agent_policy["commit_policy"]["round_prompt_can_authorize"] is False
    assert agent_policy["push_policy"]["automatic_push"] is False
    assert (
        agent_policy["push_policy"][
            "requires_explicit_current_turn_user_authorization"
        ]
        is True
    )
    assert agent_policy["push_policy"]["retry_requires_new_current_turn_user_authorization"] is True


def test_machine_policies_protect_workspace_with_per_file_baseline() -> None:
    project = load_yaml("project.yaml")
    agent_policy = load_yaml("governance/agent_policy.yaml")

    assert project["workspace_file_baseline"] == WORKSPACE_FILE_BASELINE_POLICY
    assert agent_policy["workspace_file_baseline"] == WORKSPACE_FILE_BASELINE_POLICY

    automation_gate = agent_policy["automation_gate"]
    assert automation_gate["live_worktree_execution"] == "prohibited"
    assert automation_gate["isolated_execution_only"] == "disposable_copy"
    assert automation_gate["isolated_outputs_write_back"] is False


def test_policy_documents_match_local_only_authority_boundaries() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    governance = (ROOT / "docs/governance_rules.md").read_text(encoding="utf-8")
    alignment = (ROOT / "docs/repo_protocol_alignment.md").read_text(encoding="utf-8")
    current_policy_docs = agents + "\n" + governance
    all_policy_docs = current_policy_docs + "\n" + alignment

    assert "git add ." not in all_policy_docs
    assert "Round Prompt" in current_policy_docs
    assert "不构成 Git 授权" in current_policy_docs
    assert "用户在当前轮明确要求 commit" in current_policy_docs
    assert "用户在当前轮另行明确授权" in current_policy_docs
    assert "local-only" in agents
    assert "approved-round automatic stage/commit/push" in governance
    assert "dirty worktree warning 是预期、非阻断状态" in governance
    assert "Round Prompt 不再具有任何 Git 授权效力" in alignment
    assert "本条仅保留当轮历史语境" in alignment

    for category in (
        "真实原文",
        "真实译文",
        "workspace runtime artifacts",
        "secrets",
    ):
        assert category in current_policy_docs


def test_policy_documents_require_workspace_verify_and_isolate_full_gate() -> None:
    policy_documents = [
        (ROOT / "AGENTS.md").read_text(encoding="utf-8"),
        (ROOT / "docs/governance_rules.md").read_text(encoding="utf-8"),
        (ROOT / "docs/repo_protocol_alignment.md").read_text(encoding="utf-8"),
    ]

    for document in policy_documents:
        assert "任何已知或可能写入 `workspace` 的工具" in document
        assert WORKSPACE_VERIFY_COMMAND in document
        assert "drift" in document
        assert "硬阻断" in document
        assert "不得自动" in document
        assert "当前轮明确授权" in document
        assert "禁止在真实仓库工作树运行完整" in document
        assert "targeted/read-only checks" in document
        assert "一次性隔离临时副本" in document
        assert "不得写回" in document
        assert "python3 scripts/agent_gate.py" not in document

    combined = "\n".join(policy_documents)
    assert "auto_rebaseline=false" in combined
    assert "workspace/reports/runtime outputs" in combined


def test_machine_layer_routes_full_gate_to_disposable_copy_only() -> None:
    layer = load_yaml("agent_layer.yaml")
    tools = load_yaml("agent_tools.yaml")

    isolated = layer["commands"]["isolated_full_gate"]
    assert isolated == {
        "execution_context": "disposable_copy_only",
        "live_worktree_prohibited": True,
        "output_writeback": False,
        "commands": ["python3 scripts/agent_gate.py --json"],
    }
    assert layer["commands"]["live_targeted_validation"] == [
        "npm run check:tooling"
    ]
    assert layer["agent_policy"]["live_full_gate_prohibited"] is True
    assert (
        layer["agent_policy"][
            "push_requires_separate_explicit_current_turn_user_authorization"
        ]
        is True
    )
    assert (
        layer["agent_policy"]["push_retry_requires_new_current_turn_user_authorization"]
        is True
    )
    assert layer["agent_policy"]["git_authorization_sources"] == {
        "edit_or_build_request": False,
        "round_prompt": False,
    }

    assert tools["policies"]["live_full_gate_prohibited"] is True
    assert tools["policies"]["full_gate_context"] == "disposable_copy_only"
    assert tools["policies"]["full_gate_output_writeback"] is False
    assert (
        tools["policies"]["push_retry_requires_new_current_turn_user_authorization"]
        is True
    )
    assert tools["policies"]["git_authorization_sources"] == {
        "edit_or_build_request": False,
        "round_prompt": False,
    }
    assert tools["task_stage_mapping"]["gate_and_report"]["commands"] == [
        "npm run check:tooling"
    ]
    assert tools["task_stage_mapping"]["gate_and_report"]["full_gate"] == {
        "context": "disposable_copy_only",
        "command": "python3 scripts/agent_gate.py",
        "output_writeback": False,
    }
    active_machine_text = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in ("agent_layer.yaml", "agent_tools.yaml", "docs/TOOL_INVENTORY.md")
    )
    assert "/Users/" not in active_machine_text
    assert "/home/" not in active_machine_text


def test_live_tooling_entrypoint_has_no_hidden_full_or_report_writes() -> None:
    package = (ROOT / "package.json").read_text(encoding="utf-8")
    script = (ROOT / "scripts/run_tooling_checks.sh").read_text(encoding="utf-8")

    assert '"check:tooling": "sh scripts/run_tooling_checks.sh"' in package
    for forbidden in (
        "agent_gate.py",
        "scripts/tool_probe.py",
        "sync_agent_tools_from_probe.py",
        "scan_repo_inventory.py",
        "check_protocol_standard.py",
    ):
        assert forbidden not in script
    assert script.count("workspace_file_baseline.py verify --json") == 1
    assert script.count("verify_workspace") >= 3
    assert "classify_workspace_state" in script
    assert "verify_tracked_workspace_skeleton" in script
    assert "--untracked-files=all" in script
    assert "--ignored=matching -- workspace/" in script
    assert "tests/test_workspace_file_baseline.py" in script
    assert "tests/test_local_only_git_policy.py" in script
    assert "tests/test_tool_probe.py" in script
    assert "tests/ -q" not in script


def test_active_policy_docs_subordinate_full_gate_and_prompt_git_grants() -> None:
    documents = {
        path: (ROOT / path).read_text(encoding="utf-8")
        for path in ACTIVE_POLICY_DOCUMENTS
    }
    combined = "\n".join(documents.values())

    assert "Round Prompt、edit/build 请求不授权 Git" in combined
    assert "commit 与 push" in combined
    assert "该 Prompt 由用户授权每轮 commit + push" not in combined
    for path, document in documents.items():
        if "python3 scripts/agent_gate.py" in document:
            assert (
                "disposable isolated copy" in document
                or "一次性隔离副本" in document
            ), path
        if "tool_probe.py --sync-docs" in document:
            assert any(
                marker in document
                for marker in ("明确拥有", "separately scoped", "独立写操作")
            ), path
    assert "历史、非执行性路线图" in documents["docs/AGENT_ROADMAP.md"]
    assert "历史/快照（无当前执行或授权效力）" in documents["docs/index.md"]
    assert "/Users/" not in combined


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    return subprocess.run(
        [
            "git",
            "-c",
            "core.hooksPath=/dev/null",
            "-c",
            "init.templateDir=",
            *args,
        ],
        cwd=repo,
        env=env,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _make_tooling_fixture(
    tmp_path: Path,
    state: str,
    *,
    git_available: bool = True,
) -> tuple[Path, dict[str, str], Path]:
    repo = tmp_path / "repo"
    scripts = repo / "scripts"
    scripts.mkdir(parents=True)
    source_script = ROOT / "scripts/run_tooling_checks.sh"
    target_script = scripts / "run_tooling_checks.sh"
    target_script.write_bytes(source_script.read_bytes())
    target_script.chmod(0o755)

    fake_python = tmp_path / "fake-python"
    fake_python.write_text(
        textwrap.dedent(
            """\
            #!/bin/sh
            printf '%s\\n' "$*" >> "$TOOLING_TEST_LOG"
            case "$*" in
              *"workspace_file_baseline.py verify"*)
                verify_call=$(grep -c 'workspace_file_baseline.py verify' "$TOOLING_TEST_LOG")
                if [ "${FAIL_VERIFY_CALL:-0}" = "$verify_call" ]; then
                  exit 9
                fi
                ;;
              *"validate_agent_report.py"*)
                if [ "${CREATE_IGNORED_DURING_CHECK:-0}" = "1" ]; then
                  mkdir -p workspace/runtime
                  printf '%s\\n' generated > workspace/runtime/generated.json
                fi
                if [ "${FAIL_INTERMEDIATE:-0}" = "1" ]; then
                  exit 7
                fi
                if [ -n "${SIGNAL_PARENT_DURING_CHECK:-}" ]; then
                  kill "-${SIGNAL_PARENT_DURING_CHECK}" "$PPID"
                fi
                ;;
            esac
            exit 0
            """
        ),
        encoding="utf-8",
    )
    fake_python.chmod(0o755)
    log = tmp_path / "tooling.log"
    env = dict(os.environ)
    env.update(
        {
            "PYTHON": str(fake_python),
            "PYTEST": str(fake_python),
            "TOOLING_TEST_LOG": str(log),
        }
    )

    if git_available:
        _git(repo, "init", "-q")
        (repo / ".gitignore").write_text(
            ".agent_runtime/inspection_reports/*\nworkspace/runtime/\n",
            encoding="utf-8",
        )
        (repo / "control.txt").write_text("control\n", encoding="utf-8")
        tracked = [".gitignore", "control.txt"]
        if state in {"skeleton", "populated"}:
            workspace = repo / "workspace"
            workspace.mkdir()
            (workspace / "README.md").write_text("tracked skeleton\n", encoding="utf-8")
            tracked.append("workspace/README.md")
        _git(repo, "add", "--", *tracked)
        _git(
            repo,
            "-c",
            "user.name=Control Test",
            "-c",
            "user.email=control-test@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-qm",
            "fixture",
        )

    if state == "populated":
        manifest = repo / ".agent_runtime/inspection_reports/workspace_file_baseline.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("{}\n", encoding="utf-8")
    elif state == "manifest_only":
        manifest = repo / ".agent_runtime/inspection_reports/workspace_file_baseline.json"
        manifest.parent.mkdir(parents=True)
        manifest.write_text("{}\n", encoding="utf-8")
    elif state == "no_tracked_skeleton":
        (repo / "workspace").mkdir()
    elif state == "skeleton" and not git_available:
        (repo / "workspace").mkdir()

    return repo, env, log


def _run_tooling(repo: Path, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["sh", "scripts/run_tooling_checks.sh"],
        cwd=repo,
        env=env,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _logged_calls(log: Path) -> list[str]:
    if not log.exists():
        return []
    return log.read_text(encoding="utf-8").splitlines()


def test_tooling_populated_state_verifies_before_and_after(tmp_path: Path) -> None:
    repo, env, log = _make_tooling_fixture(tmp_path, "populated")
    result = _run_tooling(repo, env)

    assert result.returncode == 0
    assert sum("workspace_file_baseline.py verify" in call for call in _logged_calls(log)) == 2


def test_tooling_populated_state_reverifies_after_intermediate_failure(tmp_path: Path) -> None:
    repo, env, log = _make_tooling_fixture(tmp_path, "populated")
    env["FAIL_INTERMEDIATE"] = "1"
    result = _run_tooling(repo, env)

    assert result.returncode == 7
    assert sum("workspace_file_baseline.py verify" in call for call in _logged_calls(log)) == 2


@pytest.mark.parametrize(("signal_name", "expected_status"), [("INT", 130), ("TERM", 143)])
def test_tooling_populated_state_reverifies_after_signal(
    tmp_path: Path,
    signal_name: str,
    expected_status: int,
) -> None:
    repo, env, log = _make_tooling_fixture(tmp_path, "populated")
    env["SIGNAL_PARENT_DURING_CHECK"] = signal_name
    result = _run_tooling(repo, env)

    assert result.returncode == expected_status
    assert sum("workspace_file_baseline.py verify" in call for call in _logged_calls(log)) == 2


def test_tooling_post_verification_failure_is_overall_failure(tmp_path: Path) -> None:
    repo, env, log = _make_tooling_fixture(tmp_path, "populated")
    env["FAIL_VERIFY_CALL"] = "2"
    result = _run_tooling(repo, env)

    assert result.returncode == 9
    assert sum("workspace_file_baseline.py verify" in call for call in _logged_calls(log)) == 2


def test_tooling_both_absent_clean_checkout_stays_absent(tmp_path: Path) -> None:
    repo, env, _log = _make_tooling_fixture(tmp_path, "empty")
    result = _run_tooling(repo, env)

    assert result.returncode == 0
    assert not (repo / "workspace").exists()
    assert not (repo / ".agent_runtime/inspection_reports/workspace_file_baseline.json").exists()


def test_tooling_both_absent_fails_if_check_creates_workspace(tmp_path: Path) -> None:
    repo, env, _log = _make_tooling_fixture(tmp_path, "empty")
    env["CREATE_IGNORED_DURING_CHECK"] = "1"
    result = _run_tooling(repo, env)

    assert result.returncode == 2
    assert "workspace state changed" in result.stderr


def test_tooling_tracked_clean_skeleton_succeeds(tmp_path: Path) -> None:
    repo, env, log = _make_tooling_fixture(tmp_path, "skeleton")
    result = _run_tooling(repo, env)

    assert result.returncode == 0
    assert not any("workspace_file_baseline.py verify" in call for call in _logged_calls(log))


@pytest.mark.parametrize("mutation", ["modified", "deleted", "type_changed"])
def test_tooling_rejects_tracked_skeleton_diff(tmp_path: Path, mutation: str) -> None:
    repo, env, _log = _make_tooling_fixture(tmp_path, "skeleton")
    tracked = repo / "workspace/README.md"
    if mutation == "modified":
        tracked.write_text("modified\n", encoding="utf-8")
    elif mutation == "deleted":
        tracked.unlink()
    else:
        tracked.unlink()
        tracked.symlink_to("../control.txt")

    result = _run_tooling(repo, env)
    assert result.returncode == 2
    assert "incomplete or dirty" in result.stderr


@pytest.mark.parametrize("kind", ["untracked", "ignored"])
def test_tooling_rejects_runtime_or_untracked_skeleton_entry(tmp_path: Path, kind: str) -> None:
    repo, env, _log = _make_tooling_fixture(tmp_path, "skeleton")
    if kind == "untracked":
        (repo / "workspace/new.txt").write_text("new\n", encoding="utf-8")
    else:
        runtime = repo / "workspace/runtime"
        runtime.mkdir()
        (runtime / "generated.json").write_text("{}\n", encoding="utf-8")

    result = _run_tooling(repo, env)
    assert result.returncode == 2
    assert "incomplete or dirty" in result.stderr


def test_tooling_rejects_workspace_without_tracked_skeleton(tmp_path: Path) -> None:
    repo, env, _log = _make_tooling_fixture(tmp_path, "no_tracked_skeleton")
    result = _run_tooling(repo, env)

    assert result.returncode == 2
    assert "incomplete or dirty" in result.stderr


def test_tooling_rejects_skeleton_when_git_metadata_is_unavailable(tmp_path: Path) -> None:
    repo, env, _log = _make_tooling_fixture(
        tmp_path, "skeleton", git_available=False
    )
    result = _run_tooling(repo, env)

    assert result.returncode == 2
    assert "incomplete or dirty" in result.stderr


def test_tooling_rejects_manifest_without_workspace(tmp_path: Path) -> None:
    repo, env, log = _make_tooling_fixture(tmp_path, "manifest_only")
    result = _run_tooling(repo, env)

    assert result.returncode == 2
    assert _logged_calls(log) == []


def test_tooling_skeleton_failure_still_detects_exit_time_runtime_creation(
    tmp_path: Path,
) -> None:
    repo, env, _log = _make_tooling_fixture(tmp_path, "skeleton")
    env["FAIL_INTERMEDIATE"] = "1"
    env["CREATE_IGNORED_DURING_CHECK"] = "1"
    result = _run_tooling(repo, env)

    assert result.returncode == 2
    assert "workspace state changed" in result.stderr
