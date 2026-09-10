"""Resolve project indexes through the registered external-storage guard.

Production defaults under ``workspace/indexes`` are routed to the verified
external index root.  There is no production fallback to the internal legacy
directory.  Explicit non-legacy paths and fixture repositories remain
available for tests and ad-hoc isolated tooling.
"""

from __future__ import annotations

import os
import stat
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
COMMON_GUARD = Path("/Users/alalapi/.config/storage-governance/guard.sh")
MAP_KEY = "mappings.light_novel.index_root"
EXPECTED_VOLUME_ROOT = Path("/Volumes/AI_WORK_SSD")
EXPECTED_ROOT = EXPECTED_VOLUME_ROOT / "ProjectData" / "light_novel" / "indexes"


class IndexWorkspaceStorageError(RuntimeError):
    """The guarded external index workspace cannot be used safely."""


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(path))


def _canonical_repo_root(path: Path) -> Path:
    absolute = _absolute(path)
    try:
        return absolute.resolve(strict=True)
    except OSError:
        return absolute


def _validate_relative(relative: Path) -> None:
    if relative.is_absolute() or not relative.parts:
        raise IndexWorkspaceStorageError("index path must be relative")
    if any(part in {"", ".", ".."} for part in relative.parts):
        raise IndexWorkspaceStorageError("index path traversal is forbidden")


def _guarded_root() -> Path:
    if not COMMON_GUARD.is_file() or not os.access(COMMON_GUARD, os.X_OK):
        raise IndexWorkspaceStorageError("storage guard is missing or not executable")
    proc = subprocess.run(
        [str(COMMON_GUARD), "--get-path", MAP_KEY],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or "external storage identity check failed"
        raise IndexWorkspaceStorageError(detail)
    resolved = Path(proc.stdout.strip())
    if resolved != EXPECTED_ROOT:
        raise IndexWorkspaceStorageError("index root mapping drifted")
    if not resolved.is_dir() or not os.access(resolved, os.R_OK | os.W_OK):
        raise IndexWorkspaceStorageError("guarded index root is unavailable")
    if resolved.is_symlink() or resolved.resolve(strict=True) != EXPECTED_ROOT:
        raise IndexWorkspaceStorageError("index root is not the guarded physical path")
    if not EXPECTED_VOLUME_ROOT.is_dir():
        raise IndexWorkspaceStorageError("guarded volume root is unavailable")
    if resolved.stat().st_dev != EXPECTED_VOLUME_ROOT.stat().st_dev:
        raise IndexWorkspaceStorageError("index root crossed the guarded filesystem")
    return resolved


def _guarded_path(root: Path, relative: Path) -> Path:
    _validate_relative(relative)
    root_device = root.lstat().st_dev
    candidate = root / relative
    current = root
    for component in relative.parts:
        current = current / component
        try:
            current_stat = current.lstat()
        except FileNotFoundError:
            break
        if stat.S_ISLNK(current_stat.st_mode):
            raise IndexWorkspaceStorageError("index path contains a symlink")
        if current_stat.st_dev != root_device:
            raise IndexWorkspaceStorageError("index path crossed the guarded filesystem")
    try:
        candidate.resolve(strict=False).relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise IndexWorkspaceStorageError("index path escaped its root") from exc
    return candidate


def index_workspace_root(*, repo_root: Path = PROJECT_ROOT) -> Path:
    """Return the guarded root in production and the local root for fixtures."""
    normalized_repo = _canonical_repo_root(repo_root)
    if normalized_repo != PROJECT_ROOT:
        return normalized_repo / "workspace" / "indexes"
    return _guarded_root()


def index_workspace_path(*relative_parts: str, repo_root: Path = PROJECT_ROOT) -> Path:
    """Resolve a safe index path for the production or fixture repository."""
    relative = Path(*relative_parts)
    _validate_relative(relative)
    normalized_repo = _canonical_repo_root(repo_root)
    if normalized_repo != PROJECT_ROOT:
        return normalized_repo / "workspace" / "indexes" / relative
    return _guarded_path(_guarded_root(), relative)


def reroute_legacy_index_path(requested: Path, *, repo_root: Path = PROJECT_ROOT) -> Path:
    """Map a logical ``workspace/indexes`` path externally in production."""
    lexical_repo = _absolute(repo_root)
    normalized_repo = _canonical_repo_root(repo_root)
    requested_absolute = requested if requested.is_absolute() else lexical_repo / requested
    requested_absolute = _absolute(requested_absolute)
    relative = None
    for legacy_root in {
        lexical_repo / "workspace" / "indexes",
        normalized_repo / "workspace" / "indexes",
    }:
        try:
            relative = requested_absolute.relative_to(legacy_root)
            break
        except ValueError:
            continue
    if relative is None:
        return requested_absolute
    if normalized_repo != PROJECT_ROOT:
        return requested_absolute
    if not relative.parts:
        return _guarded_root()
    return _guarded_path(_guarded_root(), relative)
