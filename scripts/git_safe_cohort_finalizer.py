#!/usr/bin/env python3
"""Finalize one approved Git-safe cohort on an existing non-default branch.

The plan is a hash-bound authorization envelope.  This program never discovers
or broad-stages a candidate: every path, state, mode, and SHA-256 must already
be registered.  A successful run stages those exact paths, commits, performs a
normal push to the already-existing branch, and verifies the remote ref.

Push failures preserve the local commit and an ignored local receipt.  A retry
is a separate command and requires a named state or method change.
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable
from urllib.parse import urlparse


PLAN_SCHEMA = "git_safe_cohort_v1"
DELIVERY_AUTHORITY = "standing_git_safe_cohort_policy_v1"
STANDING_REMOTE = "origin"
STANDING_BRANCH = "codex/light-novel-governance-closure-20260813"
STANDING_DEFAULT_BRANCH = "main"
COMMIT_IDENTITY_NAME = "Codex Git-safe Cohort Finalizer"
COMMIT_IDENTITY_EMAIL = "codex-git-safe-cohort@users.noreply.github.com"
ALLOWED_LANES = {"direct", "reviewed", "governed"}
ALLOWED_STATES = {"added", "modified", "deleted"}
ALLOWED_CLASSIFICATIONS = {
    "code",
    "documentation",
    "governance",
    "schema",
    "test",
    "sanitized_metadata",
    "sanitized_report",
}
ALLOWED_RETRY_CONDITIONS = {
    "credentials_refreshed",
    "network_state_changed",
    "remote_state_changed",
    "transport_method_changed",
}
MAX_GIT_SAFE_FILE_BYTES = 2 * 1024 * 1024
MAX_PLAN_BYTES = 256 * 1024
RECEIPT_ROOT = Path(".agent_runtime/inspection_reports/git_delivery")
LOCK_PATH = Path(".agent_runtime/locks/git_safe_cohort_finalizer.lock")

DENIED_PREFIXES = (
    ".agent_runtime/",
    "artifacts/",
    "draft_full_baseline/",
    "input_cn/",
    "input_jp/",
    "notes/",
    "output_cn/",
    "output_draft/",
    "output_final/",
    "output_jp/",
    "output_refined/",
    "workspace/",
)
SAFE_PATH_EXCEPTIONS = {
    ".agent_runtime/blockers.jsonl",
    ".agent_runtime/queue.jsonl",
    ".agent_runtime/status.json",
    "input_cn/.gitkeep",
    "input_cn/README.md",
    "input_jp/.gitkeep",
    "input_jp/README.md",
    "notes/README.md",
    "output_cn/README.md",
    "output_cn/bilingual/.gitkeep",
    "output_cn/final_export_manifest.json",
    "output_cn/review/.gitkeep",
    "output_cn/translated/.gitkeep",
    "output_jp/README.md",
    "output_jp/bilingual/.gitkeep",
    "output_jp/review/.gitkeep",
    "output_jp/translated/.gitkeep",
    "workspace/README.md",
    "workspace/checkpoints/.gitkeep",
    "workspace/embeddings/.gitkeep",
    "workspace/manifests/.gitkeep",
    "workspace/model_runs/.gitkeep",
    "workspace/review/README.md",
    "workspace/runs/.gitkeep",
    "workspace/smoke/.gitkeep",
    "workspace/vector_store/.gitkeep",
    "workspace/vector_store/README.md",
}
PRIVATE_NAME_RE = re.compile(
    r"(^|/)(?:\.env(?:\..*)?|[^/]*(?:secret|credential|private[-_]?key)[^/]*)$",
    re.IGNORECASE,
)
SECRET_PATTERNS = (
    re.compile(rb"AKIA[0-9A-Z]{16}"),
    re.compile(rb"gh[pousr]_[A-Za-z0-9]{30,}"),
    re.compile(rb"github_pat_[A-Za-z0-9_]{40,}"),
    re.compile(rb"sk-[A-Za-z0-9]{20,}"),
    re.compile(rb"xox[baprs]-[A-Za-z0-9-]{20,}"),
    re.compile(rb"AIza[0-9A-Za-z_-]{30,}"),
    re.compile(rb"(?i)\bbearer[ \t]+[A-Za-z0-9._~+/-]{20,}={0,2}"),
    re.compile(rb"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(rb"https?://[^/\s:@]+:[^@\s/]+@"),
)
HEX_SHA_RE = re.compile(r"[0-9a-f]{40}")
HEX_SHA256_RE = re.compile(r"[0-9a-f]{64}")
COHORT_ID_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}")


class FinalizationError(RuntimeError):
    """A fail-closed policy or delivery error."""


@dataclass(frozen=True)
class PlanPath:
    path: str
    state: str
    mode: str
    sha256: str | None
    classification: str


@dataclass(frozen=True)
class CohortPlan:
    cohort_id: str
    base_sha: str
    remote: str
    remote_url_sha256: str
    branch: str
    default_branch: str
    commit_message: str
    review_lane: str
    approvals: dict[str, Any]
    delivery_authority: str
    paths: tuple[PlanPath, ...]
    digest: str


@dataclass(frozen=True)
class RetryChangeEvidence:
    condition: str
    change_id: str
    before_fingerprint: str
    after_fingerprint: str
    summary: str
    recorded_at: str
    previous_attempt_updated_at: str
    digest: str


def _canonical_digest(value: dict[str, Any]) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _load_json_regular(path: Path) -> dict[str, Any]:
    try:
        linked = path.lstat()
    except OSError as exc:
        raise FinalizationError("cohort plan is missing or unreadable") from exc
    if stat.S_ISLNK(linked.st_mode) or not stat.S_ISREG(linked.st_mode):
        raise FinalizationError("cohort plan must be a direct regular file")
    if linked.st_size > MAX_PLAN_BYTES:
        raise FinalizationError("cohort plan is unexpectedly large")
    try:
        flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
        fd = os.open(path, flags)
        with os.fdopen(fd, "rb", closefd=True) as handle:
            opened = os.fstat(handle.fileno())
            payload = handle.read(MAX_PLAN_BYTES + 1)
        visible = path.lstat()
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_ISLNK(visible.st_mode)
            or (opened.st_dev, opened.st_ino) != (visible.st_dev, visible.st_ino)
            or len(payload) > MAX_PLAN_BYTES
        ):
            raise FinalizationError("cohort plan identity changed while reading")
        _scan_git_safe_bytes(payload, path="cohort plan metadata")
        value = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise FinalizationError("cohort plan must be strict UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise FinalizationError("cohort plan must be a JSON object")
    return value


def _normalize_relative_path(raw: Any) -> str:
    if not isinstance(raw, str) or not raw or raw.startswith("-"):
        raise FinalizationError("candidate path must be a non-empty relative path")
    if any(ord(char) < 32 for char in raw) or "\\" in raw or ":" in raw:
        raise FinalizationError("candidate path contains unsafe characters")
    if any(char in raw for char in "*?[]{}"):
        raise FinalizationError("candidate path must not contain glob syntax")
    pure = PurePosixPath(raw)
    if pure.is_absolute() or raw in {".", ".."} or ".." in pure.parts:
        raise FinalizationError("candidate path escapes the repository")
    normalized = pure.as_posix()
    folded = normalized.casefold()
    if normalized != raw or folded.startswith(".git/") or folded == ".git":
        raise FinalizationError("candidate path is not canonical or targets Git metadata")
    return normalized


def _approval_subject_digest(raw: dict[str, Any]) -> str:
    subject = {key: value for key, value in raw.items() if key != "approvals"}
    return _canonical_digest(subject)


def _validate_approvals(
    lane: str, approvals: Any, *, approval_subject_sha256: str
) -> dict[str, Any]:
    if not isinstance(approvals, dict) or set(approvals) != {
        "validation",
        "judge",
        "governor",
        "content_safety",
        "approval_subject_sha256",
        "evidence",
    }:
        raise FinalizationError("approval envelope has unexpected fields")
    evidence = approvals.get("evidence")
    if (
        approvals.get("validation") != "passed"
        or approvals.get("content_safety") != "passed"
        or approvals.get("approval_subject_sha256") != approval_subject_sha256
        or not isinstance(evidence, list)
        or not evidence
        or any(not isinstance(item, str) or not item.strip() for item in evidence)
    ):
        raise FinalizationError("validation approval evidence is incomplete")
    expected = {
        "direct": ("not_required", "not_required"),
        "reviewed": ("passed", "not_required"),
        "governed": ("passed", "approved"),
    }[lane]
    if (approvals.get("judge"), approvals.get("governor")) != expected:
        raise FinalizationError("approval states do not satisfy the review lane")
    return approvals


def load_plan(
    path: Path,
    *,
    expected_plan_sha256: str,
    allowed_remote: str = STANDING_REMOTE,
    allowed_branch: str = STANDING_BRANCH,
    allowed_default_branch: str = STANDING_DEFAULT_BRANCH,
) -> CohortPlan:
    raw = _load_json_regular(path)
    raw_digest = _canonical_digest(raw)
    if (
        not isinstance(expected_plan_sha256, str)
        or HEX_SHA256_RE.fullmatch(expected_plan_sha256) is None
        or raw_digest != expected_plan_sha256
    ):
        raise FinalizationError("plan differs from the exact registered approval identity")
    required = {
        "schema",
        "cohort_id",
        "base_sha",
        "remote",
        "remote_url_sha256",
        "branch",
        "default_branch",
        "commit_message",
        "review_lane",
        "approvals",
        "delivery_authority",
        "paths",
    }
    if set(raw) != required or raw.get("schema") != PLAN_SCHEMA:
        raise FinalizationError("cohort plan schema or fields are invalid")
    cohort_id = raw.get("cohort_id")
    base_sha = raw.get("base_sha")
    remote = raw.get("remote")
    remote_url_sha256 = raw.get("remote_url_sha256")
    branch = raw.get("branch")
    default_branch = raw.get("default_branch")
    commit_message = raw.get("commit_message")
    lane = raw.get("review_lane")
    if not isinstance(cohort_id, str) or COHORT_ID_RE.fullmatch(cohort_id) is None:
        raise FinalizationError("cohort_id is invalid")
    if not isinstance(base_sha, str) or HEX_SHA_RE.fullmatch(base_sha) is None:
        raise FinalizationError("base_sha must be a full lowercase Git SHA")
    if remote != allowed_remote:
        raise FinalizationError("standing policy permits only its registered existing remote")
    if not isinstance(remote_url_sha256, str) or HEX_SHA256_RE.fullmatch(remote_url_sha256) is None:
        raise FinalizationError("remote_url_sha256 is invalid")
    for label, value in (("branch", branch), ("default_branch", default_branch)):
        if (
            not isinstance(value, str)
            or not value
            or value.startswith("-")
            or any(char.isspace() for char in value)
            or ".." in value
            or value.endswith("/")
        ):
            raise FinalizationError(f"{label} is invalid")
    if branch == default_branch:
        raise FinalizationError("default-branch delivery is forbidden")
    if branch != allowed_branch or default_branch != allowed_default_branch:
        raise FinalizationError("branch target differs from the standing authorized scope")
    if (
        not isinstance(commit_message, str)
        or not commit_message.strip()
        or "\n" in commit_message
        or len(commit_message) > 100
    ):
        raise FinalizationError("commit_message must be one non-empty line")
    if lane not in ALLOWED_LANES:
        raise FinalizationError("review_lane is invalid")
    approvals = _validate_approvals(
        lane,
        raw.get("approvals"),
        approval_subject_sha256=_approval_subject_digest(raw),
    )
    if raw.get("delivery_authority") != DELIVERY_AUTHORITY:
        raise FinalizationError("standing Git delivery authority is missing")
    paths_raw = raw.get("paths")
    if not isinstance(paths_raw, list) or not paths_raw:
        raise FinalizationError("one non-empty cohort path list is required")
    paths: list[PlanPath] = []
    seen: set[str] = set()
    for item in paths_raw:
        if not isinstance(item, dict) or set(item) != {
            "path",
            "state",
            "mode",
            "sha256",
            "classification",
        }:
            raise FinalizationError("candidate entry has unexpected fields")
        relative = _normalize_relative_path(item.get("path"))
        state_value = item.get("state")
        mode = item.get("mode")
        digest = item.get("sha256")
        classification = item.get("classification")
        if relative in seen:
            raise FinalizationError("candidate path list contains duplicates")
        if state_value not in ALLOWED_STATES:
            raise FinalizationError("candidate state is invalid")
        if classification not in ALLOWED_CLASSIFICATIONS:
            raise FinalizationError("candidate classification is invalid")
        if state_value == "deleted":
            if mode != "absent" or digest is not None:
                raise FinalizationError("deleted entry must use mode=absent and sha256=null")
        elif (
            not isinstance(mode, str)
            or re.fullmatch(r"0[0-7]{3}", mode) is None
            or not isinstance(digest, str)
            or HEX_SHA256_RE.fullmatch(digest) is None
        ):
            raise FinalizationError("present entry mode or SHA-256 is invalid")
        seen.add(relative)
        paths.append(PlanPath(relative, state_value, mode, digest, classification))
    return CohortPlan(
        cohort_id=cohort_id,
        base_sha=base_sha,
        remote=remote,
        remote_url_sha256=remote_url_sha256,
        branch=branch,
        default_branch=default_branch,
        commit_message=commit_message,
        review_lane=lane,
        approvals=approvals,
        delivery_authority=raw["delivery_authority"],
        paths=tuple(paths),
        digest=raw_digest,
    )


def load_retry_change_evidence(
    path: Path, plan: CohortPlan
) -> RetryChangeEvidence:
    raw = _load_json_regular(path)
    if set(raw) != {
        "schema",
        "cohort_id",
        "plan_sha256",
        "condition",
        "change_id",
        "recorded_at",
        "before_fingerprint",
        "after_fingerprint",
        "previous_attempt_updated_at",
        "summary",
    } or raw.get("schema") != "git_safe_cohort_retry_change_v1":
        raise FinalizationError("retry change evidence schema or fields are invalid")
    if raw.get("cohort_id") != plan.cohort_id or raw.get("plan_sha256") != plan.digest:
        raise FinalizationError("retry change evidence does not bind the exact cohort plan")
    condition = raw.get("condition")
    if condition not in ALLOWED_RETRY_CONDITIONS:
        raise FinalizationError("retry requires one recognized state or method change")
    change_id = raw.get("change_id")
    if not isinstance(change_id, str) or COHORT_ID_RE.fullmatch(change_id) is None:
        raise FinalizationError("retry change_id is invalid")
    before = raw.get("before_fingerprint")
    after = raw.get("after_fingerprint")
    if (
        not isinstance(before, str)
        or not isinstance(after, str)
        or HEX_SHA256_RE.fullmatch(before) is None
        or HEX_SHA256_RE.fullmatch(after) is None
        or before == after
    ):
        raise FinalizationError("retry evidence must record distinct before/after fingerprints")
    recorded_at = raw.get("recorded_at")
    try:
        timestamp = dt.datetime.fromisoformat(str(recorded_at).replace("Z", "+00:00"))
    except ValueError as exc:
        raise FinalizationError("retry evidence recorded_at is invalid") from exc
    if timestamp.tzinfo is None:
        raise FinalizationError("retry evidence recorded_at must include a timezone")
    if timestamp > dt.datetime.now(dt.timezone.utc) + dt.timedelta(minutes=5):
        raise FinalizationError("retry evidence recorded_at is implausibly in the future")
    previous_attempt_updated_at = raw.get("previous_attempt_updated_at")
    try:
        previous_timestamp = dt.datetime.fromisoformat(
            str(previous_attempt_updated_at).replace("Z", "+00:00")
        )
    except ValueError as exc:
        raise FinalizationError("retry evidence previous attempt timestamp is invalid") from exc
    if previous_timestamp.tzinfo is None or timestamp <= previous_timestamp:
        raise FinalizationError("retry evidence must be recorded after the previous attempt")
    summary = raw.get("summary")
    if (
        not isinstance(summary, str)
        or not summary.strip()
        or "\n" in summary
        or len(summary) > 200
    ):
        raise FinalizationError("retry evidence summary must be one bounded non-empty line")
    return RetryChangeEvidence(
        condition=condition,
        change_id=change_id,
        before_fingerprint=before,
        after_fingerprint=after,
        summary=summary,
        recorded_at=str(recorded_at),
        previous_attempt_updated_at=str(previous_attempt_updated_at),
        digest=_canonical_digest(raw),
    )


def _git(
    repo: Path,
    args: Iterable[str],
    *,
    check: bool = True,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        env=env,
        text=True,
        input=input_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise FinalizationError(f"Git command failed safely: {args!r}")
    return result


def _git_bytes(
    repo: Path,
    args: Iterable[str],
    *,
    check: bool = True,
    input_bytes: bytes | None = None,
) -> subprocess.CompletedProcess[bytes]:
    result = subprocess.run(
        ["git", *args],
        cwd=repo,
        input=input_bytes,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if check and result.returncode != 0:
        raise FinalizationError(f"Git command failed safely: {args!r}")
    return result


def _repo_root(path: Path) -> Path:
    resolved = path.resolve()
    root = _git(resolved, ["rev-parse", "--show-toplevel"]).stdout.strip()
    if Path(root).resolve() != resolved:
        raise FinalizationError("--repo must be the selected repository root")
    return resolved


def _head(repo: Path) -> str:
    value = _git(repo, ["rev-parse", "HEAD"]).stdout.strip()
    if HEX_SHA_RE.fullmatch(value) is None:
        raise FinalizationError("repository HEAD is invalid")
    return value


def _current_branch(repo: Path) -> str:
    branch = _git(repo, ["symbolic-ref", "--quiet", "--short", "HEAD"]).stdout.strip()
    if not branch:
        raise FinalizationError("detached or unborn HEAD is not deliverable")
    return branch


def _safe_remote_url(url: str, *, allow_local_for_tests: bool) -> None:
    if allow_local_for_tests and (url.startswith("file://") or Path(url).is_absolute()):
        return
    https = re.fullmatch(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", url)
    scp = re.fullmatch(r"git@github\.com:[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", url)
    ssh = re.fullmatch(r"ssh://git@github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?", url)
    if not (https or scp or ssh):
        raise FinalizationError("origin is not an approved credential-free GitHub URL")
    parsed = urlparse(url) if "://" in url else None
    if parsed is not None and parsed.password:
        raise FinalizationError("credentials must not be embedded in the remote URL")


def _remote_url(repo: Path, plan: CohortPlan, *, allow_local_for_tests: bool) -> str:
    fetch_urls = [
        line
        for line in _git(repo, ["remote", "get-url", "--all", plan.remote]).stdout.splitlines()
        if line
    ]
    push_urls = [
        line
        for line in _git(
            repo, ["remote", "get-url", "--push", "--all", plan.remote]
        ).stdout.splitlines()
        if line
    ]
    if len(fetch_urls) != 1 or push_urls != fetch_urls:
        raise FinalizationError(
            "registered remote must have one identical fetch and push URL"
        )
    url = fetch_urls[0]
    _safe_remote_url(url, allow_local_for_tests=allow_local_for_tests)
    if hashlib.sha256(url.encode("utf-8")).hexdigest() != plan.remote_url_sha256:
        raise FinalizationError("origin URL changed after cohort registration")
    mirror = _git(
        repo,
        ["config", "--bool", "--get", f"remote.{plan.remote}.mirror"],
        check=False,
    )
    if mirror.returncode == 0 and mirror.stdout.strip() != "false":
        raise FinalizationError("mirror remotes are forbidden for cohort delivery")
    return url


def _approved_credential_args(repo: Path, remote_url: str) -> list[str]:
    if not remote_url.startswith("https://"):
        return []
    helpers = [
        value.strip()
        for value in _git(
            repo, ["config", "--get-all", "credential.helper"], check=False
        ).stdout.splitlines()
        if value.strip()
    ]
    if helpers != ["osxkeychain"]:
        raise FinalizationError(
            "HTTPS delivery requires the single approved osxkeychain credential helper"
        )
    return ["-c", "credential.helper=osxkeychain"]


def _isolated_remote_environment() -> dict[str, str]:
    # Start from a deliberately small allowlist.  Inheriting the caller's Git,
    # curl, proxy, TLS, loader, Python, or executable-path variables would turn
    # a literal approved URL back into an unbound transport input.
    env = {
        key: os.environ[key]
        for key in (
            "PATH",
            "HOME",
            "USER",
            "LOGNAME",
            "TMPDIR",
            "LANG",
            "LC_ALL",
            "LC_CTYPE",
            "SSH_AUTH_SOCK",
        )
        if key in os.environ
    }
    env["GIT_CONFIG_NOSYSTEM"] = "1"
    env["GIT_CONFIG_GLOBAL"] = os.devnull
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GIT_PAGER"] = "cat"
    return env


def _literal_remote_git(
    repo: Path, remote_url: str, args: list[str]
) -> subprocess.CompletedProcess[str]:
    credential_args = _approved_credential_args(repo, remote_url)
    env = _isolated_remote_environment()
    with tempfile.TemporaryDirectory(prefix="git-safe-cohort-remote.") as temporary:
        return subprocess.run(
            ["git", *credential_args, *args],
            cwd=temporary,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )


def _remote_default_branch_at(repo: Path, plan: CohortPlan, remote_target: str) -> str:
    symbolic = _literal_remote_git(
        repo, remote_target, ["ls-remote", "--symref", remote_target, "HEAD"]
    )
    if symbolic.returncode != 0:
        raise FinalizationError("fresh remote HEAD lookup failed")
    refs = [line.split() for line in symbolic.stdout.splitlines() if line.startswith("ref:")]
    expected = f"refs/heads/{plan.default_branch}"
    if len(refs) != 1 or refs[0] != ["ref:", expected, "HEAD"]:
        raise FinalizationError("registered default branch does not match fresh remote HEAD")
    if expected == f"refs/heads/{plan.branch}":
        raise FinalizationError("authorized delivery branch became the default branch")
    return plan.default_branch


def _ls_remote_branch(
    repo: Path, plan: CohortPlan, remote_target: str | None = None
) -> str:
    target = remote_target or plan.remote
    result = _literal_remote_git(
        repo,
        target,
        [
            "ls-remote",
            "--heads",
            target,
            f"refs/heads/{plan.branch}",
        ],
    )
    if result.returncode != 0:
        raise FinalizationError("remote branch lookup failed")
    lines = [line for line in result.stdout.splitlines() if line.strip()]
    if len(lines) != 1:
        raise FinalizationError("the authorized remote branch must already exist exactly once")
    fields = lines[0].split()
    expected_ref = f"refs/heads/{plan.branch}"
    if len(fields) != 2 or HEX_SHA_RE.fullmatch(fields[0]) is None or fields[1] != expected_ref:
        raise FinalizationError("remote branch response is invalid")
    return fields[0]


def _path_is_denied(item: PlanPath) -> bool:
    folded = item.path.casefold()
    safe_exceptions = {value.casefold(): value for value in SAFE_PATH_EXCEPTIONS}
    if PRIVATE_NAME_RE.search(item.path):
        return True
    if folded in safe_exceptions:
        return item.classification not in {"documentation", "sanitized_metadata", "governance"}
    return folded.startswith(tuple(value.casefold() for value in DENIED_PREFIXES))


def _head_has_path(repo: Path, relative: str) -> bool:
    return _git(repo, ["cat-file", "-e", f"HEAD:{relative}"], check=False).returncode == 0


def _head_mode(repo: Path, relative: str) -> str | None:
    result = _git(repo, ["ls-tree", "HEAD", "--", relative], check=False)
    if result.returncode != 0 or not result.stdout.strip():
        return None
    lines = result.stdout.splitlines()
    if len(lines) != 1:
        raise FinalizationError(f"HEAD path identity is ambiguous: {relative}")
    fields = lines[0].split(None, 3)
    if len(fields) != 4 or fields[3].split("\t", 1)[-1] != relative:
        raise FinalizationError(f"HEAD path metadata is invalid: {relative}")
    return fields[0]


def _validate_path_ancestry(repo: Path, relative: str) -> None:
    current = repo
    for part in PurePosixPath(relative).parts[:-1]:
        current = current / part
        try:
            linked = current.lstat()
        except OSError as exc:
            raise FinalizationError(f"candidate parent is missing: {relative}") from exc
        if stat.S_ISLNK(linked.st_mode) or not stat.S_ISDIR(linked.st_mode):
            raise FinalizationError(f"candidate parent must be a direct directory: {relative}")


def _read_regular_nofollow(path: Path, *, label: str) -> bytes:
    try:
        before = path.lstat()
        fd = os.open(path, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    except OSError as exc:
        raise FinalizationError(f"candidate cannot be opened safely: {label}") from exc
    try:
        opened = os.fstat(fd)
        if not stat.S_ISREG(opened.st_mode) or opened.st_size > MAX_GIT_SAFE_FILE_BYTES:
            raise FinalizationError(f"candidate is not a bounded regular file: {label}")
        chunks: list[bytes] = []
        remaining = MAX_GIT_SAFE_FILE_BYTES + 1
        while remaining:
            chunk = os.read(fd, min(1024 * 1024, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
    finally:
        os.close(fd)
    try:
        after = path.lstat()
    except OSError as exc:
        raise FinalizationError(f"candidate identity changed while reading: {label}") from exc
    if (
        stat.S_ISLNK(before.st_mode)
        or stat.S_ISLNK(after.st_mode)
        or (before.st_dev, before.st_ino) != (opened.st_dev, opened.st_ino)
        or (after.st_dev, after.st_ino) != (opened.st_dev, opened.st_ino)
        or (before.st_size, after.st_size) != (opened.st_size, opened.st_size)
    ):
        raise FinalizationError(f"candidate identity changed while reading: {label}")
    data = b"".join(chunks)
    if len(data) > MAX_GIT_SAFE_FILE_BYTES or len(data) != opened.st_size:
        raise FinalizationError(f"candidate size changed while reading: {label}")
    return data


def _scan_git_safe_bytes(data: bytes, *, path: str) -> None:
    if len(data) > MAX_GIT_SAFE_FILE_BYTES:
        raise FinalizationError(f"Git-safe candidate file is too large: {path}")
    if b"\0" in data:
        raise FinalizationError(f"binary candidate requires a separate contract: {path}")
    for pattern in SECRET_PATTERNS:
        if pattern.search(data):
            raise FinalizationError(f"high-confidence secret pattern found in: {path}")


def _validate_worktree_entry(repo: Path, item: PlanPath) -> None:
    if _path_is_denied(item):
        raise FinalizationError(f"candidate path belongs to a never-commit category: {item.path}")
    absolute = repo / item.path
    head_mode = _head_mode(repo, item.path)
    in_head = head_mode is not None
    exists = absolute.exists() or absolute.is_symlink()
    if item.state == "deleted":
        if not in_head or exists:
            raise FinalizationError(f"deleted candidate state is false: {item.path}")
        if head_mode not in {"100644", "100755"}:
            raise FinalizationError(f"symlink, submodule, and special deletion is forbidden: {item.path}")
        return
    _validate_path_ancestry(repo, item.path)
    if item.state == "added":
        if in_head or not exists:
            raise FinalizationError(f"added candidate state is false: {item.path}")
        if _git(repo, ["check-ignore", "--quiet", "--", item.path], check=False).returncode == 0:
            raise FinalizationError(f"ignored content cannot be force-added: {item.path}")
    elif item.state == "modified":
        if not in_head or not exists:
            raise FinalizationError(f"modified candidate state is false: {item.path}")
    linked = absolute.lstat()
    if stat.S_ISLNK(linked.st_mode) or not stat.S_ISREG(linked.st_mode):
        raise FinalizationError(f"candidate must be a direct regular file: {item.path}")
    mode = f"0{stat.S_IMODE(linked.st_mode):03o}"
    if mode not in {"0644", "0755"} or mode != item.mode:
        raise FinalizationError(f"candidate mode is not Git-safe: {item.path}")
    if item.state == "modified" and head_mode not in {"100644", "100755"}:
        raise FinalizationError(f"symlink, submodule, and special modification is forbidden: {item.path}")
    data = _read_regular_nofollow(absolute, label=item.path)
    if hashlib.sha256(data).hexdigest() != item.sha256:
        raise FinalizationError(f"candidate bytes or mode changed: {item.path}")
    _scan_git_safe_bytes(data, path=item.path)
    if item.state == "modified":
        head_blob = _git_bytes(repo, ["show", f"HEAD:{item.path}"], check=False)
        expected_mode = "100755" if item.mode == "0755" else "100644"
        if head_blob.returncode != 0:
            raise FinalizationError(f"tracked base bytes are unavailable: {item.path}")
        if head_blob.stdout == data and head_mode == expected_mode:
            raise FinalizationError(f"modified candidate has no exact raw diff: {item.path}")


def _index_paths(repo: Path) -> tuple[str, ...]:
    raw = _git(repo, ["diff", "--cached", "--no-renames", "--name-only", "-z"]).stdout
    return tuple(path for path in raw.split("\0") if path)


def _ensure_empty_index(repo: Path) -> None:
    if _index_paths(repo):
        raise FinalizationError("pre-existing staged changes are forbidden")


def _stage_exact_candidate(repo: Path, plan: CohortPlan) -> None:
    """Populate the index from verified bytes without filters or path re-opening by Git."""
    for item in plan.paths:
        _validate_worktree_entry(repo, item)
        if item.state == "deleted":
            _git(repo, ["update-index", "--force-remove", "--", item.path])
            if (repo / item.path).exists() or (repo / item.path).is_symlink():
                raise FinalizationError(f"deleted candidate reappeared while staging: {item.path}")
            continue
        data = _read_regular_nofollow(repo / item.path, label=item.path)
        if hashlib.sha256(data).hexdigest() != item.sha256:
            raise FinalizationError(f"candidate bytes changed before staging: {item.path}")
        _scan_git_safe_bytes(data, path=item.path)
        blob = _git_bytes(
            repo,
            ["hash-object", "-w", "--stdin"],
            input_bytes=data,
        ).stdout.decode("ascii").strip()
        if HEX_SHA_RE.fullmatch(blob) is None:
            raise FinalizationError(f"Git returned an invalid staged blob identity: {item.path}")
        git_mode = "100755" if item.mode == "0755" else "100644"
        _git(
            repo,
            ["update-index", "--add", "--cacheinfo", f"{git_mode},{blob},{item.path}"],
        )


def _unstage_exact_after_failure(repo: Path, plan: CohortPlan) -> None:
    """Restore the cohort's HEAD entries without refreshing from the worktree."""
    try:
        for item in plan.paths:
            if item.state == "added":
                _git(repo, ["update-index", "--force-remove", "--", item.path])
                continue
            entry = _git(repo, ["ls-tree", "HEAD", "--", item.path], check=False)
            fields = entry.stdout.strip().split(None, 3)
            if (
                entry.returncode != 0
                or len(fields) != 4
                or fields[0] not in {"100644", "100755"}
                or fields[1] != "blob"
                or HEX_SHA_RE.fullmatch(fields[2]) is None
                or fields[3].split("\t", 1)[-1] != item.path
            ):
                raise FinalizationError("HEAD entry cannot be restored safely")
            _git(
                repo,
                [
                    "update-index",
                    "--add",
                    "--cacheinfo",
                    f"{fields[0]},{fields[2]},{item.path}",
                ],
            )
    except FinalizationError:
        raise FinalizationError(
            "pre-commit failure left an unsafe index; delivery is blocked for manual recovery"
        )
    if _index_paths(repo):
        raise FinalizationError(
            "pre-commit failure left an unsafe index; delivery is blocked for manual recovery"
        )


