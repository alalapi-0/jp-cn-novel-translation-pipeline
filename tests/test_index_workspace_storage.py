from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from consistency import index_workspace_storage as storage  # noqa: E402


def _fake_guard(tmp_path: Path, output: Path, *, exit_code: int = 0) -> Path:
    guard = tmp_path / "guard.sh"
    guard.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' '{output}'\n"
        f"exit {exit_code}\n",
        encoding="utf-8",
    )
    guard.chmod(0o755)
    return guard


def _configure_production_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    *,
    guard_output: Path | None = None,
) -> tuple[Path, Path]:
    project = tmp_path / "project"
    project.mkdir()
    external = tmp_path / "external" / "indexes"
    external.mkdir(parents=True)
    output = guard_output or external
    monkeypatch.setattr(storage, "PROJECT_ROOT", project)
    monkeypatch.setattr(storage, "EXPECTED_VOLUME_ROOT", tmp_path / "external")
    monkeypatch.setattr(storage, "EXPECTED_ROOT", external)
    monkeypatch.setattr(storage, "COMMON_GUARD", _fake_guard(tmp_path, output))
    return project, external


def test_fixture_repository_keeps_local_index_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(storage, "COMMON_GUARD", tmp_path / "missing-guard")
    fixture_repo = tmp_path / "fixture"
    requested = Path("workspace/indexes/segment_index.json")
    assert storage.reroute_legacy_index_path(requested, repo_root=fixture_repo) == (
        fixture_repo / requested
    )


def test_production_legacy_path_routes_to_guarded_external_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, external = _configure_production_fixture(monkeypatch, tmp_path)
    requested = Path("workspace/indexes/entity_index.json")
    assert storage.reroute_legacy_index_path(requested, repo_root=project) == (
        external / "entity_index.json"
    )


def test_compatibility_symlink_repo_routes_to_guarded_external_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, external = _configure_production_fixture(monkeypatch, tmp_path)
    compatibility_root = tmp_path / "compatibility-project"
    compatibility_root.symlink_to(project, target_is_directory=True)
    requested = compatibility_root / "workspace" / "indexes" / "entity_index.json"
    assert storage.reroute_legacy_index_path(
        requested,
        repo_root=compatibility_root,
    ) == external / "entity_index.json"


def test_mapping_drift_fails_closed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    wrong = tmp_path / "wrong" / "indexes"
    wrong.mkdir(parents=True)
    project, _ = _configure_production_fixture(
        monkeypatch,
        tmp_path,
        guard_output=wrong,
    )
    with pytest.raises(storage.IndexWorkspaceStorageError, match="mapping drifted"):
        storage.reroute_legacy_index_path(
            Path("workspace/indexes/segment_index.json"),
            repo_root=project,
        )


def test_explicit_nonlegacy_path_is_preserved(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project, _ = _configure_production_fixture(monkeypatch, tmp_path)
    explicit = tmp_path / "isolated" / "index.json"
    assert storage.reroute_legacy_index_path(explicit, repo_root=project) == explicit


def test_relative_traversal_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(storage.IndexWorkspaceStorageError, match="traversal"):
        storage.index_workspace_path("..", "escape.json", repo_root=tmp_path)
