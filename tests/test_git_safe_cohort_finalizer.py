from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts/git_safe_cohort_finalizer.py"
MODULE_SPEC = importlib.util.spec_from_file_location("git_safe_cohort_finalizer_test", MODULE_PATH)
assert MODULE_SPEC and MODULE_SPEC.loader
finalizer = importlib.util.module_from_spec(MODULE_SPEC)
sys.modules[MODULE_SPEC.name] = finalizer
MODULE_SPEC.loader.exec_module(finalizer)


def _git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    result = subprocess.run(
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
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check:
        assert result.returncode == 0, result.stderr
    return result


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _remote_sha(repo: Path, branch: str = "task/delivery") -> str:
    result = _git(repo, "ls-remote", "--heads", "origin", f"refs/heads/{branch}")
    return result.stdout.split()[0]


def _fixture(tmp_path: Path) -> tuple[Path, Path]:
    remote = tmp_path / "remote.git"
    remote.mkdir()
    _git(remote, "init", "--bare", "-q")
    _git(remote, "symbolic-ref", "HEAD", "refs/heads/main")

    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q", "-b", "main")
    _git(repo, "config", "user.name", "Cohort Test")
    _git(repo, "config", "user.email", "cohort@example.invalid")
    (repo / ".gitignore").write_text(
        ".agent_runtime/inspection_reports/*\n.agent_runtime/locks/*\nworkspace/\nartifacts/\n.env*\n",
        encoding="utf-8",
    )
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    _git(repo, "add", "--", ".gitignore", "README.md")
    _git(repo, "commit", "-qm", "base")
    _git(repo, "remote", "add", "origin", str(remote))
    _git(repo, "push", "-q", "-u", "origin", "main")
    _git(repo, "switch", "-q", "-c", "task/delivery")
    _git(repo, "push", "-q", "-u", "origin", "task/delivery")
    _git(repo, "remote", "set-head", "origin", "main")
    return repo, remote


def _entry(repo: Path, relative: str, *, state_value: str = "added", classification: str = "code") -> dict:
    path = repo / relative
    if state_value == "deleted":
        return {
            "path": relative,
            "state": "deleted",
            "mode": "absent",
            "sha256": None,
            "classification": classification,
        }
    return {
        "path": relative,
        "state": state_value,
        "mode": f"0{stat.S_IMODE(path.lstat().st_mode):03o}",
        "sha256": _sha256(path),
        "classification": classification,
    }


def _plan_dict(
    repo: Path,
    entries: list[dict],
    *,
    lane: str = "direct",
    branch: str = "task/delivery",
    default_branch: str = "main",
    remote: str = "origin",
) -> dict:
    approvals = {
        "validation": "passed",
        "judge": "not_required",
        "governor": "not_required",
        "content_safety": "passed",
        "approval_subject_sha256": "",
        "evidence": ["pytest:passed", "diff-check:passed"],
    }
    if lane == "reviewed":
        approvals["judge"] = "passed"
    elif lane == "governed":
        approvals["judge"] = "passed"
        approvals["governor"] = "approved"
    remote_url = _git(repo, "remote", "get-url", "origin").stdout.strip()
    payload = {
        "schema": finalizer.PLAN_SCHEMA,
        "cohort_id": "cohort-001",
        "base_sha": _git(repo, "rev-parse", "HEAD").stdout.strip(),
        "remote": remote,
        "remote_url_sha256": hashlib.sha256(remote_url.encode()).hexdigest(),
        "branch": branch,
        "default_branch": default_branch,
        "commit_message": "test: deliver one Git-safe cohort",
        "review_lane": lane,
        "approvals": approvals,
        "delivery_authority": finalizer.DELIVERY_AUTHORITY,
        "paths": entries,
    }
    payload["approvals"]["approval_subject_sha256"] = finalizer._approval_subject_digest(
        payload
    )
    return payload


def _load_plan(tmp_path: Path, payload: dict) -> finalizer.CohortPlan:
    plan_path = tmp_path / "cohort-plan.json"
    plan_path.write_text(json.dumps(payload), encoding="utf-8")
    return finalizer.load_plan(
        plan_path,
        expected_plan_sha256=finalizer._canonical_digest(payload),
        allowed_remote=payload.get("remote", "origin"),
        allowed_branch=payload.get("branch", "task/delivery"),
        allowed_default_branch=payload.get("default_branch", "main"),
    )


def _retry_evidence(
    plan: finalizer.CohortPlan,
    *,
    condition: str,
    change_id: str,
    before: str,
    after: str,
    previous_attempt_updated_at: str,
) -> finalizer.RetryChangeEvidence:
    previous = datetime.fromisoformat(previous_attempt_updated_at.replace("Z", "+00:00"))
    recorded_at = (previous + timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
    payload = {
        "schema": "git_safe_cohort_retry_change_v1",
        "cohort_id": plan.cohort_id,
        "plan_sha256": plan.digest,
        "condition": condition,
        "change_id": change_id,
        "recorded_at": recorded_at,
        "previous_attempt_updated_at": previous_attempt_updated_at,
        "before_fingerprint": before,
        "after_fingerprint": after,
        "summary": "Synthetic test records a real fixture state change",
    }
    return finalizer.RetryChangeEvidence(
        condition=condition,
        change_id=change_id,
        before_fingerprint=before,
        after_fingerprint=after,
        summary=payload["summary"],
        recorded_at=payload["recorded_at"],
        previous_attempt_updated_at=previous_attempt_updated_at,
        digest=finalizer._canonical_digest(payload),
    )


def test_finalize_exact_cohort_pushes_and_verifies_remote_sha(tmp_path: Path) -> None:
    repo, _remote = _fixture(tmp_path)
    source = repo / "src/app.py"
    source.parent.mkdir()
    source.write_text("print('safe')\n", encoding="utf-8")
    (repo / "unrelated.txt").write_text("preserve me\n", encoding="utf-8")
    plan = _load_plan(tmp_path, _plan_dict(repo, [_entry(repo, "src/app.py")]))

    result = finalizer.finalize(repo, plan, allow_local_remote_for_tests=True)

    local_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert result["status"] == "complete"
    assert result["remote_sha_verified"] is True
    assert result["local_commit_sha"] == result["remote_commit_sha"] == local_sha
    assert _remote_sha(repo) == local_sha
    assert _git(repo, "show", "--format=", "--name-only", "HEAD").stdout.split() == ["src/app.py"]
    assert (repo / "unrelated.txt").read_text(encoding="utf-8") == "preserve me\n"
    assert "?? unrelated.txt" in _git(repo, "status", "--short").stdout
    receipt = json.loads((repo / finalizer.RECEIPT_ROOT / "cohort-001.json").read_text())
    assert receipt["remote_sha_verified"] is True


def test_exact_staging_bypasses_configured_content_filters(tmp_path: Path) -> None:
    repo, _remote = _fixture(tmp_path)
    attributes = repo / ".gitattributes"
    attributes.write_text("*.txt filter=hostile\n", encoding="utf-8")
    _git(repo, "add", "--", ".gitattributes")
    _git(repo, "commit", "-qm", "add attributes")
    _git(repo, "push", "-q", "origin", "HEAD:task/delivery")
    sentinel = tmp_path / "filter-ran.txt"
    filter_script = tmp_path / "filter.sh"
    filter_script.write_text(
        f"#!/bin/sh\nprintf ran > '{sentinel}'\ncat\n", encoding="utf-8"
    )
    filter_script.chmod(0o755)
    _git(repo, "config", "filter.hostile.clean", str(filter_script))
    _git(repo, "config", "filter.hostile.required", "true")
    candidate = repo / "candidate.txt"
    candidate.write_text("exact raw bytes\n", encoding="utf-8")
    plan = _load_plan(
        tmp_path,
        _plan_dict(
            repo,
            [_entry(repo, "candidate.txt", classification="documentation")],
        ),
    )

    result = finalizer.finalize(repo, plan, allow_local_remote_for_tests=True)

    assert result["remote_sha_verified"] is True
    assert not sentinel.exists()
    assert _git(repo, "show", "HEAD:candidate.txt").stdout == "exact raw bytes\n"


def test_modified_and_deleted_paths_never_run_clean_filters(
    tmp_path: Path, monkeypatch
) -> None:
    repo, _remote = _fixture(tmp_path)
    attributes = repo / ".gitattributes"
    attributes.write_text("*.txt filter=hostile\n", encoding="utf-8")
    candidate = repo / "candidate.txt"
    deleted = repo / "deleted.txt"
    candidate.write_text("base candidate\n", encoding="utf-8")
    deleted.write_text("base deletion\n", encoding="utf-8")
    _git(repo, "add", "--", ".gitattributes", "candidate.txt", "deleted.txt")
    _git(repo, "commit", "-qm", "add tracked filter fixtures")
    _git(repo, "push", "-q", "origin", "HEAD:task/delivery")

    sentinel = tmp_path / "tracked-filter-ran.txt"
    filter_script = tmp_path / "tracked-filter.sh"
    filter_script.write_text(
        f"#!/bin/sh\nprintf ran > '{sentinel}'\ncat\n", encoding="utf-8"
    )
    filter_script.chmod(0o755)
    _git(repo, "config", "filter.hostile.clean", str(filter_script))
    _git(repo, "config", "filter.hostile.required", "true")
    candidate.write_text("modified raw bytes\n", encoding="utf-8")
    deleted.unlink()
    entries = [
        _entry(
            repo,
            "candidate.txt",
            state_value="modified",
            classification="documentation",
        ),
        _entry(
            repo,
            "deleted.txt",
            state_value="deleted",
            classification="documentation",
        ),
    ]
    plan = _load_plan(tmp_path, _plan_dict(repo, entries))

    real_git = finalizer._git

    def reappear_before_force_remove(repo_arg, args, **kwargs):
        values = list(args)
        if values[:2] == ["update-index", "--force-remove"]:
            deleted.write_text("foreign reappearance\n", encoding="utf-8")
        return real_git(repo_arg, values, **kwargs)

    monkeypatch.setattr(finalizer, "_git", reappear_before_force_remove)
    with pytest.raises(finalizer.FinalizationError, match="reappeared"):
        finalizer.finalize(repo, plan, allow_local_remote_for_tests=True)
    assert not sentinel.exists()
    assert _git(repo, "diff", "--cached", "--name-only").stdout == ""


def test_governed_lane_requires_exact_judge_and_governor_states(tmp_path: Path) -> None:
    repo, _remote = _fixture(tmp_path)
    candidate = repo / "policy.yaml"
    candidate.write_text("safe: true\n", encoding="utf-8")
    payload = _plan_dict(repo, [_entry(repo, "policy.yaml", classification="governance")], lane="governed")
    payload["approvals"]["governor"] = "not_required"
    with pytest.raises(finalizer.FinalizationError, match="review lane"):
        _load_plan(tmp_path, payload)


def test_plan_must_match_registered_digest_and_production_target(tmp_path: Path) -> None:
    repo, _remote = _fixture(tmp_path)
    candidate = repo / "candidate.py"
    candidate.write_text("safe\n", encoding="utf-8")
    payload = _plan_dict(repo, [_entry(repo, "candidate.py")])
    plan_path = tmp_path / "registered-plan.json"
    plan_path.write_text(json.dumps(payload), encoding="utf-8")
    registered = finalizer._canonical_digest(payload)

    with pytest.raises(finalizer.FinalizationError, match="standing authorized scope"):
        finalizer.load_plan(plan_path, expected_plan_sha256=registered)

    payload["branch"] = finalizer.STANDING_BRANCH
    payload["approvals"]["approval_subject_sha256"] = finalizer._approval_subject_digest(
        payload
    )
    plan_path.write_text(json.dumps(payload), encoding="utf-8")
    production_digest = finalizer._canonical_digest(payload)
    loaded = finalizer.load_plan(
        plan_path, expected_plan_sha256=production_digest
    )
    assert loaded.branch == finalizer.STANDING_BRANCH

    payload["commit_message"] = "test: altered after approval"
    plan_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(finalizer.FinalizationError, match="registered approval identity"):
        finalizer.load_plan(
            plan_path, expected_plan_sha256=production_digest
        )
    with pytest.raises(finalizer.FinalizationError, match="approval evidence"):
        finalizer.load_plan(
            plan_path,
            expected_plan_sha256=finalizer._canonical_digest(payload),
        )


@pytest.mark.parametrize("field", ["commit_message", "approval_evidence"])
def test_plan_metadata_rejects_high_confidence_secrets(
    tmp_path: Path, field: str
) -> None:
    repo, _remote = _fixture(tmp_path)
    candidate = repo / "candidate.py"
    candidate.write_text("safe\n", encoding="utf-8")
    payload = _plan_dict(repo, [_entry(repo, "candidate.py")])
    secret = "Bearer " + "A" * 32
    if field == "commit_message":
        payload["commit_message"] = secret
    else:
        payload["approvals"]["evidence"].append(secret)
    plan_path = tmp_path / f"secret-{field}.json"
    plan_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(finalizer.FinalizationError, match="secret"):
        finalizer.load_plan(
            plan_path,
            expected_plan_sha256=finalizer._canonical_digest(payload),
            allowed_branch="task/delivery",
        )


@pytest.mark.parametrize("unsafe_path", [".", "../escape", "src/*.py", "-A", ".GIT/config", "src:evil"])
def test_plan_rejects_broad_escape_or_git_metadata_paths(tmp_path: Path, unsafe_path: str) -> None:
    repo, _remote = _fixture(tmp_path)
    payload = _plan_dict(
        repo,
        [{"path": unsafe_path, "state": "deleted", "mode": "absent", "sha256": None, "classification": "code"}],
    )
    with pytest.raises(finalizer.FinalizationError):
        _load_plan(tmp_path, payload)


def test_preexisting_index_is_rejected_without_changing_it(tmp_path: Path) -> None:
    repo, _remote = _fixture(tmp_path)
    candidate = repo / "candidate.py"
    candidate.write_text("candidate = True\n", encoding="utf-8")
    unrelated = repo / "staged.txt"
    unrelated.write_text("owned elsewhere\n", encoding="utf-8")
    _git(repo, "add", "--", "staged.txt")
    plan = _load_plan(tmp_path, _plan_dict(repo, [_entry(repo, "candidate.py")]))
    with pytest.raises(finalizer.FinalizationError, match="pre-existing staged"):
        finalizer.preflight(repo, plan, allow_local_remote_for_tests=True)
    assert _git(repo, "diff", "--cached", "--name-only").stdout.strip() == "staged.txt"


@pytest.mark.parametrize(
    ("relative", "classification"),
    [
        ("workspace/private.json", "sanitized_metadata"),
        ("Workspace/private.json", "sanitized_metadata"),
        ("artifacts/report.json", "sanitized_report"),
        ("input_jp/book.md", "documentation"),
        ("output_cn/translated/full_volume_cn.md", "documentation"),
        (".env.production", "code"),
        ("secrets.txt", "documentation"),
    ],
)
def test_never_commit_categories_are_rejected_case_insensitively(
    tmp_path: Path, relative: str, classification: str
) -> None:
    repo, _remote = _fixture(tmp_path)
    path = repo / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("private body\n", encoding="utf-8")
    plan = _load_plan(tmp_path, _plan_dict(repo, [_entry(repo, relative, classification=classification)]))
    with pytest.raises(finalizer.FinalizationError, match="never-commit"):
        finalizer.preflight(repo, plan, allow_local_remote_for_tests=True)


def test_symlink_file_and_symlink_parent_are_rejected(tmp_path: Path) -> None:
    repo, _remote = _fixture(tmp_path)
    external = tmp_path / "external.txt"
    external.write_text("external\n", encoding="utf-8")
    linked = repo / "linked.py"
    linked.symlink_to(external)
    payload = _plan_dict(repo, [{
        "path": "linked.py",
        "state": "added",
        "mode": "0644",
        "sha256": _sha256(external),
        "classification": "code",
    }])
    plan = _load_plan(tmp_path, payload)
    with pytest.raises(finalizer.FinalizationError, match="direct regular"):
        finalizer.preflight(repo, plan, allow_local_remote_for_tests=True)

    real_dir = tmp_path / "outside-dir"
    real_dir.mkdir()
    (real_dir / "child.py").write_text("outside\n", encoding="utf-8")
    (repo / "alias").symlink_to(real_dir, target_is_directory=True)
    payload = _plan_dict(repo, [{
        "path": "alias/child.py",
        "state": "added",
        "mode": "0644",
        "sha256": _sha256(real_dir / "child.py"),
        "classification": "code",
    }])
    plan = _load_plan(tmp_path, payload)
    with pytest.raises(finalizer.FinalizationError, match="parent"):
        finalizer.preflight(repo, plan, allow_local_remote_for_tests=True)
    assert external.read_text() == "external\n"
    assert (real_dir / "child.py").read_text() == "outside\n"


def test_tracked_submodule_deletion_is_rejected(tmp_path: Path) -> None:
    repo, _remote = _fixture(tmp_path)
    _git(repo, "update-index", "--add", "--cacheinfo", "160000," + "1" * 40 + ",vendor/lib")
    _git(repo, "commit", "-qm", "add synthetic gitlink")
    _git(repo, "push", "-q", "origin", "HEAD:task/delivery")
    payload = _plan_dict(repo, [_entry(repo, "vendor/lib", state_value="deleted")])
    plan = _load_plan(tmp_path, payload)
    with pytest.raises(finalizer.FinalizationError, match="submodule"):
        finalizer.preflight(repo, plan, allow_local_remote_for_tests=True)


def test_changed_bytes_after_registration_are_rejected(tmp_path: Path) -> None:
    repo, _remote = _fixture(tmp_path)
    candidate = repo / "candidate.py"
    candidate.write_text("before\n", encoding="utf-8")
    plan = _load_plan(tmp_path, _plan_dict(repo, [_entry(repo, "candidate.py")]))
    candidate.write_text("after\n", encoding="utf-8")
    with pytest.raises(finalizer.FinalizationError, match="bytes or mode changed"):
        finalizer.preflight(repo, plan, allow_local_remote_for_tests=True)


@pytest.mark.parametrize(
    "payload",
    [b"\0binary", b"AK" + b"IA" + b"ABCDEFGHIJKLMNOP"],
)
def test_binary_or_high_confidence_secret_content_is_rejected(tmp_path: Path, payload: bytes) -> None:
    repo, _remote = _fixture(tmp_path)
    candidate = repo / "candidate.txt"
    candidate.write_bytes(payload)
    plan = _load_plan(tmp_path, _plan_dict(repo, [_entry(repo, "candidate.txt", classification="documentation")]))
    with pytest.raises(finalizer.FinalizationError):
        finalizer.preflight(repo, plan, allow_local_remote_for_tests=True)


def test_default_nonexistent_or_changed_remote_target_is_rejected(tmp_path: Path) -> None:
    repo, _remote = _fixture(tmp_path)
    candidate = repo / "candidate.py"
    candidate.write_text("safe\n", encoding="utf-8")
    entry = _entry(repo, "candidate.py")
    with pytest.raises(finalizer.FinalizationError, match="default-branch"):
        _load_plan(tmp_path, _plan_dict(repo, [entry], branch="main"))

    _git(repo, "switch", "-q", "-c", "task/not-on-remote")
    plan = _load_plan(tmp_path, _plan_dict(repo, [entry], branch="task/not-on-remote"))
    with pytest.raises(finalizer.FinalizationError, match="already exist"):
        finalizer.preflight(repo, plan, allow_local_remote_for_tests=True)

    _git(repo, "switch", "-q", "task/delivery")
    payload = _plan_dict(repo, [entry])
    payload["remote_url_sha256"] = "0" * 64
    payload["approvals"]["approval_subject_sha256"] = finalizer._approval_subject_digest(
        payload
    )
    plan = _load_plan(tmp_path, payload)
    with pytest.raises(finalizer.FinalizationError, match="URL changed"):
        finalizer.preflight(repo, plan, allow_local_remote_for_tests=True)


def test_distinct_push_url_and_fresh_remote_default_branch_are_rejected(
    tmp_path: Path,
) -> None:
    repo, remote = _fixture(tmp_path)
    candidate = repo / "candidate.py"
    candidate.write_text("safe\n", encoding="utf-8")
    plan = _load_plan(tmp_path, _plan_dict(repo, [_entry(repo, "candidate.py")]))
    alternate = tmp_path / "alternate.git"
    alternate.mkdir()
    _git(alternate, "init", "--bare", "-q")
    _git(repo, "remote", "set-url", "--push", "origin", str(alternate))
    with pytest.raises(finalizer.FinalizationError, match="fetch and push URL"):
        finalizer.preflight(repo, plan, allow_local_remote_for_tests=True)

    _git(repo, "remote", "set-url", "--delete", "--push", "origin", str(alternate))
    _git(repo, "config", f"url.{alternate}.pushInsteadOf", str(remote))
    with pytest.raises(finalizer.FinalizationError, match="fetch and push URL"):
        finalizer.preflight(repo, plan, allow_local_remote_for_tests=True)
    _git(repo, "config", "--unset-all", f"url.{alternate}.pushInsteadOf")

    _git(remote, "symbolic-ref", "HEAD", "refs/heads/task/delivery")
    with pytest.raises(finalizer.FinalizationError, match="fresh remote HEAD"):
        finalizer.preflight(repo, plan, allow_local_remote_for_tests=True)


def test_staged_and_committed_modes_must_match_plan(tmp_path: Path) -> None:
    repo, _remote = _fixture(tmp_path)
    candidate = repo / "candidate.py"
    candidate.write_text("safe\n", encoding="utf-8")
    plan = _load_plan(tmp_path, _plan_dict(repo, [_entry(repo, "candidate.py")]))
    _git(repo, "add", "--", "candidate.py")
    _git(repo, "update-index", "--chmod=+x", "candidate.py")
    with pytest.raises(finalizer.FinalizationError, match="staged mode"):
        finalizer._verify_staged_candidate(repo, plan)
    _git(
        repo,
        "-c",
        f"user.name={finalizer.COMMIT_IDENTITY_NAME}",
        "-c",
        f"user.email={finalizer.COMMIT_IDENTITY_EMAIL}",
        "commit",
        "-qm",
        plan.commit_message,
    )
    commit_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    with pytest.raises(finalizer.FinalizationError, match="committed mode"):
        finalizer._verify_commit(repo, plan, commit_sha)


def test_commit_identity_is_fixed_and_untrusted_git_identity_is_not_persisted(
    tmp_path: Path, monkeypatch
) -> None:
    repo, _remote = _fixture(tmp_path)
    candidate = repo / "candidate.py"
    candidate.write_text("safe\n", encoding="utf-8")
    plan = _load_plan(tmp_path, _plan_dict(repo, [_entry(repo, "candidate.py")]))
    marker = "UNTRUSTED_PRIVATE_IDENTITY"
    monkeypatch.setenv("GIT_AUTHOR_NAME", marker)
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "private-person@example.invalid")
    monkeypatch.setenv("GIT_COMMITTER_NAME", marker)
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "private-person@example.invalid")

    result = finalizer.finalize(repo, plan, allow_local_remote_for_tests=True)

    raw = _git(repo, "cat-file", "commit", result["local_commit_sha"]).stdout
    assert marker not in raw and "private-person" not in raw
    assert (
        _git(repo, "show", "-s", "--format=%an|%ae|%cn|%ce", "HEAD").stdout.strip()
        == f"{finalizer.COMMIT_IDENTITY_NAME}|{finalizer.COMMIT_IDENTITY_EMAIL}|"
        f"{finalizer.COMMIT_IDENTITY_NAME}|{finalizer.COMMIT_IDENTITY_EMAIL}"
    )


