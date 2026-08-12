from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "tool_probe.py"


def _load_tool_probe():
    spec = importlib.util.spec_from_file_location("tool_probe_local_binary_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def tool_probe():
    return _load_tool_probe()


def _set_repo_root(tool_probe, tmp_path: Path, monkeypatch) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    monkeypatch.setattr(tool_probe, "REPO_ROOT", repo)
    return repo


def _local_binary(repo: Path, name: str, *, executable: bool = True) -> Path:
    binary = repo / "node_modules" / ".bin" / name
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    binary.chmod(0o755 if executable else 0o644)
    return binary


@pytest.mark.parametrize(
    ("name", "probe_name", "availability_key", "detail_key"),
    [
        ("playwright", "_probe_playwright_offline", "npx_playwright", "version"),
        ("prisma", "_probe_prisma_offline", "npx_prisma", "detail"),
    ],
)
def test_local_node_probe_invokes_only_repo_anchored_executable(
    tmp_path: Path,
    monkeypatch,
    tool_probe,
    name: str,
    probe_name: str,
    availability_key: str,
    detail_key: str,
) -> None:
    repo = _set_repo_root(tool_probe, tmp_path, monkeypatch)
    binary = _local_binary(repo, name)
    calls: list[list[str] | str] = []

    def fake_run(command, *, timeout=15):
        calls.append(command)
        return {"exit_code": 0, "output": "Version 1.2.3", "available": True}

    monkeypatch.setattr(tool_probe, "_run", fake_run)
    result = getattr(tool_probe, probe_name)()

    assert result[availability_key] is True
    assert result[detail_key] == "Version 1.2.3"
    assert calls == [[str(binary), "--version"]]
    assert not any(
        token in str(calls).lower()
        for token in ("npx", "npm", "pnpm", "yarn", "install", "http")
    )


@pytest.mark.parametrize(
    ("name", "probe_name", "availability_key", "detail_key"),
    [
        ("playwright", "_probe_playwright_offline", "npx_playwright", "version"),
        ("prisma", "_probe_prisma_offline", "npx_prisma", "detail"),
    ],
)
@pytest.mark.parametrize("binary_state", ["missing", "non_executable"])
def test_local_node_probe_fails_closed_without_invoking_runner(
    tmp_path: Path,
    monkeypatch,
    tool_probe,
    name: str,
    probe_name: str,
    availability_key: str,
    detail_key: str,
    binary_state: str,
) -> None:
    repo = _set_repo_root(tool_probe, tmp_path, monkeypatch)
    if binary_state == "non_executable":
        _local_binary(repo, name, executable=False)

    def forbidden_run(*_args, **_kwargs):
        raise AssertionError("missing/non-executable local probes must not run a command")

    monkeypatch.setattr(tool_probe, "_run", forbidden_run)
    result = getattr(tool_probe, probe_name)()

    assert result[availability_key] is False
    assert result[detail_key].startswith("BLOCKED_ENV:")


def test_probe_local_tools_uses_same_repo_local_playwright_rule(
    tmp_path: Path,
    monkeypatch,
    tool_probe,
) -> None:
    repo = _set_repo_root(tool_probe, tmp_path, monkeypatch)
    binary = _local_binary(repo, "playwright")
    calls: list[list[str] | str] = []

    def fake_run(command, *, timeout=15):
        calls.append(command)
        return {"exit_code": 0, "output": "ok", "available": True}

    monkeypatch.setattr(tool_probe, "_run", fake_run)
    probes = tool_probe.probe_local_tools()

    assert probes["playwright_npx"]["available"] is True
    assert [str(binary), "--version"] in calls
    assert not any(
        isinstance(command, str) and "npx" in command.lower()
        for command in calls
    )
    assert not any(
        isinstance(command, list)
        and command
        and command[0] in {"npx", "npm", "pnpm", "yarn"}
        for command in calls
    )


def test_probe_local_tools_missing_playwright_is_compatible_blocked_env(
    tmp_path: Path,
    monkeypatch,
    tool_probe,
) -> None:
    _set_repo_root(tool_probe, tmp_path, monkeypatch)

    def fake_run(_command, *, timeout=15):
        return {"exit_code": 127, "output": "unavailable", "available": False}

    monkeypatch.setattr(tool_probe, "_run", fake_run)
    result = tool_probe.probe_local_tools()["playwright_npx"]

    assert result == {
        "exit_code": 127,
        "output": "BLOCKED_ENV: node_modules/.bin/playwright missing or not executable",
        "available": False,
    }


@pytest.mark.parametrize(
    ("name", "probe_name", "availability_key"),
    [
        ("playwright", "_probe_playwright_offline", "npx_playwright"),
        ("prisma", "_probe_prisma_offline", "npx_prisma"),
    ],
)
def test_repo_internal_symlink_resolves_and_executes_inside_node_modules(
    tmp_path: Path,
    monkeypatch,
    tool_probe,
    name: str,
    probe_name: str,
    availability_key: str,
) -> None:
    repo = _set_repo_root(tool_probe, tmp_path, monkeypatch)
    target = repo / "node_modules" / f"{name}-package" / "cli"
    target.parent.mkdir(parents=True)
    target.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    target.chmod(0o755)
    binary = repo / "node_modules" / ".bin" / name
    binary.parent.mkdir(parents=True)
    binary.symlink_to(Path("..") / f"{name}-package" / "cli")
    calls: list[list[str] | str] = []

    def fake_run(command, *, timeout=15):
        calls.append(command)
        return {"exit_code": 0, "output": "Version 1.2.3", "available": True}

    monkeypatch.setattr(tool_probe, "_run", fake_run)
    result = getattr(tool_probe, probe_name)()

    assert result[availability_key] is True
    assert calls == [[str(target), "--version"]]


@pytest.mark.parametrize(
    ("name", "probe_name", "availability_key", "detail_key"),
    [
        ("playwright", "_probe_playwright_offline", "npx_playwright", "version"),
        ("prisma", "_probe_prisma_offline", "npx_prisma", "detail"),
    ],
)
def test_repo_local_spelling_rejects_symlink_target_outside_repository(
    tmp_path: Path,
    monkeypatch,
    tool_probe,
    name: str,
    probe_name: str,
    availability_key: str,
    detail_key: str,
) -> None:
    repo = _set_repo_root(tool_probe, tmp_path, monkeypatch)
    outside = tmp_path / f"outside-{name}"
    outside.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    outside.chmod(0o755)
    binary = repo / "node_modules" / ".bin" / name
    binary.parent.mkdir(parents=True)
    binary.symlink_to(outside)

    def forbidden_run(*_args, **_kwargs):
        raise AssertionError("external symlink targets must never execute")

    monkeypatch.setattr(tool_probe, "_run", forbidden_run)
    direct = tool_probe._probe_repo_local_node_binary(name)
    result = getattr(tool_probe, probe_name)()

    assert direct["available"] is False
    assert "outside repository" in direct["output"]
    assert str(outside) not in direct["output"]
    assert result[availability_key] is False
    assert result[detail_key].startswith("BLOCKED_ENV:")
    assert str(outside) not in result[detail_key]


@pytest.mark.parametrize(
    ("name", "probe_name", "availability_key", "detail_key"),
    [
        ("playwright", "_probe_playwright_offline", "npx_playwright", "version"),
        ("prisma", "_probe_prisma_offline", "npx_prisma", "detail"),
    ],
)
@pytest.mark.parametrize("link_state", ["broken", "loop"])
def test_repo_local_probe_rejects_broken_or_looping_symlink(
    tmp_path: Path,
    monkeypatch,
    tool_probe,
    name: str,
    probe_name: str,
    availability_key: str,
    detail_key: str,
    link_state: str,
) -> None:
    repo = _set_repo_root(tool_probe, tmp_path, monkeypatch)
    binary = repo / "node_modules" / ".bin" / name
    binary.parent.mkdir(parents=True)
    if link_state == "broken":
        binary.symlink_to(Path("..") / "missing-package" / "cli")
    else:
        binary.symlink_to(binary.name)

    def forbidden_run(*_args, **_kwargs):
        raise AssertionError("broken or looping symlinks must never execute")

    monkeypatch.setattr(tool_probe, "_run", forbidden_run)
    result = getattr(tool_probe, probe_name)()

    assert result[availability_key] is False
    assert result[detail_key].startswith("BLOCKED_ENV:")
