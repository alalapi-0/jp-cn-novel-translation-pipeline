import hashlib
import json
import os
import subprocess
import textwrap
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
NEVER_COMMIT_CATEGORIES = [
    "real_source_text",
    "full_real_translation",
    "workspace_runtime_artifacts",
    "artifacts",
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
    ".cursor/rules/agent-layer.mdc",
    ".cursor/rules/safety-gates.mdc",
    ".cursor/rules/tool-usage.mdc",
    "README.md",
    "docs/AGENT_SAFETY.md",
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
    "docs/git_safe_cohort_delivery.md",
    "docs/governance_rules.md",
    "docs/micro_round_runner_design.md",
    "docs/agent_skills/mcp_usage_skill.md",
    "docs/translation_consistency_protocol.md",
    "docs/prompts/CONTINUOUS_FS_ADVANCE_PROMPT.md",
    "docs/prompts/CURSOR_UI_IMPLEMENTATION_PROMPT.md",
    "docs/repo_protocol_alignment.md",
]
PROTECTED_STANDARD_SHA256 = "968cd20b88c8d4bde47de642e1d873d79e6d53c091ad867d5bd9d22068dcafef"


def load_yaml(relative_path: str) -> dict:
    return yaml.safe_load((ROOT / relative_path).read_text(encoding="utf-8"))


def test_project_requires_verified_remote_git_safe_cohort_delivery() -> None:
    project = load_yaml("project.yaml")
    policy = project["git_finalization_policy"]

    assert policy == {
        "mode": "required_verified_remote_delivery",
        "unit": "git_safe_cohort",
        "max_cohorts_per_round": 1,
        "standing_delivery_authority": "standing_git_safe_cohort_policy_v1",
        "auto_finalize_approved_git_safe_cohort": True,
        "target": {
            "remote": "origin",
            "branch": "codex/light-novel-governance-closure-20260813",
            "default_branch": "main",
            "remote_must_preexist": True,
            "branch_must_preexist": True,
            "fetch_and_push_url_must_match": True,
            "fresh_remote_head_must_match_default_branch": True,
        },
        "authorization_sources": {
            "standing_repository_policy": True,
            "edit_or_build_request": False,
            "round_prompt": False,
        },
        "prerequisites": {
            "exact_hash_bound_plan": True,
            "registered_plan_sha256_required_at_execution": True,
            "approval_subject_sha256_required": True,
            "content_safety_review_required": True,
            "scoped_validation_required": True,
            "required_approvals_satisfied": True,
            "prior_remote_sha_must_match_base": True,
        },
        "staging": {
            "exact_paths_only": True,
            "preexisting_index_must_be_empty": True,
            "broad_staging_forbidden": True,
        },
        "delivery": {
            "commit_required": True,
            "push_required": True,
            "force_push_forbidden": True,
            "verify_remote_sha": True,
        },
        "completion": {
            "approved_local_only_completion_allowed": False,
            "requires_remote_sha_match": True,
            "next_cohort_blocked_until_verified": True,
        },
        "push_failure": {
            "preserve_local_commit": True,
            "mark_cohort_incomplete": True,
            "blind_retry_forbidden": True,
            "same_target_retry_requires_state_or_method_change": True,
            "retry_change_evidence_required": True,
            "retry_evidence_must_bind_plan": True,
            "retry_evidence_reuse_forbidden": True,
        },
        "authority_expansion": {
            "remote_change_requires_new_user_authorization": True,
            "branch_change_requires_new_user_authorization": True,
            "effect_expansion_requires_new_user_authorization": True,
        },
        "actual_fail_or_blocked_is_blocking": True,
        "never_commit_categories": NEVER_COMMIT_CATEGORIES,
    }

    override = next(
        item
        for item in project["project_overrides"]
        if item["field"] == "agent_policy_standard.git_finalization"
    )
    assert "automatic stage, commit, and push" in override["standard_expectation"]
    assert "hash-bound finalizer" in override["override_value"]
    assert "verify the remote SHA" in override["override_value"]
    assert override["owner"] == "user"
    assert "registered remote" in override["review_trigger"]


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