def test_push_uses_literal_endpoint_and_exact_commit_despite_repo_config_or_head_race(
    tmp_path: Path, monkeypatch
) -> None:
    repo, authorized_remote = _fixture(tmp_path)
    alternate = tmp_path / "unauthorized.git"
    alternate.mkdir()
    _git(alternate, "init", "--bare", "-q")
    candidate = repo / "candidate.py"
    candidate.write_text("safe\n", encoding="utf-8")
    plan = _load_plan(tmp_path, _plan_dict(repo, [_entry(repo, "candidate.py")]))
    real_push = finalizer._push_exact_commit_from_isolated_config
    observed: dict[str, str] = {}

    def race_selected_repo_config_and_head(repo_arg, remote_url, local_sha, branch):
        observed["approved"] = local_sha
        _git(repo_arg, "remote", "set-url", "--push", "origin", str(alternate))
        _git(repo_arg, "config", f"url.{alternate}.pushInsteadOf", remote_url)
        tree = _git(repo_arg, "rev-parse", f"{local_sha}^{{tree}}").stdout.strip()
        result = subprocess.run(
            ["git", "commit-tree", tree, "-p", local_sha],
            cwd=repo_arg,
            input="unapproved concurrent head\n",
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        unapproved_sha = result.stdout.strip()
        observed["unapproved"] = unapproved_sha
        _git(repo_arg, "update-ref", f"refs/heads/{branch}", unapproved_sha, local_sha)
        return real_push(repo_arg, remote_url, local_sha, branch)

    monkeypatch.setattr(
        finalizer,
        "_push_exact_commit_from_isolated_config",
        race_selected_repo_config_and_head,
    )
    with pytest.raises(finalizer.FinalizationError, match="blind retry"):
        finalizer.finalize(repo, plan, allow_local_remote_for_tests=True)

    assert _remote_sha(repo) == observed["approved"]
    alternate_lookup = _git(
        alternate,
        "show-ref",
        "--verify",
        "refs/heads/task/delivery",
        check=False,
    )
    assert alternate_lookup.returncode != 0
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == observed["unapproved"]
    assert authorized_remote != alternate


def test_isolated_remote_operations_ignore_global_url_rewrite_race(
    tmp_path: Path, monkeypatch
) -> None:
    repo, authorized_remote = _fixture(tmp_path)
    alternate = tmp_path / "global-unauthorized.git"
    alternate.mkdir()
    _git(alternate, "init", "--bare", "-q")
    candidate = repo / "candidate.py"
    candidate.write_text("safe\n", encoding="utf-8")
    plan = _load_plan(tmp_path, _plan_dict(repo, [_entry(repo, "candidate.py")]))
    global_config = tmp_path / "hostile-global.gitconfig"
    global_config.write_text(
        "[url \"{}\"]\n\tpushInsteadOf = {}\n\tinsteadOf = {}\n".format(
            alternate, authorized_remote, authorized_remote
        ),
        encoding="utf-8",
    )
    real_push = finalizer._push_exact_commit_from_isolated_config

    def enable_global_rewrite_after_endpoint_validation(
        repo_arg, remote_url, local_sha, branch
    ):
        prior = os.environ.get("GIT_CONFIG_GLOBAL")
        monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
        try:
            return real_push(repo_arg, remote_url, local_sha, branch)
        finally:
            if prior is None:
                monkeypatch.delenv("GIT_CONFIG_GLOBAL", raising=False)
            else:
                monkeypatch.setenv("GIT_CONFIG_GLOBAL", prior)

    monkeypatch.setattr(
        finalizer,
        "_push_exact_commit_from_isolated_config",
        enable_global_rewrite_after_endpoint_validation,
    )
    result = finalizer.finalize(repo, plan, allow_local_remote_for_tests=True)

    assert result["remote_sha_verified"] is True
    assert _remote_sha(repo) == result["local_commit_sha"]
    assert (
        _git(
            alternate,
            "show-ref",
            "--verify",
            "refs/heads/task/delivery",
            check=False,
        ).returncode
        != 0
    )


def test_isolated_remote_environment_drops_transport_proxy_tls_and_exec_overrides(
    tmp_path: Path, monkeypatch
) -> None:
    repo, _remote = _fixture(tmp_path)
    candidate = repo / "candidate.py"
    candidate.write_text("safe\n", encoding="utf-8")
    plan = _load_plan(tmp_path, _plan_dict(repo, [_entry(repo, "candidate.py")]))
    hostile_exec = tmp_path / "hostile-git-exec"
    hostile_exec.mkdir()
    helper_sentinel = tmp_path / "transport-helper-ran.txt"
    helper = hostile_exec / "git-remote-file"
    helper.write_text(
        f"#!/bin/sh\nprintf ran > '{helper_sentinel}'\nexit 99\n",
        encoding="utf-8",
    )
    helper.chmod(0o755)
    hostile = {
        "GIT_EXEC_PATH": str(hostile_exec),
        "GIT_SSH_COMMAND": "false",
        "GIT_PROXY_COMMAND": "false",
        "GIT_ASKPASS": "false",
        "SSH_ASKPASS": "false",
        "HTTP_PROXY": "http://127.0.0.1:1",
        "HTTPS_PROXY": "http://127.0.0.1:1",
        "ALL_PROXY": "socks5://127.0.0.1:1",
        "http_proxy": "http://127.0.0.1:1",
        "https_proxy": "http://127.0.0.1:1",
        "SSL_CERT_FILE": str(tmp_path / "malicious-ca.pem"),
        "SSL_CERT_DIR": str(tmp_path / "malicious-ca-dir"),
        "CURL_CA_BUNDLE": str(tmp_path / "malicious-ca.pem"),
        "GIT_SSL_NO_VERIFY": "1",
        "GIT_SSL_CERT": str(tmp_path / "malicious-cert.pem"),
        "GIT_SSL_KEY": str(tmp_path / "malicious-key.pem"),
        "GIT_SSL_VERSION": "sslv3",
        "GIT_CONFIG_PARAMETERS": "'url.fake.insteadOf=file://'",
        "DYLD_LIBRARY_PATH": str(tmp_path / "malicious-libs"),
        "PYTHONPATH": str(tmp_path / "malicious-python"),
    }
    real_push = finalizer._push_exact_commit_from_isolated_config

    def inject_hostile_environment(repo_arg, remote_url, local_sha, branch):
        for key, value in hostile.items():
            monkeypatch.setenv(key, value)
        isolated = finalizer._isolated_remote_environment()
        assert not (set(hostile) & set(isolated))
        return real_push(repo_arg, remote_url, local_sha, branch)

    monkeypatch.setattr(
        finalizer,
        "_push_exact_commit_from_isolated_config",
        inject_hostile_environment,
    )
    result = finalizer.finalize(repo, plan, allow_local_remote_for_tests=True)

    assert result["remote_sha_verified"] is True
    assert not helper_sentinel.exists()

def test_commit_failure_unstages_exact_cohort_and_never_pushes(tmp_path: Path, monkeypatch) -> None:
    repo, _remote = _fixture(tmp_path)
    candidate = repo / "candidate.py"
    candidate.write_text("safe\n", encoding="utf-8")
    plan = _load_plan(tmp_path, _plan_dict(repo, [_entry(repo, "candidate.py")]))
    base = plan.base_sha
    real_git = finalizer._git

    def fail_commit(repo_arg, args, **kwargs):
        values = list(args)
        if "commit-tree" in values:
            return subprocess.CompletedProcess(values, 1, "", "injected commit failure")
        return real_git(repo_arg, values, **kwargs)

    monkeypatch.setattr(finalizer, "_git", fail_commit)
    with pytest.raises(finalizer.FinalizationError, match="commit failed"):
        finalizer.finalize(repo, plan, allow_local_remote_for_tests=True)
    assert _git(repo, "rev-parse", "HEAD").stdout.strip() == base
    assert _git(repo, "diff", "--cached", "--name-only").stdout == ""
    assert _remote_sha(repo) == base
    receipt = json.loads(
        (repo / finalizer.RECEIPT_ROOT / "cohort-001.json").read_text()
    )
    assert receipt["status"] == "incomplete"
    assert receipt["outcome"] == "pre_commit_failed"


def test_push_failure_preserves_commit_blocks_blind_retry_then_recovers(
    tmp_path: Path,
) -> None:
    repo, remote = _fixture(tmp_path)
    candidate = repo / "candidate.py"
    candidate.write_text("safe\n", encoding="utf-8")
    plan = _load_plan(tmp_path, _plan_dict(repo, [_entry(repo, "candidate.py")]))
    base = plan.base_sha
    hook = remote / "hooks/pre-receive"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)

    with pytest.raises(finalizer.FinalizationError, match="blind retry"):
        finalizer.finalize(repo, plan, allow_local_remote_for_tests=True)
    local_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert local_sha != base and _remote_sha(repo) == base
    receipt = json.loads((repo / finalizer.RECEIPT_ROOT / "cohort-001.json").read_text())
    assert receipt["status"] == "incomplete" and receipt["remote_sha_verified"] is False

    first_change = _retry_evidence(
        plan,
        condition="network_state_changed",
        change_id="network-change-1",
        before="1" * 64,
        after="2" * 64,
        previous_attempt_updated_at=receipt["updated_at"],
    )
    with pytest.raises(finalizer.FinalizationError, match="retry did not verify"):
        finalizer.retry_push(
            repo,
            plan,
            change_evidence=first_change,
            allow_local_remote_for_tests=True,
        )
    with pytest.raises(finalizer.FinalizationError, match="already consumed"):
        finalizer.retry_push(
            repo,
            plan,
            change_evidence=first_change,
            allow_local_remote_for_tests=True,
        )

    hook.unlink()
    failed_retry_receipt = json.loads(
        (repo / finalizer.RECEIPT_ROOT / "cohort-001.json").read_text()
    )
    second_change = _retry_evidence(
        plan,
        condition="transport_method_changed",
        change_id="transport-change-1",
        before="2" * 64,
        after="4" * 64,
        previous_attempt_updated_at=failed_retry_receipt["updated_at"],
    )
    result = finalizer.retry_push(
        repo,
        plan,
        change_evidence=second_change,
        allow_local_remote_for_tests=True,
    )
    assert result["remote_sha_verified"] is True
    assert _remote_sha(repo) == local_sha
    completed_receipt = json.loads(
        (repo / finalizer.RECEIPT_ROOT / "cohort-001.json").read_text()
    )
    history_before_verify = completed_receipt["retry_history"]
    assert len(history_before_verify) == 2
    finalizer.verify_delivery(repo, plan, allow_local_remote_for_tests=True)
    history_after_verify = json.loads(
        (repo / finalizer.RECEIPT_ROOT / "cohort-001.json").read_text()
    )["retry_history"]
    assert history_after_verify == history_before_verify


