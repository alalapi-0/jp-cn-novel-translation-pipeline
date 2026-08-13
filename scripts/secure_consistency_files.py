"""No-follow, descriptor-anchored regular-file operations for consistency tools."""

from __future__ import annotations

import os
import ctypes
import errno
import secrets
import stat
import sys
from dataclasses import dataclass
from pathlib import Path


def _dir_flags() -> int:
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise RuntimeError("secure consistency file operations are unsupported")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _identity(value: os.stat_result) -> tuple[int, int]:
    return value.st_dev, value.st_ino


def _rename_with_flag(
    source_fd: int, source: str, destination_fd: int, destination: str, flag: int
) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    rename = getattr(libc, "renameatx_np" if sys.platform == "darwin" else "renameat2", None)
    if rename is None:
        raise RuntimeError("secure atomic consistency publication is unsupported")
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(source_fd, os.fsencode(source), destination_fd, os.fsencode(destination), flag) == 0:
        return
    error = ctypes.get_errno()
    if error in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(error, os.strerror(error), destination)
    raise OSError(error, os.strerror(error), destination)


def _atomic_exchange(parent_fd: int, source: str, destination: str) -> None:
    _rename_with_flag(parent_fd, source, parent_fd, destination, 0x00000002)


def _atomic_noreplace(parent_fd: int, source: str, destination: str) -> None:
    flag = 0x00000004 if sys.platform == "darwin" else 0x00000001
    _rename_with_flag(parent_fd, source, parent_fd, destination, flag)


def _inject(_boundary: str) -> None:
    """Deterministic synthetic race boundary; production is a no-op."""


def _unlink_owned(parent_fd: int, name: str, expected: tuple[int, int]) -> bool:
    try:
        visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
    except FileNotFoundError:
        return True
    if stat.S_ISLNK(visible.st_mode) or not stat.S_ISREG(visible.st_mode) or _identity(visible) != expected:
        return False
    os.unlink(name, dir_fd=parent_fd)
    return True


def open_parent(path: Path, *, create: bool = False) -> tuple[int, str]:
    absolute = Path(os.path.abspath(path))
    parts = absolute.parts
    fd = os.open(parts[0], _dir_flags())
    try:
        for part in parts[1:-1]:
            try:
                linked = os.stat(part, dir_fd=fd, follow_symlinks=False)
            except FileNotFoundError:
                if not create:
                    raise
                os.mkdir(part, 0o700, dir_fd=fd)
                linked = os.stat(part, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISLNK(linked.st_mode) or not stat.S_ISDIR(linked.st_mode):
                raise RuntimeError("secure file ancestry must be real directories")
            child = os.open(part, _dir_flags(), dir_fd=fd)
            visible = os.stat(part, dir_fd=fd, follow_symlinks=False)
            if _identity(linked) != _identity(os.fstat(child)) or _identity(visible) != _identity(os.fstat(child)):
                os.close(child)
                raise RuntimeError("secure file ancestry changed while opening")
            os.close(fd)
            fd = child
        return fd, parts[-1]
    except BaseException:
        os.close(fd)
        raise


@dataclass
class BoundRegularFile:
    path: Path
    parent_fd: int
    name: str
    fd: int
    identity: tuple[int, int]

    @classmethod
    def open(cls, path: Path, *, expected: tuple[int, int] | None = None) -> "BoundRegularFile":
        parent_fd, name = open_parent(path)
        fd: int | None = None
        try:
            linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if stat.S_ISLNK(linked.st_mode) or not stat.S_ISREG(linked.st_mode):
                raise RuntimeError("consistency file must be a regular file")
            fd = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), dir_fd=parent_fd)
            opened = os.fstat(fd)
            visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            identity = _identity(opened)
            if _identity(linked) != identity or _identity(visible) != identity or (expected is not None and expected != identity):
                raise RuntimeError("consistency file identity changed or mismatched")
            return cls(Path(os.path.abspath(path)), parent_fd, name, fd, identity)
        except BaseException:
            if fd is not None:
                os.close(fd)
            os.close(parent_fd)
            raise

    def read_bytes(self) -> bytes:
        os.lseek(self.fd, 0, os.SEEK_SET)
        chunks = []
        while True:
            chunk = os.read(self.fd, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)

    def verify_visible(self) -> None:
        visible = os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(visible.st_mode) or not stat.S_ISREG(visible.st_mode) or _identity(visible) != self.identity:
            raise RuntimeError("consistency file identity changed before write")

    def replace_bytes(self, content: bytes) -> None:
        self.verify_visible()
        private = f".{self.name}.consistency.{secrets.token_hex(16)}"
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        temp_fd = os.open(private, flags, 0o600, dir_fd=self.parent_fd)
        temp_identity = _identity(os.fstat(temp_fd))
        try:
            view = memoryview(content)
            while view:
                written = os.write(temp_fd, view)
                if written <= 0:
                    raise RuntimeError("secure consistency write made no progress")
                view = view[written:]
            os.fsync(temp_fd)
            self.verify_visible()
            _inject("before-exchange")
            _atomic_exchange(self.parent_fd, private, self.name)
            visible = os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False)
            displaced = os.stat(private, dir_fd=self.parent_fd, follow_symlinks=False)
            if _identity(visible) != temp_identity:
                raise RuntimeError("secure consistency replacement identity changed")
            if _identity(displaced) != self.identity:
                foreign_identity = _identity(displaced)
                _inject("before-rollback-exchange")
                current_public = os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False)
                current_private = os.stat(private, dir_fd=self.parent_fd, follow_symlinks=False)
                if _identity(current_public) != temp_identity or _identity(current_private) != foreign_identity:
                    raise RuntimeError("secure consistency rollback boundary changed")
                _atomic_exchange(self.parent_fd, private, self.name)
                restored = os.stat(self.name, dir_fd=self.parent_fd, follow_symlinks=False)
                owned = os.stat(private, dir_fd=self.parent_fd, follow_symlinks=False)
                if _identity(restored) != foreign_identity or _identity(owned) != temp_identity:
                    raise RuntimeError("secure consistency rollback was not stable")
                raise RuntimeError("consistency file identity changed during publication")
            if not _unlink_owned(self.parent_fd, private, self.identity):
                raise RuntimeError("displaced consistency file changed before cleanup")
            private = ""
            os.fsync(self.parent_fd)
        finally:
            os.close(temp_fd)
            if private and temp_identity is not None:
                _unlink_owned(self.parent_fd, private, temp_identity)

    def close(self) -> None:
        if self.fd >= 0:
            os.close(self.fd)
            self.fd = -1
        if self.parent_fd >= 0:
            os.close(self.parent_fd)
            self.parent_fd = -1

    def __del__(self) -> None:
        self.close()


