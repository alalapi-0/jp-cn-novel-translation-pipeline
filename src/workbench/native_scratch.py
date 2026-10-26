"""Opaque cleanup for one newly created private native scratch directory.

Keep this capability in the creating controller. It cannot adopt an existing
directory, follow links, inspect file contents, or authorize stopping a writer.
"""
import os
import math
from pathlib import Path
import stat
import time


class ScratchRefused(RuntimeError):
    pass


def _pin(info):
    return info.st_dev, info.st_ino, info.st_uid, stat.S_IMODE(info.st_mode)


class OwnedScratch:
    def __init__(self, path):
        self.path = Path(path).absolute()
        self._parent = self._root = None
        self._used = False
        self.removed = False
        flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC
        try:
            self._parent = os.open(self.path.parent, flags)
            self._parent_pin = _pin(os.fstat(self._parent))
            os.mkdir(self.path.name, mode=0o700, dir_fd=self._parent)
            self._root = os.open(self.path.name, flags, dir_fd=self._parent)
            self._root_pin = _pin(os.fstat(self._root))
            if self._root_pin[2:] != (os.geteuid(), 0o700):
                raise ScratchRefused('private_scratch_ownership_required')
        except BaseException:
            self.abandon()
            raise

    def abandon(self):
        for key in ('_root', '_parent'):
            descriptor = getattr(self, key, None)
            if descriptor is not None:
                os.close(descriptor)
                setattr(self, key, None)

    def cleanup(self, deadline, *, writers_closed, max_entries=256, max_depth=8, now=None):
        now = now or time.monotonic
        if self._used or self._parent is None or self._root is None:
            raise ScratchRefused('new_owned_scratch_required')
        self._used = True
        count = 0

        def before():
            if now() >= deadline:
                raise TimeoutError('scratch_cleanup_deadline')

        def binding():
            before()
            parent = os.stat(self.path.parent, follow_symlinks=False)
            root = os.stat(self.path.name, dir_fd=self._parent, follow_symlinks=False)
            if (not stat.S_ISDIR(parent.st_mode) or not stat.S_ISDIR(root.st_mode)
                    or _pin(parent) != self._parent_pin or _pin(root) != self._root_pin):
                raise ScratchRefused('scratch_identity_changed')

        def drain(descriptor, depth):
            nonlocal count
            before()
            if depth > max_depth:
                raise ScratchRefused('scratch_depth_limit')
            with os.scandir(descriptor) as entries:
                for entry in entries:
                    before()
                    count += 1
                    if count > max_entries:
                        raise ScratchRefused('scratch_entry_limit')
                    info = os.stat(entry.name, dir_fd=descriptor, follow_symlinks=False)
                    if stat.S_ISLNK(info.st_mode):
                        raise ScratchRefused('scratch_symlink_refused')
                    before()
                    if stat.S_ISDIR(info.st_mode):
                        child = os.open(entry.name, os.O_RDONLY | os.O_DIRECTORY |
                                        os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=descriptor)
                        try:
                            if _pin(os.fstat(child)) != _pin(info):
                                raise ScratchRefused('scratch_child_identity_changed')
                            drain(child, depth + 1)
                        finally:
                            os.close(child)
                        before()
                        if _pin(os.stat(entry.name, dir_fd=descriptor, follow_symlinks=False)) != _pin(info):
                            raise ScratchRefused('scratch_child_identity_changed')
                        os.rmdir(entry.name, dir_fd=descriptor)
                    else:
                        if _pin(os.stat(entry.name, dir_fd=descriptor, follow_symlinks=False)) != _pin(info):
                            raise ScratchRefused('scratch_child_identity_changed')
                        before()
                        os.unlink(entry.name, dir_fd=descriptor)

        try:
            if writers_closed is not True:
                raise ScratchRefused('exact_writers_must_be_closed')
            if (type(deadline) not in (int, float) or not math.isfinite(deadline)
                    or type(max_entries) is not int or max_entries < 0
                    or type(max_depth) is not int or max_depth < 0):
                raise ScratchRefused('finite_scratch_limits_required')
            binding()
            drain(self._root, 0)
            binding()
            before()
            os.rmdir(self.path.name, dir_fd=self._parent)
            before()
            self.removed = True
            return True
        finally:
            self.abandon()