def test_retry_evidence_is_consumed_before_external_attempt(
    tmp_path: Path, monkeypatch
) -> None:
    repo, remote = _fixture(tmp_path)
    candidate = repo / "candidate.py"
    candidate.write_text("safe\n", encoding="utf-8")
    plan = _load_plan(tmp_path, _plan_dict(repo, [_entry(repo, "candidate.py")]))
    hook = remote / "hooks/pre-receive"
    hook.parent.mkdir(exist_ok=True)
    hook.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
    hook.chmod(0o755)
    with pytest.raises(finalizer.FinalizationError):
        finalizer.finalize(repo, plan, allow_local_remote_for_tests=True)
    receipt = json.loads(
        (repo / finalizer.RECEIPT_ROOT / "cohort-001.json").read_text()
    )
    evidence = _retry_evidence(
        plan,
        condition="network_state_changed",
        change_id="crash-window-change-1",
        before="a" * 64,
        after="b" * 64,
        previous_attempt_updated_at=receipt["updated_at"],
    )

    def crash_after_attempt(*_args, **_kwargs):
        raise RuntimeError("injected process interruption")

    monkeypatch.setattr(finalizer, "_push_and_verify", crash_after_attempt)
    with pytest.raises(RuntimeError, match="interruption"):
        finalizer.retry_push(
            repo,
            plan,
            change_evidence=evidence,
            allow_local_remote_for_tests=True,
        )
    attempting = json.loads(
        (repo / finalizer.RECEIPT_ROOT / "cohort-001.json").read_text()
    )
    assert attempting["outcome"] == "retry_attempting"
    assert attempting["retry_history"][0]["change_id"] == evidence.change_id
    with pytest.raises(finalizer.FinalizationError, match="already consumed"):
        finalizer.retry_push(
            repo,
            plan,
            change_evidence=evidence,
            allow_local_remote_for_tests=True,
        )