def _create_exact_commit(repo: Path, plan: CohortPlan) -> str:
    """Create and atomically attach one commit without hooks, filters, or status scans."""
    tree = _git(repo, ["write-tree"]).stdout.strip()
    if HEX_SHA_RE.fullmatch(tree) is None:
        raise FinalizationError("Git returned an invalid candidate tree identity")
    commit_env = dict(os.environ)
    for key in tuple(commit_env):
        if key.startswith("GIT_AUTHOR_") or key.startswith("GIT_COMMITTER_") or key == "EMAIL":
            commit_env.pop(key, None)
    commit_env.update(
        {
            "GIT_AUTHOR_NAME": COMMIT_IDENTITY_NAME,
            "GIT_AUTHOR_EMAIL": COMMIT_IDENTITY_EMAIL,
            "GIT_COMMITTER_NAME": COMMIT_IDENTITY_NAME,
            "GIT_COMMITTER_EMAIL": COMMIT_IDENTITY_EMAIL,
        }
    )
    created = _git(
        repo,
        ["-c", "commit.gpgSign=false", "commit-tree", tree, "-p", plan.base_sha],
        check=False,
        input_text=plan.commit_message + "\n",
        env=commit_env,
    )
    commit_sha = created.stdout.strip()
    if created.returncode != 0 or HEX_SHA_RE.fullmatch(commit_sha) is None:
        raise FinalizationError("commit failed; push was not attempted")
    updated = _git(
        repo,
        ["update-ref", f"refs/heads/{plan.branch}", commit_sha, plan.base_sha],
        check=False,
    )
    if updated.returncode != 0:
        raise FinalizationError("commit ref update failed; push was not attempted")
    return commit_sha