def test_agent_policy_matches_required_remote_finalization() -> None:
    agent_policy = load_yaml("governance/agent_policy.yaml")
    finalization = agent_policy["git_finalization"]

    assert finalization["mode"] == "required_verified_remote_delivery"
    assert finalization["unit"] == "git_safe_cohort"
    assert finalization["max_cohorts_per_round"] == 1
    assert finalization["standing_delivery_authority"] == "standing_git_safe_cohort_policy_v1"
    assert finalization["automatic_finalizer"] == "scripts/git_safe_cohort_finalizer.py"
    assert finalization["auto_finalize_approved_git_safe_cohort"] is True
    assert finalization["target"] == {
        "remote": "origin",
        "branch": "codex/light-novel-governance-closure-20260813",
        "default_branch": "main",
        "remote_must_preexist": True,
        "branch_must_preexist": True,
        "fetch_and_push_url_must_match": True,
        "fresh_remote_head_must_match_default_branch": True,
    }
    assert finalization["authorization_sources"] == {
        "standing_repository_policy": True,
        "edit_or_build_request": False,
        "round_prompt": False,
    }
    assert finalization["staging"]["exact_paths_only"] is True
    assert finalization["staging"]["preexisting_index_must_be_empty"] is True
    assert finalization["staging"]["broad_staging_forbidden"] is True
    assert finalization["delivery"] == {
        "commit_required": True,
        "push_required": True,
        "force_push_forbidden": True,
        "verify_remote_sha": True,
    }
    assert finalization["completion"]["approved_local_only_completion_allowed"] is False
    assert finalization["completion"]["requires_remote_sha_match"] is True
    assert finalization["completion"]["next_cohort_blocked_until_verified"] is True
    assert finalization["push_failure"]["preserve_local_commit"] is True
    assert finalization["push_failure"]["blind_retry_forbidden"] is True
    assert finalization["never_commit_categories"] == NEVER_COMMIT_CATEGORIES

    assert agent_policy["commit_policy"]["automatic_stage"] == "approved_git_safe_cohort_only"
    assert agent_policy["commit_policy"]["automatic_commit"] == "approved_git_safe_cohort_only"
    assert agent_policy["commit_policy"]["standing_repository_policy_can_authorize"] is True
    assert agent_policy["commit_policy"]["round_prompt_can_authorize"] is False
    assert agent_policy["push_policy"]["automatic_push"] == "approved_git_safe_cohort_only"
    assert agent_policy["push_policy"]["standing_repository_policy_can_authorize"] is True
    assert agent_policy["push_policy"]["verify_remote_sha"] is True
    assert agent_policy["push_policy"]["blind_retry_forbidden"] is True
    assert agent_policy["push_policy"]["target_change_requires_new_user_authorization"] is True


def test_machine_git_delivery_surfaces_have_exact_semantic_parity() -> None:
    project_policy = load_yaml("project.yaml")["git_finalization_policy"]
    agent_policy = load_yaml("governance/agent_policy.yaml")["git_finalization"]
    comparable_project = dict(project_policy)
    comparable_project.pop("actual_fail_or_blocked_is_blocking")
    comparable_agent = dict(agent_policy)
    comparable_agent.pop("automatic_finalizer")
    assert comparable_project == comparable_agent

    layer_policy = load_yaml("agent_layer.yaml")["agent_policy"]
    tools_policy = load_yaml("agent_tools.yaml")["policies"]
    git_keys = {
        "git_finalization_mode",
        "git_safe_cohort_finalizer",
        "auto_finalize_approved_git_safe_cohort",
        "registered_remote",
        "registered_branch",
        "default_branch_push_forbidden",
        "exact_hash_bound_plan_required",
        "registered_plan_sha256_required_at_execution",
        "approval_subject_sha256_required",
        "content_safety_review_required",
        "exact_path_staging_only",
        "remote_sha_match_required_for_completion",
        "next_cohort_blocked_until_remote_verified",
        "blind_push_retry_forbidden",
        "same_target_retry_requires_state_or_method_change",
        "retry_change_evidence_required",
        "retry_evidence_reuse_forbidden",
        "target_change_requires_new_user_authorization",
        "git_authorization_sources",
    }
    assert {key: layer_policy[key] for key in git_keys} == {
        key: tools_policy[key] for key in git_keys
    }