def test_retry_change_evidence_binds_plan_and_requires_real_fingerprint_delta(
    tmp_path: Path,
) -> None:
    repo, _remote = _fixture(tmp_path)
    candidate = repo / "candidate.py"
    candidate.write_text("safe\n", encoding="utf-8")
    plan = _load_plan(tmp_path, _plan_dict(repo, [_entry(repo, "candidate.py")]))
    evidence_path = tmp_path / "retry-change.json"
    payload = {
        "schema": "git_safe_cohort_retry_change_v1",
        "cohort_id": plan.cohort_id,
        "plan_sha256": plan.digest,
        "condition": "network_state_changed",
        "change_id": "network-change-file-1",
        "recorded_at": "2026-08-13T00:00:00Z",
        "previous_attempt_updated_at": "2026-08-12T23:59:59Z",
        "before_fingerprint": "7" * 64,
        "after_fingerprint": "7" * 64,
        "summary": "Network diagnostics changed after a bounded repair",
    }
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(finalizer.FinalizationError, match="distinct before/after"):
        finalizer.load_retry_change_evidence(evidence_path, plan)

    payload["after_fingerprint"] = "8" * 64
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    loaded = finalizer.load_retry_change_evidence(evidence_path, plan)
    assert loaded.condition == "network_state_changed"
    assert loaded.digest == finalizer._canonical_digest(payload)

    payload["plan_sha256"] = "9" * 64
    evidence_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(finalizer.FinalizationError, match="exact cohort plan"):
        finalizer.load_retry_change_evidence(evidence_path, plan)