def preflight(
    repo: Path,
    plan: CohortPlan,
    *,
    allow_local_remote_for_tests: bool = False,
) -> dict[str, Any]:
    repo = _repo_root(repo)
    if _head(repo) != plan.base_sha:
        raise FinalizationError("HEAD changed after cohort registration")
    for branch in (plan.branch, plan.default_branch):
        if _git(repo, ["check-ref-format", "--branch", branch], check=False).returncode != 0:
            raise FinalizationError("registered branch name is not a valid Git branch")
    if _current_branch(repo) != plan.branch:
        raise FinalizationError("current branch differs from the registered branch")
    remote_url = _remote_url(repo, plan, allow_local_for_tests=allow_local_remote_for_tests)
    _remote_default_branch_at(repo, plan, remote_url)
    remote_sha = _ls_remote_branch(repo, plan, remote_url)
    if remote_sha != plan.base_sha:
        raise FinalizationError("previous cohort is not remotely verified or branch diverged")
    _ensure_empty_index(repo)
    for item in plan.paths:
        _validate_worktree_entry(repo, item)
    return {
        "status": "candidate_ready_for_delivery",
        "cohort_id": plan.cohort_id,
        "plan_sha256": plan.digest,
        "base_sha": plan.base_sha,
        "remote": plan.remote,
        "branch": plan.branch,
        "remote_sha_verified": False,
    }


