#!/usr/bin/env python3
"""Resolve the review-report workspace through the external-storage guard.

There is deliberately no internal fallback.  Callers fail closed when the
registered external volume is absent or its volume/container identity drifts.
"""

from __future__ import annotations

import argparse
import os
import stat
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
COMMON_GUARD = Path("/Users/alalapi/.config/storage-governance/guard.sh")
MAP_KEY = "mappings.light_novel.chapter_review_root"
EXPECTED_VOLUME_ROOT = Path("/Volumes/AI_WORK_SSD")
EXPECTED_PARENT = Path("/Volumes/AI_WORK_SSD/ProjectData/light_novel/chapter_review")
EXPECTED_ROOT = EXPECTED_PARENT / "workspace_review"
LEGACY_INTERNAL_ROOT = REPO_ROOT / "workspace" / "review"
COMPATIBILITY_REPO_ROOT = Path("/Users/alalapi/PycharmProjects/light_novel")


class ReviewWorkspaceStorageError(RuntimeError):
    """The guarded external review workspace cannot be used safely."""


def _guarded_parent() -> Path:
    if not COMMON_GUARD.is_file() or not os.access(COMMON_GUARD, os.X_OK):
        raise ReviewWorkspaceStorageError("storage guard is missing or not executable")
    proc = subprocess.run(
        [str(COMMON_GUARD), "--get-path", MAP_KEY],
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        detail = proc.stderr.strip() or "external storage identity check failed"
        raise ReviewWorkspaceStorageError(detail)
    resolved = Path(proc.stdout.strip())
    if resolved != EXPECTED_PARENT:
        raise ReviewWorkspaceStorageError("review workspace parent mapping drifted")
    if not resolved.is_dir():
        raise ReviewWorkspaceStorageError("guarded review workspace parent is unavailable")
    if resolved.is_symlink() or resolved.resolve(strict=True) != EXPECTED_PARENT:
        raise ReviewWorkspaceStorageError("review workspace parent is not the guarded physical path")
    if (
        not EXPECTED_VOLUME_ROOT.is_dir()
        or EXPECTED_VOLUME_ROOT.is_symlink()
        or EXPECTED_VOLUME_ROOT.resolve(strict=True) != EXPECTED_VOLUME_ROOT
        or resolved.stat().st_dev != EXPECTED_VOLUME_ROOT.stat().st_dev
    ):
        raise ReviewWorkspaceStorageError("review workspace parent crossed the guarded volume")
    return resolved


def review_workspace_root() -> Path:
    parent = _guarded_parent()
    root = parent / "workspace_review"
    if root != EXPECTED_ROOT:
        raise ReviewWorkspaceStorageError("review workspace route drifted")
    if not root.is_dir() or not os.access(root, os.R_OK | os.W_OK):
        raise ReviewWorkspaceStorageError("guarded review workspace is unavailable")
    if root.is_symlink() or root.resolve(strict=True) != EXPECTED_ROOT:
        raise ReviewWorkspaceStorageError("review workspace is not the guarded physical path")
    if root.stat().st_dev != parent.stat().st_dev:
        raise ReviewWorkspaceStorageError("review workspace crossed the guarded filesystem")
    return root


def review_workspace_path(*relative_parts: str) -> Path:
    if not relative_parts:
        raise ReviewWorkspaceStorageError("review workspace path must be relative")
    for raw_part in relative_parts:
        if not raw_part or raw_part.startswith("/"):
            raise ReviewWorkspaceStorageError("review workspace path must be relative")
        if any(component in {"", ".", ".."} for component in raw_part.split("/")):
            raise ReviewWorkspaceStorageError("review workspace path traversal is forbidden")
    relative = Path(*relative_parts)
    if relative.is_absolute():
        raise ReviewWorkspaceStorageError("review workspace path must be relative")
    root = review_workspace_root()
    root_device = root.lstat().st_dev
    candidate = root / relative
    deepest_existing = root
    current = root
    for component in relative.parts:
        current = current / component
        try:
            current_stat = current.lstat()
        except FileNotFoundError:
            break
        if stat.S_ISLNK(current_stat.st_mode):
            raise ReviewWorkspaceStorageError("review workspace path contains a symlink")
        if current_stat.st_dev != root_device:
            raise ReviewWorkspaceStorageError("review workspace path crossed the guarded filesystem")
        deepest_existing = current
    if deepest_existing.lstat().st_dev != root_device:
        raise ReviewWorkspaceStorageError("review workspace ancestor crossed the guarded filesystem")
    try:
        candidate.resolve(strict=False).relative_to(root.resolve(strict=True))
    except ValueError as exc:
        raise ReviewWorkspaceStorageError("review workspace path escaped its root") from exc
    return candidate


def reroute_legacy_review_path(requested: Path) -> Path:
    """Map an old workspace/review path externally; preserve other explicit paths."""
    requested_absolute = requested if requested.is_absolute() else Path.cwd() / requested
    requested_absolute = Path(os.path.abspath(requested_absolute))
    legacy_roots = [LEGACY_INTERNAL_ROOT]
    try:
        if (
            COMPATIBILITY_REPO_ROOT.is_symlink()
            and COMPATIBILITY_REPO_ROOT.resolve(strict=True) == REPO_ROOT.resolve(strict=True)
        ):
            legacy_roots.append(COMPATIBILITY_REPO_ROOT / "workspace" / "review")
    except OSError:
        pass
    for legacy_root in legacy_roots:
        try:
            relative = requested_absolute.relative_to(legacy_root)
        except ValueError:
            continue
        if not relative.parts:
            return review_workspace_root()
        return review_workspace_path(*relative.parts)
    return requested


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve the guarded review workspace")
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--check", action="store_true")
    group.add_argument("--root", action="store_true")
    group.add_argument("--path", metavar="RELATIVE_PATH")
    args = parser.parse_args(argv)
    try:
        if args.path is not None:
            print(review_workspace_path(args.path))
        elif args.root:
            print(review_workspace_root())
        else:
            print(f"review workspace: OK {review_workspace_root()}")
    except ReviewWorkspaceStorageError as exc:
        print(f"review workspace: {exc}", file=sys.stderr)
        return 78
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