def test_remote_sha_mismatch_remains_incomplete_until_fresh_verify(
    tmp_path: Path, monkeypatch
) -> None:
    repo, _remote = _fixture(tmp_path)
    candidate = repo / "candidate.py"
    candidate.write_text("safe\n", encoding="utf-8")
    plan = _load_plan(tmp_path, _plan_dict(repo, [_entry(repo, "candidate.py")]))
    base = plan.base_sha
    real_lookup = finalizer._ls_remote_branch
    calls = 0

    def stale_after_push(repo_arg, plan_arg, remote_target=None):
        nonlocal calls
        calls += 1
        if calls == 3:
            return base
        return real_lookup(repo_arg, plan_arg, remote_target)

    monkeypatch.setattr(finalizer, "_ls_remote_branch", stale_after_push)
    with pytest.raises(finalizer.FinalizationError, match="blind retry"):
        finalizer.finalize(repo, plan, allow_local_remote_for_tests=True)
    local_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert _remote_sha(repo) == local_sha
    monkeypatch.setattr(finalizer, "_ls_remote_branch", real_lookup)
    verified = finalizer.verify_delivery(repo, plan, allow_local_remote_for_tests=True)
    assert verified["remote_sha_verified"] is True


def test_post_commit_verification_failure_records_recoverable_receipt(
    tmp_path: Path, monkeypatch
) -> None:
    repo, _remote = _fixture(tmp_path)
    candidate = repo / "candidate.py"
    candidate.write_text("safe\n", encoding="utf-8")
    plan = _load_plan(tmp_path, _plan_dict(repo, [_entry(repo, "candidate.py")]))
    real_verify = finalizer._verify_commit
    injected = False

    def fail_once(repo_arg, plan_arg, commit_sha):
        nonlocal injected
        if not injected:
            injected = True
            raise finalizer.FinalizationError("injected post-commit verification failure")
        return real_verify(repo_arg, plan_arg, commit_sha)

    monkeypatch.setattr(finalizer, "_verify_commit", fail_once)
    with pytest.raises(finalizer.FinalizationError, match="injected"):
        finalizer.finalize(repo, plan, allow_local_remote_for_tests=True)
    local_sha = _git(repo, "rev-parse", "HEAD").stdout.strip()
    assert local_sha != plan.base_sha
    receipt = json.loads(
        (repo / finalizer.RECEIPT_ROOT / "cohort-001.json").read_text()
    )
    assert receipt["status"] == "incomplete"
    assert receipt["outcome"] == "post_commit_verification_failed"
    assert receipt["local_commit_sha"] == local_sha

    evidence = _retry_evidence(
        plan,
        condition="remote_state_changed",
        change_id="post-commit-recovery-1",
        before="5" * 64,
        after="6" * 64,
        previous_attempt_updated_at=receipt["updated_at"],
    )
    result = finalizer.retry_push(
        repo,
        plan,
        change_evidence=evidence,
        allow_local_remote_for_tests=True,
    )
    assert result["remote_sha_verified"] is True