def _verify_staged_candidate(repo: Path, plan: CohortPlan) -> None:
    for item in plan.paths:
        _validate_worktree_entry(repo, item)
    actual = set(_index_paths(repo))
    expected = {item.path for item in plan.paths}
    if actual != expected:
        raise FinalizationError("staged path set differs from the approved cohort")
    checked = _git(repo, ["diff", "--cached", "--check"], check=False)
    if checked.returncode != 0:
        raise FinalizationError("staged diff has whitespace errors")
    for item in plan.paths:
        staged = _git_bytes(repo, ["show", f":{item.path}"], check=False)
        if item.state == "deleted":
            if staged.returncode == 0:
                raise FinalizationError(f"deleted path remains staged as content: {item.path}")
            continue
        if staged.returncode != 0:
            raise FinalizationError(f"staged content is missing: {item.path}")
        staged_meta = _git(
            repo, ["ls-files", "--stage", "--", item.path], check=False
        )
        fields = staged_meta.stdout.strip().split(None, 3)
        expected_mode = "100755" if item.mode == "0755" else "100644"
        if (
            staged_meta.returncode != 0
            or len(fields) != 4
            or fields[0] != expected_mode
            or fields[2] != "0"
            or fields[3] != item.path
        ):
            raise FinalizationError(f"staged mode or identity differs from plan: {item.path}")
        data = staged.stdout
        if hashlib.sha256(data).hexdigest() != item.sha256:
            raise FinalizationError(f"staged bytes differ from registered bytes: {item.path}")
        _scan_git_safe_bytes(data, path=item.path)