def read_regular(path: Path, *, expected: tuple[int, int] | None = None) -> tuple[bytes, tuple[int, int]]:
    bound = BoundRegularFile.open(path, expected=expected)
    try:
        return bound.read_bytes(), bound.identity
    finally:
        bound.close()


def atomic_write_new_or_replace(path: Path, content: bytes) -> None:
    try:
        bound = BoundRegularFile.open(path)
    except FileNotFoundError:
        parent_fd, name = open_parent(path, create=True)
        try:
            private = f".{name}.consistency.{secrets.token_hex(16)}"
            fd = os.open(private, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent_fd)
            private_identity = _identity(os.fstat(fd))
            try:
                view = memoryview(content)
                while view:
                    written = os.write(fd, view)
                    if written <= 0:
                        raise RuntimeError("secure consistency write made no progress")
                    view = view[written:]
                os.fsync(fd)
            finally:
                os.close(fd)
            try:
                _inject("before-noreplace")
                _atomic_noreplace(parent_fd, private, name)
                private = ""
                visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if _identity(visible) != private_identity:
                    raise RuntimeError("secure destination identity changed during publication")
                os.fsync(parent_fd)
            except FileExistsError as exc:
                raise RuntimeError("secure destination appeared during publication") from exc
            finally:
                if private and private_identity is not None and not _unlink_owned(parent_fd, private, private_identity):
                    raise RuntimeError("secure private cleanup identity changed")
        finally:
            os.close(parent_fd)
    else:
        try:
            bound.replace_bytes(content)
        finally:
            bound.close()


def unlink_regular(path: Path, expected: tuple[int, int]) -> None:
    parent_fd, name = open_parent(path)
    try:
        visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(visible.st_mode) or not stat.S_ISREG(visible.st_mode) or _identity(visible) != expected:
            raise RuntimeError("secure cleanup identity changed")
        os.unlink(name, dir_fd=parent_fd)
        os.fsync(parent_fd)
    finally:
        os.close(parent_fd)


def create_bound_empty(path: Path) -> tuple[int, int]:
    parent_fd, name = open_parent(path, create=True)
    fd: int | None = None
    identity: tuple[int, int] | None = None
    complete = False
    try:
        flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        fd = os.open(name, flags, 0o600, dir_fd=parent_fd)
        identity = _identity(os.fstat(fd))
        visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if _identity(visible) != identity or not stat.S_ISREG(visible.st_mode):
            raise RuntimeError("bound private file identity changed during creation")
        os.fsync(fd)
        os.fsync(parent_fd)
        complete = True
        return identity
    finally:
        if fd is not None:
            os.close(fd)
        if not complete and identity is not None:
            _unlink_owned(parent_fd, name, identity)
        os.close(parent_fd)


def write_bound_bytes(path: Path, expected: tuple[int, int], content: bytes) -> None:
    parent_fd, name = open_parent(path)
    fd: int | None = None
    try:
        linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if stat.S_ISLNK(linked.st_mode) or not stat.S_ISREG(linked.st_mode) or _identity(linked) != expected:
            raise RuntimeError("bound private destination identity changed")
        fd = os.open(name, os.O_WRONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0), dir_fd=parent_fd)
        if _identity(os.fstat(fd)) != expected:
            raise RuntimeError("bound private destination identity changed while opening")
        os.ftruncate(fd, 0)
        view = memoryview(content)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise RuntimeError("bound private write made no progress")
            view = view[written:]
        os.fsync(fd)
        visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        if _identity(visible) != expected or not stat.S_ISREG(visible.st_mode):
            raise RuntimeError("bound private destination changed during write")
        os.fsync(parent_fd)
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent_fd)
