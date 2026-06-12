"""Baseline draft write protection (FS-038).

Refuses pipeline writes to ``draft_full_baseline/`` and metadata once locked.
"""

from __future__ import annotations

import os
import stat
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from translation.run_progress import safe_load_json

BASELINE_DIR_NAME = "draft_full_baseline"
BASELINE_METADATA_NAME = "draft_full_baseline_metadata.json"

_bypass_guard = False


class BaselineWriteError(PermissionError):
    """Raised when pipeline code attempts to mutate a locked baseline path."""


def baseline_dir(repo_root: Path) -> Path:
    return repo_root / BASELINE_DIR_NAME


def baseline_metadata_path(repo_root: Path) -> Path:
    return repo_root / BASELINE_METADATA_NAME


def _find_repo_root(path: Path) -> Path | None:
    resolved = path.resolve()
    for parent in [resolved, *resolved.parents]:
        if (parent / BASELINE_METADATA_NAME).is_file() or (parent / ".git").is_dir():
            return parent
    return None


def is_baseline_protected_path(path: Path, repo_root: Path | None = None) -> bool:
    resolved = path.resolve()
    root = (repo_root or _find_repo_root(resolved))
    if root is None:
        return BASELINE_DIR_NAME in resolved.parts or resolved.name == BASELINE_METADATA_NAME
    try:
        resolved.relative_to(baseline_dir(root))
        return True
    except ValueError:
        pass
    if resolved == baseline_metadata_path(root).resolve():
        return True
    return False


def is_baseline_locked(repo_root: Path) -> bool:
    meta_path = baseline_metadata_path(repo_root)
    if not meta_path.is_file():
        return False
    meta = safe_load_json(meta_path) or {}
    if not meta.get("locked"):
        return False
    return baseline_dir(repo_root).is_dir()


def assert_baseline_writable(path: Path, repo_root: Path | None = None) -> None:
    """Raise ``BaselineWriteError`` if ``path`` is a locked baseline target."""
    if _bypass_guard:
        return
    resolved = path.resolve()
    root = repo_root or _find_repo_root(resolved)
    if root is None:
        return
    if not is_baseline_locked(root):
        return
    if is_baseline_protected_path(resolved, root):
        rel = resolved.relative_to(root) if resolved.is_relative_to(root) else resolved
        raise BaselineWriteError(
            f"baseline is locked; refusing write to {rel} "
            f"(see {BASELINE_METADATA_NAME})"
        )


def guarded_mkdir(path: Path, repo_root: Path | None = None, **kwargs) -> None:
    assert_baseline_writable(path, repo_root)
    path.mkdir(**kwargs)


def guarded_write_text(path: Path, content: str, *, repo_root: Path | None = None) -> None:
    assert_baseline_writable(path, repo_root)
    path.write_text(content, encoding="utf-8")


@contextmanager
def baseline_write_override() -> Iterator[None]:
    """Allow baseline lock script to populate baseline before read-only is applied."""
    global _bypass_guard
    prev = _bypass_guard
    _bypass_guard = True
    try:
        yield
    finally:
        _bypass_guard = prev


def apply_baseline_readonly(repo_root: Path) -> int:
    """Set baseline tree to owner read+execute, no write. Returns files touched."""
    base = baseline_dir(repo_root)
    if not base.is_dir():
        return 0
    dir_mode = stat.S_IRUSR | stat.S_IXUSR | stat.S_IRGRP | stat.S_IXGRP | stat.S_IROTH | stat.S_IXOTH
    file_mode = stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH
    touched = 0
    for root, dirs, files in os.walk(base, topdown=False):
        root_path = Path(root)
        for name in files:
            fp = root_path / name
            os.chmod(fp, file_mode)
            touched += 1
        for name in dirs:
            dp = root_path / name
            os.chmod(dp, dir_mode)
            touched += 1
    os.chmod(base, dir_mode)
    meta_path = baseline_metadata_path(repo_root)
    if meta_path.is_file():
        os.chmod(meta_path, file_mode)
        touched += 1
    return touched
