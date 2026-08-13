"""Repository-scoped kernel lock for consistency mutation transactions.

The lock inode is persistent: ownership is the kernel ``flock``, never a PID
record and never deletion of the lock file.  Callers may pass the same open
file description to a direct child with ``pass_fds``; the child must validate
the descriptor against the anchored public inode before doing any work.
"""

from __future__ import annotations

import errno
import fcntl
import os
import stat
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator


INHERITED_LOCK_FD_ENV = "LIGHT_NOVEL_CONSISTENCY_LOCK_FD"
LOCK_PARTS = (".agent_runtime", "locks")
LOCK_NAME = "consistency_transaction.lock"


def _directory_flags() -> int:
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise RuntimeError("secure consistency locking is unsupported")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _same_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _open_real_directory(path: Path) -> int:
    before = path.lstat()
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
        raise RuntimeError("consistency lock ancestry must be real directories")
    fd = os.open(path, _directory_flags())
    opened = os.fstat(fd)
    after = path.lstat()
    if not _same_identity(before, opened) or not _same_identity(opened, after):
        os.close(fd)
        raise RuntimeError("consistency lock ancestry changed while opening")
    return fd


def _open_lock_parent(repo_root: Path) -> int:
    root = Path(os.path.abspath(repo_root))
    current_fd = _open_real_directory(root)
    try:
        for part in LOCK_PARTS:
            try:
                linked = os.stat(part, dir_fd=current_fd, follow_symlinks=False)
            except FileNotFoundError:
                try:
                    os.mkdir(part, 0o700, dir_fd=current_fd)
                except FileExistsError:
                    pass
                linked = os.stat(part, dir_fd=current_fd, follow_symlinks=False)
            if stat.S_ISLNK(linked.st_mode) or not stat.S_ISDIR(linked.st_mode):
                raise RuntimeError("consistency lock ancestry must be real directories")
            child_fd = os.open(part, _directory_flags(), dir_fd=current_fd)
            opened = os.fstat(child_fd)
            visible = os.stat(part, dir_fd=current_fd, follow_symlinks=False)
            if not _same_identity(linked, opened) or not _same_identity(opened, visible):
                os.close(child_fd)
                raise RuntimeError("consistency lock ancestry changed while opening")
            os.close(current_fd)
            current_fd = child_fd
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def _validate_lock_fd(parent_fd: int, lock_fd: int) -> None:
    linked = os.stat(LOCK_NAME, dir_fd=parent_fd, follow_symlinks=False)
    opened = os.fstat(lock_fd)
    visible = os.stat(LOCK_NAME, dir_fd=parent_fd, follow_symlinks=False)
    if (
        stat.S_ISLNK(linked.st_mode)
        or not stat.S_ISREG(linked.st_mode)
        or not stat.S_ISREG(opened.st_mode)
        or not _same_identity(linked, opened)
        or not _same_identity(opened, visible)
        or stat.S_IMODE(opened.st_mode) & 0o077
    ):
        raise RuntimeError("consistency lock inode is ambiguous or insecure")


@dataclass
class ConsistencyLock:
    fd: int
    inherited: bool

    def child_environment(self) -> dict[str, str]:
        return {INHERITED_LOCK_FD_ENV: str(self.fd)}


@contextmanager
def exclusive_consistency_lock(repo_root: Path) -> Iterator[ConsistencyLock]:
    """Acquire or validate the single nonblocking consistency transaction lock."""

    parent_fd = _open_lock_parent(repo_root)
    lock_fd: int | None = None
    inherited = False
    try:
        inherited_raw = os.environ.get(INHERITED_LOCK_FD_ENV)
        if inherited_raw is not None:
            try:
                lock_fd = int(inherited_raw, 10)
            except ValueError as exc:
                raise RuntimeError("inherited consistency lock descriptor is invalid") from exc
            if lock_fd < 0:
                raise RuntimeError("inherited consistency lock descriptor is invalid")
            inherited = True
            _validate_lock_fd(parent_fd, lock_fd)
        else:
            flags = os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
            try:
                lock_fd = os.open(LOCK_NAME, flags, 0o600, dir_fd=parent_fd)
            except OSError as exc:
                raise RuntimeError("consistency lock inode cannot be opened safely") from exc
            os.fchmod(lock_fd, 0o600)
            _validate_lock_fd(parent_fd, lock_fd)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            if exc.errno in {errno.EACCES, errno.EAGAIN}:
                raise RuntimeError("another consistency transaction holds the lock") from exc
            raise RuntimeError("consistency lock cannot be acquired safely") from exc
        _validate_lock_fd(parent_fd, lock_fd)
        yield ConsistencyLock(fd=lock_fd, inherited=inherited)
        _validate_lock_fd(parent_fd, lock_fd)
    finally:
        if lock_fd is not None and not inherited:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_UN)
            finally:
                os.close(lock_fd)
        os.close(parent_fd)