def _verify_commit(repo: Path, plan: CohortPlan, commit_sha: str) -> None:
    raw_commit = _git_bytes(repo, ["cat-file", "commit", commit_sha]).stdout
    _scan_git_safe_bytes(raw_commit, path="delivery commit metadata")
    try:
        header_block, message = raw_commit.split(b"\n\n", 1)
        header_lines = header_block.decode("utf-8", errors="strict").splitlines()
        decoded_message = message.decode("utf-8", errors="strict")
    except (ValueError, UnicodeError) as exc:
        raise FinalizationError("delivery commit metadata is not strict UTF-8") from exc
    identity = re.escape(
        f"{COMMIT_IDENTITY_NAME} <{COMMIT_IDENTITY_EMAIL}>"
    )
    identity_re = re.compile(rf"^(?:author|committer) {identity} [0-9]+ [+-][0-9]{{4}}$")
    if (
        len(header_lines) != 4
        or not header_lines[0].startswith("tree ")
        or header_lines[1] != f"parent {plan.base_sha}"
        or not identity_re.fullmatch(header_lines[2])
        or not identity_re.fullmatch(header_lines[3])
        or not header_lines[2].startswith("author ")
        or not header_lines[3].startswith("committer ")
        or decoded_message != plan.commit_message + "\n"
    ):
        raise FinalizationError("delivery commit metadata differs from the fixed safe identity")
    parents = _git(repo, ["show", "-s", "--format=%P", commit_sha]).stdout.strip().split()
    if parents != [plan.base_sha]:
        raise FinalizationError("delivery commit parent differs from the registered base")
    changed_raw = _git(
        repo,
        [
            "diff-tree",
            "--no-commit-id",
            "--no-renames",
            "--name-only",
            "-r",
            "-z",
            commit_sha,
        ],
    ).stdout
    changed = {path for path in changed_raw.split("\0") if path}
    if changed != {item.path for item in plan.paths}:
        raise FinalizationError("delivery commit path set differs from the approved cohort")
    subject = _git(repo, ["show", "-s", "--format=%s", commit_sha]).stdout.rstrip("\n")
    if subject != plan.commit_message:
        raise FinalizationError("delivery commit subject changed")
    for item in plan.paths:
        blob = _git_bytes(repo, ["show", f"{commit_sha}:{item.path}"], check=False)
        if item.state == "deleted":
            if blob.returncode == 0:
                raise FinalizationError(f"deleted path is present in commit: {item.path}")
            continue
        if blob.returncode != 0:
            raise FinalizationError(f"committed path is missing: {item.path}")
        committed_meta = _git(
            repo, ["ls-tree", commit_sha, "--", item.path], check=False
        )
        fields = committed_meta.stdout.strip().split(None, 3)
        expected_mode = "100755" if item.mode == "0755" else "100644"
        if (
            committed_meta.returncode != 0
            or len(fields) != 4
            or fields[0] != expected_mode
            or fields[1] != "blob"
            or fields[3].split("\t", 1)[-1] != item.path
        ):
            raise FinalizationError(f"committed mode or identity differs from plan: {item.path}")
        data = blob.stdout
        if hashlib.sha256(data).hexdigest() != item.sha256:
            raise FinalizationError(f"committed bytes differ from the plan: {item.path}")