def test_machine_policies_protect_workspace_with_per_file_baseline() -> None:
    project = load_yaml("project.yaml")
    agent_policy = load_yaml("governance/agent_policy.yaml")

    assert project["workspace_file_baseline"] == WORKSPACE_FILE_BASELINE_POLICY
    assert agent_policy["workspace_file_baseline"] == WORKSPACE_FILE_BASELINE_POLICY

    automation_gate = agent_policy["automation_gate"]
    assert automation_gate["live_worktree_execution"] == "prohibited"
    assert automation_gate["isolated_execution_only"] == "disposable_copy"
    assert automation_gate["isolated_outputs_write_back"] is False


def test_policy_documents_require_remote_verified_git_safe_cohort_delivery() -> None:
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    governance = (ROOT / "docs/governance_rules.md").read_text(encoding="utf-8")
    alignment = (ROOT / "docs/repo_protocol_alignment.md").read_text(encoding="utf-8")
    current_policy_docs = agents + "\n" + governance
    all_policy_docs = current_policy_docs + "\n" + alignment

    assert "禁止 `git add .`" in all_policy_docs
    assert "`git add -A`" in all_policy_docs
    assert "Round Prompt" in current_policy_docs
    assert "不能扩大" in current_policy_docs
    assert "scripts/git_safe_cohort_finalizer.py" in current_policy_docs
    assert "hash-bound" in current_policy_docs
    assert "fresh" in current_policy_docs
    assert "远端 SHA" in current_policy_docs
    assert "required_verified_remote_delivery" in governance
    assert "已批准但只留在本地不再是完成状态" in alignment
    assert "本条仅保留当轮历史语境" in alignment
    for stale in (
        "user-owned `local_only`",
        "用户在当前轮明确要求 commit",
        "commit 和 push 必须分别",
        "push 必须由用户在当前轮另行明确授权",
    ):
        assert stale not in current_policy_docs

    for category in (
        "真实原文",
        "完整真实译文",
        "workspace runtime artifacts",
        "artifacts",
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
    assert layer["agent_policy"]["git_finalization_mode"] == "required_verified_remote_delivery"
    assert layer["agent_policy"]["git_safe_cohort_finalizer"] == "scripts/git_safe_cohort_finalizer.py"
    assert layer["agent_policy"]["auto_finalize_approved_git_safe_cohort"] is True
    assert layer["agent_policy"]["registered_remote"] == "origin"
    assert layer["agent_policy"]["registered_branch"] == "codex/light-novel-governance-closure-20260813"
    assert layer["agent_policy"]["exact_hash_bound_plan_required"] is True
    assert layer["agent_policy"]["registered_plan_sha256_required_at_execution"] is True
    assert layer["agent_policy"]["approval_subject_sha256_required"] is True
    assert layer["agent_policy"]["content_safety_review_required"] is True
    assert layer["agent_policy"]["remote_sha_match_required_for_completion"] is True
    assert layer["agent_policy"]["blind_push_retry_forbidden"] is True
    assert layer["agent_policy"]["retry_change_evidence_required"] is True
    assert layer["agent_policy"]["retry_evidence_reuse_forbidden"] is True
    assert layer["agent_policy"]["git_authorization_sources"] == {
        "standing_repository_policy": True,
        "edit_or_build_request": False,
        "round_prompt": False,
    }

    assert tools["policies"]["live_full_gate_prohibited"] is True
    assert tools["policies"]["full_gate_context"] == "disposable_copy_only"
    assert tools["policies"]["full_gate_output_writeback"] is False
    assert tools["policies"]["git_finalization_mode"] == "required_verified_remote_delivery"
    assert tools["policies"]["git_safe_cohort_finalizer"] == "scripts/git_safe_cohort_finalizer.py"
    assert tools["policies"]["auto_finalize_approved_git_safe_cohort"] is True
    assert tools["policies"]["registered_remote"] == "origin"
    assert tools["policies"]["registered_branch"] == "codex/light-novel-governance-closure-20260813"
    assert tools["policies"]["remote_sha_match_required_for_completion"] is True
    assert tools["policies"]["blind_push_retry_forbidden"] is True
    assert tools["policies"]["registered_plan_sha256_required_at_execution"] is True
    assert tools["policies"]["approval_subject_sha256_required"] is True
    assert tools["policies"]["content_safety_review_required"] is True
    assert tools["policies"]["retry_change_evidence_required"] is True
    assert tools["policies"]["retry_evidence_reuse_forbidden"] is True
    assert tools["policies"]["git_authorization_sources"] == {
        "standing_repository_policy": True,
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


def test_active_policy_docs_subordinate_full_gate_and_require_git_delivery() -> None:
    documents = {
        path: (ROOT / path).read_text(encoding="utf-8")
        for path in ACTIVE_POLICY_DOCUMENTS
    }
    combined = "\n".join(documents.values())

    assert "Prompt" in combined
    assert "不能扩大" in combined or "cannot expand" in combined
    assert "git_safe_cohort_finalizer.py" in combined
    assert "remote SHA" in combined or "远端 SHA" in combined
    assert "该 Prompt 由用户授权每轮 commit + push" not in combined
    for stale in (
        "commit 与 push 分别需要用户当前轮明确授权",
        "commit 和 push 必须分别取得用户当前轮明确授权",
        "commit and push each require separate explicit current-turn",
        "Do not auto commit/push",
        "user-owned `local_only`",
    ):
        assert stale not in combined
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
    assert "报告与历史边界" in documents["docs/index.md"]
    assert "/Users/" not in combined


def test_current_state_and_report_block_completion_and_next_until_remote_sha() -> None:
    state = load_yaml("governance/round_state.yaml")
    report = json.loads(
        (ROOT / "reports/current-cohort-report.json").read_text(encoding="utf-8")
    )
    roles = load_yaml("governance/file_role_map.yaml")["round_reporting"]

    assert state["policy_version"] == "git_safe_cohort_delivery_v1"
    assert state["status"] in {"work_in_progress", "candidate_ready_for_delivery"}
    assert state["cohort_status"] == state["status"]
    assert state["git_delivery"]["remote_sha_verified"] is False
    assert state["git_delivery"]["next_cohort_blocked"] is True
    assert state["next_recommended_round"] == ""
    assert state["prior_product_round"]["status"] == "completed"
    assert report["cohort_status"] in {
        "work_in_progress",
        "candidate_ready_for_delivery",
    }
    assert report["git_delivery"]["remote_sha_verified"] is False
    assert report["next_recommended_round"] == ""
    assert roles == [
        {
            "path": "reports/current-cohort-report.json",
            "role": "current_git_safe_cohort_candidate_report",
            "completion_authority": False,
        },
        {
            "path": "reports/latest-agent-report.json",
            "role": "protected_pre_policy_historical_snapshot",
            "treat_as_authority": False,
        },
    ]
    cursor_routes = "\n".join(
        (ROOT / path).read_text(encoding="utf-8")
        for path in (
            ".cursor/rules/agent-layer.mdc",
            ".cursor/rules/tool-usage.mdc",
        )
    )
    assert "reports/current-cohort-report.json" in cursor_routes
    assert "Write `reports/latest-agent-report.json`" not in cursor_routes
    assert "in `reports/latest-agent-report.json`" not in cursor_routes


def test_consistency_product_finalizer_cannot_bypass_cohort_reporting_gate() -> None:
    source = (ROOT / "scripts/finalize_consistency_run.py").read_text(
        encoding="utf-8"
    )
    protocol = (ROOT / "docs/translation_consistency_protocol.md").read_text(
        encoding="utf-8"
    )

    assert "build_template(" in source
    assert 'cohort_status="candidate_ready_for_delivery"' in source
    assert '"next_recommended_round": ""' in source
    assert "validate_report_dict(current_cohort_report)" in source
    assert "write_report_file(current_cohort_report)" in source
    assert '"product_status": "consistency_completed"' in source
    assert '"git_cohort_status": "candidate_ready_for_delivery"' in source
    assert "_write_json(REPO_ROOT / \"reports\"" not in source
    assert "_append_jsonl(" not in source
    assert "must not mark the Git cohort complete" in protocol


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
