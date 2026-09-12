from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import review_workspace_storage as storage  # noqa: E402


def _fake_guard(tmp_path: Path, output: Path) -> Path:
    guard = tmp_path / "guard.sh"
    guard.write_text(
        "#!/bin/sh\n"
        f"printf '%s\\n' '{output}'\n",
        encoding="utf-8",
    )
    guard.chmod(0o755)
    return guard


def _configure(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[Path, Path, Path]:
    project = tmp_path / "project"
    project.mkdir()
    compatibility_root = tmp_path / "compatibility-project"
    compatibility_root.symlink_to(project, target_is_directory=True)
    parent = tmp_path / "external" / "chapter_review"
    root = parent / "workspace_review"
    root.mkdir(parents=True)
    monkeypatch.setattr(storage, "REPO_ROOT", project)
    monkeypatch.setattr(storage, "LEGACY_INTERNAL_ROOT", project / "workspace" / "review")
    monkeypatch.setattr(storage, "COMPATIBILITY_REPO_ROOT", compatibility_root)
    monkeypatch.setattr(storage, "EXPECTED_VOLUME_ROOT", tmp_path / "external")
    monkeypatch.setattr(storage, "EXPECTED_PARENT", parent)
    monkeypatch.setattr(storage, "EXPECTED_ROOT", root)
    monkeypatch.setattr(storage, "COMMON_GUARD", _fake_guard(tmp_path, parent))
    return project, compatibility_root, root


def test_compatibility_symlink_path_routes_to_guarded_workspace(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, compatibility_root, root = _configure(monkeypatch, tmp_path)
    requested = compatibility_root / "workspace" / "review" / "issue_report.json"
    assert storage.reroute_legacy_review_path(requested) == root / "issue_report.json"


def test_existing_symlink_component_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, root = _configure(monkeypatch, tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    (root / "escape").symlink_to(outside, target_is_directory=True)
    with pytest.raises(storage.ReviewWorkspaceStorageError, match="contains a symlink"):
        storage.review_workspace_path("escape", "report.json")


def test_parent_on_another_device_is_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, _, root = _configure(monkeypatch, tmp_path)

    class OtherDeviceVolume:
        def is_dir(self) -> bool:
            return True

        def is_symlink(self) -> bool:
            return False

        def resolve(self, *, strict: bool) -> OtherDeviceVolume:
            return self

        def stat(self):
            return type("Stat", (), {"st_dev": root.stat().st_dev + 1})()

    monkeypatch.setattr(storage, "EXPECTED_VOLUME_ROOT", OtherDeviceVolume())
    with pytest.raises(storage.ReviewWorkspaceStorageError, match="crossed the guarded volume"):
        storage.review_workspace_root()


def test_nonlegacy_explicit_path_is_preserved(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _configure(monkeypatch, tmp_path)
    explicit = tmp_path / "isolated" / "report.json"
    assert storage.reroute_legacy_review_path(explicit) == explicit