def _receipt_path(repo: Path, plan: CohortPlan) -> Path:
    return repo / RECEIPT_ROOT / f"{plan.cohort_id}.json"


def _ensure_receipt_root(repo: Path) -> Path:
    root = repo / RECEIPT_ROOT
    current = repo
    for part in RECEIPT_ROOT.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            linked = current.lstat()
            if stat.S_ISLNK(linked.st_mode) or not stat.S_ISDIR(linked.st_mode):
                raise FinalizationError("delivery receipt directory is unsafe")
            if stat.S_IMODE(linked.st_mode) & 0o022:
                raise FinalizationError("delivery receipt ancestry is group/world writable")
        else:
            current.mkdir(mode=0o700)
    linked = root.lstat()
    if stat.S_IMODE(linked.st_mode) & 0o077:
        raise FinalizationError("delivery receipt directory must be private")
    return root


def _write_receipt(repo: Path, plan: CohortPlan, payload: dict[str, Any]) -> None:
    root = _ensure_receipt_root(repo)
    destination = _receipt_path(repo, plan)
    if destination.exists() or destination.is_symlink():
        existing = _load_json_regular(destination)
        if (
            existing.get("schema") != "git_safe_cohort_delivery_receipt_v1"
            or existing.get("cohort_id") != plan.cohort_id
            or existing.get("plan_sha256") != plan.digest
            or existing.get("remote") != plan.remote
            or existing.get("branch") != plan.branch
        ):
            raise FinalizationError("existing delivery receipt belongs to another cohort")
    payload = dict(payload)
    payload.update(
        {
            "schema": "git_safe_cohort_delivery_receipt_v1",
            "cohort_id": plan.cohort_id,
            "plan_sha256": plan.digest,
            "remote": plan.remote,
            "branch": plan.branch,
            "updated_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        }
    )
    serialized = (json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode()
    fd, temporary = tempfile.mkstemp(prefix=f".{plan.cohort_id}.", suffix=".tmp", dir=root)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb", closefd=True) as handle:
            handle.write(serialized)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
        directory_fd = os.open(root, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _load_receipt(repo: Path, plan: CohortPlan) -> dict[str, Any]:
    value = _load_json_regular(_receipt_path(repo, plan))
    if (
        value.get("schema") != "git_safe_cohort_delivery_receipt_v1"
        or value.get("cohort_id") != plan.cohort_id
        or value.get("plan_sha256") != plan.digest
        or value.get("remote") != plan.remote
        or value.get("branch") != plan.branch
    ):
        raise FinalizationError("delivery receipt does not match the exact cohort")
    return value


def _load_receipt_optional(repo: Path, plan: CohortPlan) -> dict[str, Any] | None:
    destination = _receipt_path(repo, plan)
    if not destination.exists() and not destination.is_symlink():
        return None
    return _load_receipt(repo, plan)


@contextlib.contextmanager
def _exclusive_delivery_lock(repo: Path):
    current = repo
    for part in LOCK_PATH.parent.parts:
        current = current / part
        if current.exists() or current.is_symlink():
            linked = current.lstat()
            if stat.S_ISLNK(linked.st_mode) or not stat.S_ISDIR(linked.st_mode):
                raise FinalizationError("Git finalizer lock directory is unsafe")
            if stat.S_IMODE(linked.st_mode) & 0o022:
                raise FinalizationError("Git finalizer lock ancestry is group/world writable")
        else:
            current.mkdir(mode=0o700)
    lock_root = repo / LOCK_PATH.parent
    if stat.S_IMODE(lock_root.lstat().st_mode) & 0o077:
        raise FinalizationError("Git finalizer lock directory must be private")
    flags = os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(repo / LOCK_PATH, flags, 0o600)
    except OSError as exc:
        raise FinalizationError("Git finalizer lock cannot be opened safely") from exc
    try:
        os.fchmod(fd, 0o600)
        opened = os.fstat(fd)
        visible = (repo / LOCK_PATH).lstat()
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_ISLNK(visible.st_mode)
            or (opened.st_dev, opened.st_ino) != (visible.st_dev, visible.st_ino)
        ):
            raise FinalizationError("Git finalizer lock identity is ambiguous")
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise FinalizationError("another Git-safe cohort finalizer is active") from exc
        opened_after_lock = os.fstat(fd)
        visible_after_lock = (repo / LOCK_PATH).lstat()
        if (
            not stat.S_ISREG(opened_after_lock.st_mode)
            or stat.S_IMODE(opened_after_lock.st_mode) & 0o077
            or stat.S_ISLNK(visible_after_lock.st_mode)
            or (opened_after_lock.st_dev, opened_after_lock.st_ino)
            != (visible_after_lock.st_dev, visible_after_lock.st_ino)
        ):
            raise FinalizationError("Git finalizer lock changed while acquiring it")
        yield
    finally:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def _push_and_verify(
    repo: Path,
    plan: CohortPlan,
    local_sha: str,
    *,
    allow_local_remote_for_tests: bool = False,
) -> tuple[bool, str]:
    # Resolve and validate the endpoint immediately next to the external effect,
    # then use the literal URL and exact commit SHA.  A symbolic remote name or
    # HEAD would re-open two unbound inputs after approval.
    remote_url = _remote_url(
        repo, plan, allow_local_for_tests=allow_local_remote_for_tests
    )
    _remote_default_branch_at(repo, plan, remote_url)
    before = _ls_remote_branch(repo, plan, remote_url)
    if before not in {plan.base_sha, local_sha}:
        raise FinalizationError("remote branch changed outside the authorized lineage")
    if _head(repo) != local_sha:
        raise FinalizationError("local branch changed before the authorized push")
    if before != local_sha:
        push = _push_exact_commit_from_isolated_config(
            repo, remote_url, local_sha, plan.branch
        )
        if push.returncode != 0:
            return False, "push_failed"
    after = _ls_remote_branch(repo, plan, remote_url)
    if _head(repo) != local_sha:
        raise FinalizationError("local branch changed during the authorized push")
    if _remote_url(
        repo, plan, allow_local_for_tests=allow_local_remote_for_tests
    ) != remote_url:
        raise FinalizationError("remote configuration changed during the authorized push")
    if after != local_sha:
        return False, "remote_sha_mismatch"
    return True, "verified"


def _push_exact_commit_from_isolated_config(
    repo: Path, remote_url: str, local_sha: str, branch: str
) -> subprocess.CompletedProcess[str]:
    """Push one object identity without re-reading the selected repo's config.

    The temporary bare repository has no symbolic remote, worktree, hooks, or
    selected-repository url rewrite rules.  It can read the approved commit via
    the real repository's content-addressed object store.  Global credential
    helpers remain available for the already validated credential-free URL.
    """
    objects = _git(repo, ["rev-parse", "--git-path", "objects"]).stdout.strip()
    object_root = (repo / objects).resolve() if not Path(objects).is_absolute() else Path(objects).resolve()
    if not object_root.is_dir():
        raise FinalizationError("repository object store is unavailable for isolated push")
    credential_args = _approved_credential_args(repo, remote_url)
    push_env = _isolated_remote_environment()
    push_env["GIT_ALTERNATE_OBJECT_DIRECTORIES"] = str(object_root)
    with tempfile.TemporaryDirectory(prefix="git-safe-cohort-push.") as temporary:
        isolated = Path(temporary)
        initialized = subprocess.run(
            [
                "git",
                "-c",
                "init.templateDir=",
                "init",
                "--bare",
                "-q",
            ],
            cwd=isolated,
            env=push_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )
        if initialized.returncode != 0:
            raise FinalizationError("isolated push repository could not be initialized")
        return subprocess.run(
            [
                "git",
                *credential_args,
                "-c",
                "core.hooksPath=/dev/null",
                "push",
                "--porcelain",
                remote_url,
                f"{local_sha}:refs/heads/{branch}",
            ],
            cwd=isolated,
            env=push_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )


def finalize(
    repo: Path,
    plan: CohortPlan,
    *,
    allow_local_remote_for_tests: bool = False,
) -> dict[str, Any]:
    repo = _repo_root(repo)
    with _exclusive_delivery_lock(repo):
        ready = preflight(repo, plan, allow_local_remote_for_tests=allow_local_remote_for_tests)
        _ensure_receipt_root(repo)
        _write_receipt(
            repo,
            plan,
            {
                **ready,
                "status": "finalizing",
                "local_commit_sha": "",
                "remote_commit_sha": "",
                "remote_sha_verified": False,
                "outcome": "pre_commit",
                "retry_history": [],
            },
        )
        committed = False
        try:
            _stage_exact_candidate(repo, plan)
            _verify_staged_candidate(repo, plan)
            local_sha = _create_exact_commit(repo, plan)
            committed = True
        except BaseException:
            if not committed:
                try:
                    _unstage_exact_after_failure(repo, plan)
                except FinalizationError:
                    _write_receipt(
                        repo,
                        plan,
                        {
                            **ready,
                            "status": "incomplete",
                            "local_commit_sha": "",
                            "remote_commit_sha": "",
                            "remote_sha_verified": False,
                            "outcome": "unsafe_index_requires_manual_recovery",
                            "retry_history": [],
                        },
                    )
                    raise
                _write_receipt(
                    repo,
                    plan,
                    {
                        **ready,
                        "status": "incomplete",
                        "local_commit_sha": "",
                        "remote_commit_sha": "",
                        "remote_sha_verified": False,
                        "outcome": "pre_commit_failed",
                        "retry_history": [],
                    },
                )
            raise
        local_sha = _head(repo)
        if local_sha == plan.base_sha:
            raise FinalizationError("commit failed; push was not attempted")
        _write_receipt(
            repo,
            plan,
            {
                **ready,
                "status": "incomplete",
                "local_commit_sha": local_sha,
                "remote_commit_sha": "",
                "remote_sha_verified": False,
                "outcome": "local_commit_created",
                "retry_history": [],
            },
        )
        try:
            _verify_commit(repo, plan, local_sha)
            _ensure_empty_index(repo)
        except FinalizationError:
            _write_receipt(
                repo,
                plan,
                {
                    **ready,
                    "status": "incomplete",
                    "local_commit_sha": local_sha,
                    "remote_commit_sha": "",
                    "remote_sha_verified": False,
                    "outcome": "post_commit_verification_failed",
                    "retry_history": [],
                },
            )
            raise
        try:
            ok, outcome = _push_and_verify(
                repo,
                plan,
                local_sha,
                allow_local_remote_for_tests=allow_local_remote_for_tests,
            )
        except FinalizationError:
            ok, outcome = False, "remote_verification_failed"
        status = "complete" if ok else "incomplete"
        payload = {
            **ready,
            "status": status,
            "local_commit_sha": local_sha,
            "remote_commit_sha": local_sha if ok else "",
            "remote_sha_verified": ok,
            "outcome": outcome,
            "retry_history": [],
        }
        _write_receipt(repo, plan, payload)
        if not ok:
            raise FinalizationError(
                "push did not verify; local commit was preserved and blind retry is forbidden"
            )
        return payload


def retry_push(
    repo: Path,
    plan: CohortPlan,
    *,
    change_evidence: RetryChangeEvidence,
    allow_local_remote_for_tests: bool = False,
) -> dict[str, Any]:
    repo = _repo_root(repo)
    with _exclusive_delivery_lock(repo):
        remote_url = _remote_url(
            repo, plan, allow_local_for_tests=allow_local_remote_for_tests
        )
        _remote_default_branch_at(repo, plan, remote_url)
        if _current_branch(repo) != plan.branch:
            raise FinalizationError("retry target branch changed")
        _ensure_empty_index(repo)
        local_sha = _head(repo)
        if local_sha == plan.base_sha:
            raise FinalizationError("no local delivery commit exists for retry")
        _verify_commit(repo, plan, local_sha)
        receipt = _load_receipt_optional(repo, plan)
        if receipt is None or receipt.get("status") == "finalizing":
            recovery = {
                "status": "incomplete",
                "outcome": "post_commit_recovery_required",
                "local_commit_sha": local_sha,
                "remote_commit_sha": "",
                "remote_sha_verified": False,
                "retry_history": (
                    receipt.get("retry_history", [])
                    if isinstance(receipt, dict)
                    else []
                ),
            }
            _write_receipt(repo, plan, recovery)
            raise FinalizationError(
                "post-commit recovery receipt created; record a new change evidence against it"
            )
        if receipt.get("status") != "incomplete" or receipt.get("outcome") not in {
            "push_failed",
            "remote_sha_mismatch",
            "remote_verification_failed",
            "local_commit_created",
            "post_commit_verification_failed",
            "post_commit_recovery_required",
            "retry_attempting",
        }:
            raise FinalizationError("no failed delivery is eligible for retry")
        if receipt.get("local_commit_sha") != local_sha:
            raise FinalizationError("local delivery commit changed after push failure")
        history = receipt.get("retry_history", [])
        if not isinstance(history, list) or any(not isinstance(item, dict) for item in history):
            raise FinalizationError("retry history is invalid")
        if any(
            item.get("change_id") == change_evidence.change_id
            or item.get("evidence_sha256") == change_evidence.digest
            for item in history
        ):
            raise FinalizationError("retry change evidence was already consumed")
        if change_evidence.previous_attempt_updated_at != receipt.get("updated_at"):
            raise FinalizationError(
                "retry evidence does not bind the immediately previous attempt"
            )
        if history:
            previous_after = history[-1].get("after_fingerprint")
            if change_evidence.before_fingerprint != previous_after:
                raise FinalizationError("retry evidence fingerprint chain is broken")
        history = [
            *history,
            {
                "condition": change_evidence.condition,
                "change_id": change_evidence.change_id,
                "before_fingerprint": change_evidence.before_fingerprint,
                "after_fingerprint": change_evidence.after_fingerprint,
                "summary": change_evidence.summary,
                "recorded_at": change_evidence.recorded_at,
                "previous_attempt_updated_at": change_evidence.previous_attempt_updated_at,
                "evidence_sha256": change_evidence.digest,
            },
        ]
        attempting_payload = {
            "status": "incomplete",
            "local_commit_sha": local_sha,
            "remote_commit_sha": "",
            "remote_sha_verified": False,
            "outcome": "retry_attempting",
            "retry_history": history,
        }
        _write_receipt(repo, plan, attempting_payload)
        try:
            ok, outcome = _push_and_verify(
                repo,
                plan,
                local_sha,
                allow_local_remote_for_tests=allow_local_remote_for_tests,
            )
        except FinalizationError:
            ok, outcome = False, "remote_verification_failed"
        payload = {
            "status": "complete" if ok else "incomplete",
            "local_commit_sha": local_sha,
            "remote_commit_sha": local_sha if ok else "",
            "remote_sha_verified": ok,
            "outcome": outcome,
            "retry_history": history,
        }
        _write_receipt(repo, plan, payload)
        if not ok:
            raise FinalizationError("retry did not verify; another blind retry is forbidden")
        return payload


def verify_delivery(
    repo: Path,
    plan: CohortPlan,
    *,
    allow_local_remote_for_tests: bool = False,
) -> dict[str, Any]:
    repo = _repo_root(repo)
    with _exclusive_delivery_lock(repo):
        remote_url = _remote_url(
            repo, plan, allow_local_for_tests=allow_local_remote_for_tests
        )
        _remote_default_branch_at(repo, plan, remote_url)
        if _current_branch(repo) != plan.branch:
            raise FinalizationError("verification branch changed")
        _ensure_empty_index(repo)
        local_sha = _head(repo)
        _verify_commit(repo, plan, local_sha)
        remote_sha = _ls_remote_branch(repo, plan, remote_url)
        if remote_sha != local_sha:
            raise FinalizationError("remote SHA does not match the exact local delivery commit")
        existing = _load_receipt_optional(repo, plan)
        history: list[dict[str, Any]] = []
        if existing is not None:
            candidate_history = existing.get("retry_history", [])
            if not isinstance(candidate_history, list) or any(
                not isinstance(item, dict) for item in candidate_history
            ):
                raise FinalizationError("retry history is invalid")
            history = candidate_history
        payload = {
            "status": "complete",
            "cohort_id": plan.cohort_id,
            "plan_sha256": plan.digest,
            "local_commit_sha": local_sha,
            "remote_commit_sha": remote_sha,
            "remote": plan.remote,
            "branch": plan.branch,
            "remote_sha_verified": True,
            "outcome": "verified",
            "retry_history": history,
        }
        _write_receipt(repo, plan, payload)
        return payload


def _print_json(payload: dict[str, Any], *, stream: Any = sys.stdout) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), file=stream)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("preflight", "finalize", "retry-push", "verify"))
    parser.add_argument("plan", type=Path)
    parser.add_argument("--repo", type=Path, default=Path.cwd())
    parser.add_argument("--expected-plan-sha256", required=True)
    parser.add_argument("--change-evidence", type=Path)
    args = parser.parse_args(argv)
    try:
        plan = load_plan(
            args.plan, expected_plan_sha256=args.expected_plan_sha256
        )
        if args.action == "preflight":
            if args.change_evidence is not None:
                raise FinalizationError("preflight does not accept retry state")
            payload = preflight(args.repo, plan)
        elif args.action == "finalize":
            if args.change_evidence is not None:
                raise FinalizationError("finalize does not accept retry state")
            payload = finalize(args.repo, plan)
        elif args.action == "retry-push":
            if args.change_evidence is None:
                raise FinalizationError("retry-push requires --change-evidence")
            change_evidence = load_retry_change_evidence(args.change_evidence, plan)
            payload = retry_push(args.repo, plan, change_evidence=change_evidence)
        else:
            if args.change_evidence is not None:
                raise FinalizationError("verify does not accept retry state")
            payload = verify_delivery(args.repo, plan)
    except FinalizationError as exc:
        _print_json(
            {
                "status": "incomplete",
                "remote_sha_verified": False,
                "error": str(exc),
            },
            stream=sys.stderr,
        )
        return 2
    _print_json(payload)
    return 0


if __name__ == "__main__":
    sys.exit(main())