def test_exact_rename_and_regular_delete_are_allowed_when_fully_registered(tmp_path: Path) -> None:
    repo, _remote = _fixture(tmp_path)
    old = repo / "old.txt"
    old.write_text("rename body\n", encoding="utf-8")
    _git(repo, "add", "--", "old.txt")
    _git(repo, "commit", "-qm", "add old")
    _git(repo, "push", "-q", "origin", "HEAD:task/delivery")
    old.rename(repo / "new.txt")
    entries = [
        _entry(repo, "old.txt", state_value="deleted", classification="documentation"),
        _entry(repo, "new.txt", classification="documentation"),
    ]
    plan = _load_plan(tmp_path, _plan_dict(repo, entries))
    result = finalizer.finalize(repo, plan, allow_local_remote_for_tests=True)
    assert result["remote_sha_verified"] is True
    assert set(
        _git(
            repo,
            "diff-tree",
            "--no-commit-id",
            "--no-renames",
            "--name-only",
            "-r",
            "HEAD",
        ).stdout.split()
    ) == {
        "new.txt",
        "old.txt",
    }


def test_exclusive_lock_rejects_overlapping_finalizer(tmp_path: Path) -> None:
    repo, _remote = _fixture(tmp_path)
    with finalizer._exclusive_delivery_lock(repo):
        with pytest.raises(finalizer.FinalizationError, match="another Git-safe cohort"):
            with finalizer._exclusive_delivery_lock(repo):
                raise AssertionError("unreachable")


def test_exclusive_lock_rejects_shared_writable_lock_directory(tmp_path: Path) -> None:
    repo, _remote = _fixture(tmp_path)
    lock_root = repo / finalizer.LOCK_PATH.parent
    lock_root.mkdir(parents=True)
    lock_root.chmod(0o777)
    with pytest.raises(finalizer.FinalizationError, match="group/world writable"):
        with finalizer._exclusive_delivery_lock(repo):
            raise AssertionError("unreachable")
