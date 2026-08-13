#!/usr/bin/env python3
"""Export the consistency-audited canonical translation.

The default export is intentionally a singleton final handoff: one Chinese
full-volume file plus a manifest. Per-chapter and bilingual files are useful
working artifacts, but they create extra "final" copies that can mislead later
agents. Recreate them only with explicit flags.
"""

from __future__ import annotations

import argparse
import ctypes
import errno
import fnmatch
import hashlib
import json
import os
import re
import secrets
import stat
import sys
from datetime import datetime, timezone
from pathlib import Path

from run_consistency_fix_all import (
    canonical_chapter_number,
    discover_active_chapter_numbers,
    discover_canonical_files,
)
from consistency_transaction_lock import exclusive_consistency_lock
from secure_consistency_files import read_regular

REPO_ROOT = Path(__file__).resolve().parent.parent
EXCLUDED_SEGMENT_STATUSES = {"validation_failed", "failed", "retry_pending"}
TOP_LEVEL_HEADING_RE = re.compile(rb"(?m)^# .*(?:\r?\n|$)")
CHAPTER_HEADING_RE = re.compile(rb"(?m)^# (?P<number>\d+)(?=[ \t\r\n]|$).*(?:\r?\n|$)")
_UNSET = object()
TRANSACTION_PREFIX = ".consistency-export-txn."
PREPARATION_PREFIX = ".consistency-export-prep."


def _inject(_boundary: str) -> None:
    """Deterministic synthetic fault boundary; production is a no-op."""


def _fsync_directory(directory_fd: int) -> None:
    try:
        os.fsync(directory_fd)
    except OSError as exc:
        raise RuntimeError("export directory durability cannot be established") from exc


def _chapter_num(chapter_id: str) -> int:
    return canonical_chapter_number(chapter_id)


def _same_file_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _output_path_parts(path: Path) -> tuple[Path, tuple[str, ...]]:
    root = Path(os.path.abspath(REPO_ROOT))
    candidate = Path(os.path.abspath(path))
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise RuntimeError("output path escapes repository root") from exc
    return candidate, relative.parts


def _directory_open_flags() -> int:
    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise RuntimeError("safe descriptor-anchored output is unsupported")
    return os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)


def _open_repo_root_fd() -> int:
    root = Path(os.path.abspath(REPO_ROOT))
    try:
        before = root.lstat()
    except OSError as exc:
        raise RuntimeError("repository root cannot be inspected safely") from exc
    if stat.S_ISLNK(before.st_mode) or not stat.S_ISDIR(before.st_mode):
        raise RuntimeError("repository root must be a real directory")
    try:
        root_fd = os.open(root, _directory_open_flags())
    except OSError as exc:
        raise RuntimeError("repository root cannot be opened safely") from exc
    try:
        opened = os.fstat(root_fd)
        after = root.lstat()
        if (
            not stat.S_ISDIR(opened.st_mode)
            or stat.S_ISLNK(after.st_mode)
            or not _same_file_identity(before, opened)
            or not _same_file_identity(opened, after)
        ):
            raise RuntimeError("repository root changed while being opened")
    except BaseException:
        os.close(root_fd)
        raise
    return root_fd


def _open_child_directory(parent_fd: int, name: str, *, create: bool) -> int:
    for _attempt in range(2):
        try:
            linked = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        except FileNotFoundError:
            if not create:
                raise
            try:
                os.mkdir(name, mode=0o755, dir_fd=parent_fd)
            except FileExistsError:
                continue
            except OSError as exc:
                raise RuntimeError("output directory component cannot be created safely") from exc
            continue
        except OSError as exc:
            raise RuntimeError("output directory component cannot be inspected safely") from exc
        if stat.S_ISLNK(linked.st_mode):
            raise RuntimeError("output path component must not be a symlink")
        if not stat.S_ISDIR(linked.st_mode):
            raise RuntimeError("output path component is not a directory")
        try:
            child_fd = os.open(name, _directory_open_flags(), dir_fd=parent_fd)
        except OSError as exc:
            raise RuntimeError(
                "output path component must not be a symlink or non-directory"
            ) from exc
        try:
            opened = os.fstat(child_fd)
            visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if (
                not stat.S_ISDIR(opened.st_mode)
                or stat.S_ISLNK(visible.st_mode)
                or not _same_file_identity(linked, opened)
                or not _same_file_identity(opened, visible)
            ):
                raise RuntimeError("output directory component changed while being opened")
        except BaseException:
            os.close(child_fd)
            raise
        return child_fd
    raise RuntimeError("output directory component changed while being created")


def _renameat_with_flags(
    parent_fd: int,
    source: str,
    destination: str,
    *,
    flag: int,
) -> None:
    _renameat_with_flags_between(
        parent_fd, source, parent_fd, destination, flag=flag
    )


def _renameat_with_flags_between(
    source_fd: int,
    source: str,
    destination_fd: int,
    destination: str,
    *,
    flag: int,
) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    source_bytes = os.fsencode(source)
    destination_bytes = os.fsencode(destination)
    if sys.platform == "darwin":
        rename = getattr(libc, "renameatx_np", None)
    else:
        rename = getattr(libc, "renameat2", None)
    if rename is None:
        raise RuntimeError("safe atomic output publication is unsupported")
    rename.argtypes = [ctypes.c_int, ctypes.c_char_p, ctypes.c_int, ctypes.c_char_p, ctypes.c_uint]
    rename.restype = ctypes.c_int
    if rename(source_fd, source_bytes, destination_fd, destination_bytes, flag) == 0:
        return
    error = ctypes.get_errno()
    if error in {errno.EEXIST, errno.ENOTEMPTY}:
        raise FileExistsError(error, os.strerror(error), destination)
    raise OSError(error, os.strerror(error), destination)


def _rename_entry_noreplace(parent_fd: int, source: str, destination: str) -> None:
    """Publish a bound private entry without replacing a visible entry."""

    flag = 0x00000004 if sys.platform == "darwin" else 0x00000001
    _renameat_with_flags(parent_fd, source, destination, flag=flag)


def _rename_entry_noreplace_between(
    source_fd: int, source: str, destination_fd: int, destination: str
) -> None:
    flag = 0x00000004 if sys.platform == "darwin" else 0x00000001
    _renameat_with_flags_between(
        source_fd, source, destination_fd, destination, flag=flag
    )


def _rename_directory_noreplace(parent_fd: int, source: str, destination: str) -> None:
    """Publish a bound private directory without replacing a visible entry."""

    _rename_entry_noreplace(parent_fd, source, destination)


def _create_and_bind_child_directory(parent_fd: int, name: str) -> int:
    """Create privately, bind its inode, then publish it atomically by name."""

    for _attempt in range(128):
        private_name = f".consistency-export-dir.{os.getpid()}.{secrets.token_hex(16)}"
        try:
            os.mkdir(private_name, mode=0o700, dir_fd=parent_fd)
        except FileExistsError:
            continue
        except OSError as exc:
            raise RuntimeError("private output directory cannot be created safely") from exc

        child_fd: int | None = None
        published = False
        try:
            child_fd = _open_child_directory(parent_fd, private_name, create=False)
            created = os.fstat(child_fd)
            try:
                _rename_directory_noreplace(parent_fd, private_name, name)
            except FileExistsError as exc:
                raise RuntimeError("missing output directory appeared after preflight") from exc
            except OSError as exc:
                raise RuntimeError("output directory cannot be published safely") from exc
            published = True
            try:
                visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            except OSError as exc:
                raise RuntimeError("created output directory disappeared during publication") from exc
            if (
                stat.S_ISLNK(visible.st_mode)
                or not stat.S_ISDIR(visible.st_mode)
                or not _same_file_identity(created, visible)
            ):
                raise RuntimeError("created output directory identity changed during publication")
            os.fchmod(child_fd, 0o755)
            visible = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
            if not _same_file_identity(os.fstat(child_fd), visible):
                raise RuntimeError("created output directory identity changed during publication")
            return child_fd
        except BaseException:
            if child_fd is not None:
                os.close(child_fd)
            if not published:
                try:
                    os.rmdir(private_name, dir_fd=parent_fd)
                except OSError:
                    pass
            raise
    raise RuntimeError("private output directory name could not be allocated")


def _open_output_directory_fd(path: Path, *, create: bool) -> int | None:
    _candidate, parts = _output_path_parts(path)
    current_fd = _open_repo_root_fd()
    try:
        for part in parts:
            try:
                child_fd = _open_child_directory(current_fd, part, create=create)
            except FileNotFoundError:
                os.close(current_fd)
                return None
            os.close(current_fd)
            current_fd = child_fd
        return current_fd
    except BaseException:
        os.close(current_fd)
        raise


def _regular_output_entry(
    directory_fd: int,
    name: str,
    *,
    context: str,
) -> os.stat_result | None:
    try:
        entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    except FileNotFoundError:
        return None
    except OSError as exc:
        raise RuntimeError(f"{context} cannot be inspected safely") from exc
    if stat.S_ISLNK(entry.st_mode):
        raise RuntimeError(f"{context} must not be a symlink")
    if not stat.S_ISREG(entry.st_mode):
        raise RuntimeError(f"{context} is not a regular file")
    return entry


def _read_output_file(
    path: Path,
    *,
    directory_fd: int | None | object = _UNSET,
) -> bytes | None:
    candidate, parts = _output_path_parts(path)
    if not parts:
        raise RuntimeError("output file path names the repository root")
    if directory_fd is _UNSET:
        opened_directory_fd = _open_output_directory_fd(candidate.parent, create=False)
    elif directory_fd is None:
        return None
    else:
        opened_directory_fd = os.dup(directory_fd)
    if opened_directory_fd is None:
        return None
    file_fd: int | None = None
    try:
        linked = _regular_output_entry(opened_directory_fd, candidate.name, context="output destination")
        if linked is None:
            return None
        flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
        try:
            file_fd = os.open(candidate.name, flags, dir_fd=opened_directory_fd)
        except OSError as exc:
            raise RuntimeError("output destination cannot be opened safely") from exc
        opened = os.fstat(file_fd)
        visible = _regular_output_entry(
            opened_directory_fd, candidate.name, context="output destination"
        )
        if visible is None or not _same_file_identity(linked, opened) or not _same_file_identity(opened, visible):
            raise RuntimeError("output destination changed while being opened")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(file_fd, 1024 * 1024)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)
    finally:
        if file_fd is not None:
            os.close(file_fd)
        os.close(opened_directory_fd)


def _entry_identity(entry: os.stat_result | None) -> tuple[int, int] | None:
    return None if entry is None else (entry.st_dev, entry.st_ino)


def _assert_output_entry_identity(
    directory_fd: int,
    name: str,
    expected: tuple[int, int] | None,
    *,
    context: str,
) -> os.stat_result | None:
    current = _regular_output_entry(directory_fd, name, context=context)
    if _entry_identity(current) != expected:
        raise RuntimeError(f"{context} identity changed after preflight")
    return current


def _validate_output_path(path: Path, *, directory: bool) -> Path:
    """Reject output paths that escape the repo or traverse ambiguous nodes."""

    candidate, parts = _output_path_parts(path)

    current = Path(os.path.abspath(REPO_ROOT))
    for index, part in enumerate(parts):
        current /= part
        try:
            mode = current.lstat().st_mode
        except FileNotFoundError:
            break
        except OSError as exc:
            raise RuntimeError("output path cannot be inspected safely") from exc
        if stat.S_ISLNK(mode):
            raise RuntimeError("output path component must not be a symlink")
        is_destination = index == len(parts) - 1
        if not is_destination and not stat.S_ISDIR(mode):
            raise RuntimeError("output path component is not a directory")
        if is_destination:
            expected = stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode)
            if not expected:
                kind = "directory" if directory else "regular file"
                raise RuntimeError(f"output destination is not a {kind}")
    return candidate


def _cn_text(seg: dict) -> str:
    return ((seg.get("refined_text") or "").strip() or (seg.get("draft_text") or "").strip())


def _segment_exportable(seg: dict) -> bool:
    statuses = {
        str(seg.get(field) or "").strip().lower()
        for field in ("status", "refine_status")
    }
    if statuses & EXCLUDED_SEGMENT_STATUSES:
        return False
    return bool(_cn_text(seg))


def _load_canonical_chapters(active_numbers: set[int]) -> tuple[dict[int, dict], list[dict]]:
    chapters: dict[int, dict] = {}
    sources: list[dict] = []
    for path in sorted(discover_canonical_files(), key=lambda item: str(item)):
        try:
            content, identity = read_regular(path)
            doc = json.loads(content.decode("utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"invalid canonical segments file: {path.name}") from exc
        rel = str(path.relative_to(REPO_ROOT))
        visible = os.stat(path, follow_symlinks=False)
        if _entry_identity(visible) != identity:
            raise RuntimeError(f"canonical segments identity changed: {path.name}")
        mtime = visible.st_mtime
        chapter_ids: list[int] = []
        raw_chapters = doc.get("chapters") if isinstance(doc, dict) else None
        if not isinstance(raw_chapters, list):
            raise RuntimeError(f"canonical chapters must be a list: {path.name}")
        seen_in_file: set[int] = set()
        for ch in raw_chapters:
            try:
                number = canonical_chapter_number(ch.get("chapter_id") if isinstance(ch, dict) else None)
            except ValueError as exc:
                raise RuntimeError(f"malformed canonical chapter ID in {path.name}") from exc
            if number in seen_in_file:
                raise RuntimeError(f"duplicate normalized canonical chapter ID {number} in {path.name}")
            seen_in_file.add(number)
            if number not in active_numbers:
                continue
            if number in chapters:
                raise RuntimeError(f"ambiguous active canonical chapter ID {number}")
            chapter_ids.append(number)
            chapters[number] = {
                "_segments_file": rel,
                "chapter_id": f"ch-{number:03d}",
                "chapter_label": ch.get("chapter_label") or f"ch-{number:03d}",
                "source_path": ch.get("source_path") or "",
                "segments": ch.get("segments", []),
            }
        if chapter_ids:
            sources.append(
                {
                    "segments_file": rel,
                    "chapters": [f"ch-{number:03d}" for number in sorted(chapter_ids)],
                    "mtime": datetime.fromtimestamp(mtime, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                }
            )
    return chapters, sources


def _generated_output_snapshot(
    directory_fd: int,
    patterns: tuple[str, ...],
) -> dict[str, tuple[int, int]]:
    try:
        names = sorted(os.listdir(directory_fd))
    except OSError as exc:
        raise RuntimeError("generated output directory cannot be enumerated safely") from exc
    generated: dict[str, tuple[int, int]] = {}
    for name in names:
        if name == ".gitkeep" or not any(fnmatch.fnmatchcase(name, pattern) for pattern in patterns):
            continue
        entry = _regular_output_entry(directory_fd, name, context="generated output")
        if entry is None:
            raise RuntimeError("generated output disappeared during enumeration")
        generated[name] = (entry.st_dev, entry.st_ino)
    return generated


def _cleanup_generated(
    out_dir: Path,
    patterns: tuple[str, ...],
    *,
    directory_fd: int | object = _UNSET,
    expected_entries: dict[str, tuple[int, int]] | object = _UNSET,
) -> int:
    if directory_fd is _UNSET:
        opened_directory_fd = _open_output_directory_fd(out_dir, create=True)
    else:
        opened_directory_fd = os.dup(directory_fd)
    if opened_directory_fd is None:
        raise RuntimeError("generated output directory could not be created safely")
    try:
        current_entries = _generated_output_snapshot(opened_directory_fd, patterns)
        if expected_entries is not _UNSET and current_entries != expected_entries:
            raise RuntimeError("generated output identities changed after preflight")
        for name, expected in current_entries.items():
            _assert_output_entry_identity(
                opened_directory_fd,
                name,
                expected,
                context="generated output",
            )
            file_fd: int | None = None
            try:
                file_fd = os.open(
                    name,
                    os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=opened_directory_fd,
                )
                opened = os.fstat(file_fd)
                if (opened.st_dev, opened.st_ino) != expected:
                    raise RuntimeError("generated output identity changed before cleanup")
                _assert_output_entry_identity(
                    opened_directory_fd,
                    name,
                    expected,
                    context="generated output",
                )
            except OSError as exc:
                raise RuntimeError("generated output cannot be opened safely for cleanup") from exc
            finally:
                if file_fd is not None:
                    os.close(file_fd)
            try:
                os.unlink(name, dir_fd=opened_directory_fd)
            except OSError as exc:
                raise RuntimeError("generated output could not be removed safely") from exc
        return len(current_entries)
    finally:
        os.close(opened_directory_fd)


def _cleanup_snapshot(
    out_dir: Path,
    patterns: tuple[str, ...],
    *,
    directory_fd: int | None | object = _UNSET,
) -> dict[str, tuple[int, int]]:
    if directory_fd is _UNSET:
        opened_directory_fd = _open_output_directory_fd(out_dir, create=False)
    elif directory_fd is None:
        return {}
    else:
        opened_directory_fd = os.dup(directory_fd)
    if opened_directory_fd is None:
        return {}
    try:
        return _generated_output_snapshot(opened_directory_fd, patterns)
    finally:
        os.close(opened_directory_fd)


def _cleanup_count(out_dir: Path, patterns: tuple[str, ...]) -> int:
    return len(_cleanup_snapshot(out_dir, patterns))


def _assert_cleanup_snapshot(
    out_dir: Path,
    patterns: tuple[str, ...],
    expected: dict[str, tuple[int, int]],
    *,
    directory_fd: int | None,
) -> None:
    current = _cleanup_snapshot(out_dir, patterns, directory_fd=directory_fd)
    if current != expected:
        raise RuntimeError("generated output identities changed after preflight")


def _filter_singleton_content(content: bytes, active_numbers: set[int], *, context: str) -> bytes:
    """Apply strict singleton readback invariants and retain exact active bytes."""

    try:
        content.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"{context} is not strict UTF-8") from exc
    headings = list(CHAPTER_HEADING_RE.finditer(content))
    all_top_level = list(TOP_LEVEL_HEADING_RE.finditer(content))
    if not headings or len(headings) != len(all_top_level):
        raise RuntimeError(f"{context} has malformed top-level headings")
    if headings[0].start() != 0:
        raise RuntimeError(f"{context} has a preamble")

    blocks: dict[int, bytes] = {}
    previous = 0
    for index, heading in enumerate(headings):
        number = int(heading.group("number"))
        if number <= 0:
            raise RuntimeError(f"{context} has a nonpositive chapter ID")
        if number in blocks:
            raise RuntimeError(f"{context} has duplicate normalized chapter ID {number}")
        if number <= previous:
            raise RuntimeError(f"{context} chapter IDs are not strictly increasing")
        previous = number
        end = headings[index + 1].start() if index + 1 < len(headings) else len(content)
        blocks[number] = content[heading.start():end]

    missing = sorted(active_numbers - blocks.keys())
    if missing:
        raise RuntimeError(f"{context} is missing active chapters")
    return b"".join(blocks[number] for number in sorted(active_numbers))


def _filter_existing_singleton(
    path: Path,
    active_numbers: set[int],
    *,
    directory_fd: int | None | object = _UNSET,
) -> bytes | None:
    """Validate and filter an existing singleton without changing retained bytes."""

    content = _read_output_file(path, directory_fd=directory_fd)
    if content is None:
        return None
    return _filter_singleton_content(
        content, active_numbers, context="existing singleton"
    )


class _OutputDirectoryHandles:
    """Keep no-follow directory handles stable from preflight through commit."""

    def __init__(self, paths: tuple[Path, ...]):
        self.paths: tuple[Path, ...] = tuple(_output_path_parts(path)[0] for path in paths)
        self.parts: dict[Path, tuple[str, ...]] = {
            path: _output_path_parts(path)[1] for path in self.paths
        }
        self._fds: dict[tuple[str, ...], int] = {(): _open_repo_root_fd()}
        self._closed = False
        try:
            for parts in sorted(set(self.parts.values()), key=lambda item: (len(item), item)):
                self._capture_existing(parts)
        except BaseException:
            self.close()
            raise

    def _capture_existing(self, parts: tuple[str, ...]) -> None:
        for index, name in enumerate(parts):
            prefix = parts[: index + 1]
            if prefix in self._fds:
                continue
            parent_fd = self._fds.get(prefix[:-1])
            if parent_fd is None:
                return
            try:
                child_fd = _open_child_directory(parent_fd, name, create=False)
            except FileNotFoundError:
                return
            self._fds[prefix] = child_fd

    def fd_for(self, path: Path) -> int | None:
        candidate, parts = _output_path_parts(path)
        if candidate not in self.parts:
            raise RuntimeError("output directory is outside the frozen handle set")
        return self._fds.get(parts)

    def _verify_repo_root(self) -> None:
        root = Path(os.path.abspath(REPO_ROOT))
        try:
            visible = root.lstat()
        except OSError as exc:
            raise RuntimeError("repository root disappeared during export") from exc
        opened = os.fstat(self._fds[()])
        if (
            stat.S_ISLNK(visible.st_mode)
            or not stat.S_ISDIR(visible.st_mode)
            or not _same_file_identity(opened, visible)
        ):
            raise RuntimeError("repository root identity changed during export")

    def verify_visible(self) -> None:
        self._verify_repo_root()
        for prefix, child_fd in sorted(self._fds.items(), key=lambda item: (len(item[0]), item[0])):
            if not prefix:
                continue
            parent_fd = self._fds[prefix[:-1]]
            try:
                visible = os.stat(prefix[-1], dir_fd=parent_fd, follow_symlinks=False)
            except OSError as exc:
                raise RuntimeError("output directory disappeared during export") from exc
            opened = os.fstat(child_fd)
            if stat.S_ISLNK(visible.st_mode):
                raise RuntimeError("output path component must not be a symlink")
            if not stat.S_ISDIR(visible.st_mode) or not _same_file_identity(opened, visible):
                raise RuntimeError("output directory identity changed during export")

    def begin_mutation(self) -> None:
        """Revalidate the frozen preflight view, then create only absent paths."""

        self.verify_visible()
        for parts in self.parts.values():
            for index, name in enumerate(parts):
                prefix = parts[: index + 1]
                if prefix in self._fds:
                    continue
                parent_fd = self._fds.get(prefix[:-1])
                if parent_fd is None:
                    break
                try:
                    os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                except FileNotFoundError:
                    continue
                except OSError as exc:
                    raise RuntimeError("missing output component cannot be checked safely") from exc
                raise RuntimeError("missing output directory appeared after preflight")

        for parts in sorted(set(self.parts.values()), key=lambda item: (len(item), item)):
            for index, name in enumerate(parts):
                prefix = parts[: index + 1]
                if prefix in self._fds:
                    continue
                parent_fd = self._fds[prefix[:-1]]
                child_fd = _create_and_bind_child_directory(parent_fd, name)
                self._fds[prefix] = child_fd
        self.verify_visible()

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for _prefix, directory_fd in sorted(
            self._fds.items(), key=lambda item: len(item[0]), reverse=True
        ):
            os.close(directory_fd)


def _prepare_output_directories(paths: tuple[Path, ...]) -> _OutputDirectoryHandles:
    """Capture existing output handles read-only; creation waits for mutation."""

    return _OutputDirectoryHandles(paths)


def _verify_committed_file(
    path: Path,
    expected: bytes,
    *,
    directory_fd: int | object = _UNSET,
) -> None:
    content = _read_output_file(path, directory_fd=directory_fd)
    if content is None or content != expected:
        raise RuntimeError("committed output failed descriptor-anchored readback")


def _validate_manifest_bytes(content: bytes, expected: dict, active_numbers: set[int]) -> None:
    """Read back the prospective manifest and enforce its export invariants."""

    try:
        decoded = content.decode("utf-8", errors="strict")
        parsed = json.loads(decoded)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("prospective manifest is not strict UTF-8 JSON") from exc
    if parsed != expected or not isinstance(parsed, dict):
        raise RuntimeError("prospective manifest does not round-trip exactly")
    count = len(active_numbers)
    if (
        parsed.get("schema") != "consistency_final_export_v2"
        or parsed.get("chapters_discovered") != count
        or parsed.get("chapters_exported") != count
        or parsed.get("chapters_missing") != []
        or parsed.get("chapters_incomplete") != []
        or parsed.get("canonical_final_translation_count") != 1
        or parsed.get("full_volume_cn") != parsed.get("canonical_final_translation")
    ):
        raise RuntimeError("prospective manifest violates final export invariants")


def _render_cn(ch: dict) -> str:
    number = _chapter_num(ch["chapter_id"])
    label = str(ch.get("chapter_label") or "").strip()
    lines = [f"# {number}" + (f" {label}" if label else ""), ""]
    for seg in ch["segments"]:
        text = _cn_text(seg)
        if text:
            lines.append(text)
            lines.append("")
    return "\n".join(lines).strip() + "\n"


def _render_bilingual(ch: dict) -> str:
    lines = [f"# {ch['chapter_label']}", ""]
    for idx, seg in enumerate(ch["segments"], start=1):
        src = (seg.get("source_text") or "").strip()
        cn = _cn_text(seg)
        if not src and not cn:
            continue
        lines.extend(
            [
                f"## 段落 {idx}",
                "**原文：**",
                src,
                "",
                "**译文：**",
                cn,
                "",
                "---",
                "",
            ]
        )
    return "\n".join(lines).strip() + "\n"


def _read_fd_bytes(directory_fd: int, name: str) -> bytes:
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        fd = os.open(name, flags, dir_fd=directory_fd)
    except OSError as exc:
        raise RuntimeError("private transaction entry cannot be opened safely") from exc
    try:
        opened = os.fstat(fd)
        visible = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_ISLNK(visible.st_mode)
            or not _same_file_identity(opened, visible)
        ):
            raise RuntimeError("private transaction entry identity is ambiguous")
        chunks: list[bytes] = []
        while True:
            chunk = os.read(fd, 1024 * 1024)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)
    finally:
        os.close(fd)


def _write_private_bytes(directory_fd: int, name: str, content: bytes) -> tuple[int, int]:
    flags = (
        os.O_WRONLY
        | os.O_CREAT
        | os.O_EXCL
        | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        fd = os.open(name, flags, 0o600, dir_fd=directory_fd)
    except OSError as exc:
        raise RuntimeError("private transaction entry cannot be created safely") from exc
    try:
        view = memoryview(content)
        while view:
            written = os.write(fd, view)
            if written <= 0:
                raise RuntimeError("private transaction write made no progress")
            view = view[written:]
        os.fsync(fd)
        entry = os.fstat(fd)
        return (entry.st_dev, entry.st_ino)
    finally:
        os.close(fd)


class _ExportTransaction:
    """Crash-recoverable quarantine for one locked public export update."""

    def __init__(
        self,
        output_fd: int,
        area_fds: dict[str, int],
        originals: dict[str, dict[str, tuple[int, int]]],
        planned: dict[str, dict[str, bytes]],
    ):
        self.output_fd = output_fd
        self.area_fds = area_fds
        self.name = f"{TRANSACTION_PREFIX}{secrets.token_hex(16)}"
        prep_name = f"{PREPARATION_PREFIX}{secrets.token_hex(16)}"
        owned: dict[str, tuple[int, int]] = {}
        try:
            os.mkdir(prep_name, 0o700, dir_fd=output_fd)
            self.fd = _open_child_directory(output_fd, prep_name, create=False)
        except OSError as exc:
            raise RuntimeError("private export transaction cannot be created safely") from exc
        try:
            if stat.S_IMODE(os.fstat(self.fd).st_mode) != 0o700:
                raise RuntimeError("private export transaction permissions are insecure")
            _inject("prep-created")
            planned_items = []
            ordered_areas = [area for area in ("translated", "bilingual", "root") if area in planned]
            for index, (area, name, content) in enumerate(
                (a, n, c)
                for a in ordered_areas
                for n, c in sorted(planned[a].items())
            ):
                private_name = f"plan-{index:04d}"
                identity = _write_private_bytes(self.fd, private_name, content)
                owned[private_name] = identity
                planned_items.append(
                    {
                        "area": area,
                        "name": name,
                        "private": private_name,
                        "dev": identity[0],
                        "ino": identity[1],
                        "sha256": hashlib.sha256(content).hexdigest(),
                    }
                )
                _inject("prep-plan")
            _fsync_directory(self.fd)
            self.journal = {
            "schema": 1,
            "originals": [
                {
                    "area": area,
                    "name": name,
                    "private": f"old-{index:04d}",
                    "dev": identity[0],
                    "ino": identity[1],
                }
                for index, (area, name, identity) in enumerate(
                    (a, n, i)
                    for a in sorted(originals)
                    for n, i in sorted(originals[a].items())
                )
            ],
            "planned": planned_items,
            }
            journal_bytes = (json.dumps(self.journal, sort_keys=True) + "\n").encode("utf-8")
            self.journal_identity = _write_private_bytes(self.fd, "journal.json", journal_bytes)
            owned["journal.json"] = self.journal_identity
            _inject("prep-journal")
            _fsync_directory(self.fd)
            _inject("prep-ready")
            _rename_directory_noreplace(output_fd, prep_name, self.name)
            prep_name = ""
            _fsync_directory(self.output_fd)
            _inject("plan")
        except BaseException:
            if prep_name:
                for entry_name, expected in owned.items():
                    try:
                        visible = os.stat(entry_name, dir_fd=self.fd, follow_symlinks=False)
                        if _entry_identity(visible) != expected or not stat.S_ISREG(visible.st_mode):
                            raise RuntimeError("private preparation cleanup identity changed")
                        os.unlink(entry_name, dir_fd=self.fd)
                    except FileNotFoundError:
                        pass
                _fsync_directory(self.fd)
                os.close(self.fd)
                os.rmdir(prep_name, dir_fd=output_fd)
                _fsync_directory(output_fd)
            else:
                os.close(self.fd)
            raise

    def quarantine(self) -> None:
        for item in self.journal["originals"]:
            area_fd = self.area_fds[item["area"]]
            expected = (item["dev"], item["ino"])
            _assert_output_entry_identity(
                area_fd, item["name"], expected, context="quarantined output"
            )
            try:
                os.rename(
                    item["name"],
                    item["private"],
                    src_dir_fd=area_fd,
                    dst_dir_fd=self.fd,
                )
            except OSError as exc:
                raise RuntimeError("verified output cannot be quarantined safely") from exc
            moved = os.stat(item["private"], dir_fd=self.fd, follow_symlinks=False)
            if _entry_identity(moved) != expected:
                raise RuntimeError("quarantined output identity changed")
            _fsync_directory(area_fd)
            _fsync_directory(self.fd)
            _inject("quarantine")

    def publish(self) -> None:
        for item in self.journal["planned"]:
            area_fd = self.area_fds[item["area"]]
            expected = (item["dev"], item["ino"])
            private = _regular_output_entry(
                self.fd, item["private"], context="staged output"
            )
            if _entry_identity(private) != expected:
                raise RuntimeError("staged output identity changed before publication")
            try:
                _rename_entry_noreplace_between(
                    self.fd, item["private"], area_fd, item["name"]
                )
            except FileExistsError as exc:
                raise RuntimeError("output destination appeared during publication") from exc
            except OSError as exc:
                raise RuntimeError("staged output cannot be published safely") from exc
            identity, digest = _hash_public_entry(area_fd, item["name"])
            if identity != expected or digest != item["sha256"]:
                raise RuntimeError("published output identity or content changed")
            _fsync_directory(area_fd)
            _fsync_directory(self.fd)
            _inject("publish")

    def mark_committed(self) -> None:
        for item in self.journal["planned"]:
            identity, digest = _hash_public_entry(
                self.area_fds[item["area"]], item["name"]
            )
            if identity != (item["dev"], item["ino"]) or digest != item["sha256"]:
                raise RuntimeError("planned output changed before commit")
        _write_private_bytes(self.fd, "committed", b"committed\n")
        _fsync_directory(self.fd)
        _fsync_directory(self.output_fd)
        _inject("committed")

    def close(self) -> None:
        os.close(self.fd)


def _hash_public_entry(area_fd: int, name: str) -> tuple[tuple[int, int], str]:
    entry = _regular_output_entry(area_fd, name, context="recovery output")
    if entry is None:
        raise FileNotFoundError(name)
    data = _read_fd_bytes(area_fd, name)
    visible = _regular_output_entry(area_fd, name, context="recovery output")
    if visible is None or not _same_file_identity(entry, visible):
        raise RuntimeError("recovery output identity changed while hashing")
    return _entry_identity(entry), hashlib.sha256(data).hexdigest()


def _load_transaction_journal(transaction_fd: int) -> dict:
    try:
        doc = json.loads(_read_fd_bytes(transaction_fd, "journal.json"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError("private export transaction journal is invalid") from exc
    if not isinstance(doc, dict) or set(doc) != {"schema", "originals", "planned"} or doc.get("schema") != 1:
        raise RuntimeError("private export transaction journal schema is invalid")
    if not isinstance(doc.get("originals"), list) or not isinstance(doc.get("planned"), list):
        raise RuntimeError("private export transaction journal shape is invalid")
    allowed_areas = {"root", "translated", "bilingual"}
    public_keys: dict[str, set[tuple[str, str]]] = {"originals": set(), "planned": set()}
    private_names: set[str] = set()
    hex_re = re.compile(r"^[0-9a-f]{64}$")
    for kind in ("originals", "planned"):
        required = {"area", "name", "private", "dev", "ino"}
        if kind == "planned":
            required.add("sha256")
        for item in doc[kind]:
            if not isinstance(item, dict) or set(item) != required:
                raise RuntimeError("private export transaction journal entry is invalid")
            area, name, private = item["area"], item["name"], item["private"]
            if area not in allowed_areas:
                raise RuntimeError("private export transaction area is invalid")
            if (
                not isinstance(name, str)
                or not name
                or Path(name).name != name
                or name in {".", ".."}
                or not isinstance(private, str)
                or not private
                or Path(private).name != private
                or private in {".", "..", "journal.json", "committed"}
            ):
                raise RuntimeError("private export transaction name is invalid")
            if type(item["dev"]) is not int or type(item["ino"]) is not int or item["dev"] < 0 or item["ino"] <= 0:
                raise RuntimeError("private export transaction identity is invalid")
            key = (area, name)
            if key in public_keys[kind] or private in private_names:
                raise RuntimeError("private export transaction entries are duplicated")
            public_keys[kind].add(key)
            private_names.add(private)
            if kind == "planned" and (
                not isinstance(item["sha256"], str) or not hex_re.fullmatch(item["sha256"])
            ):
                raise RuntimeError("private export transaction hash is invalid")
    return doc


def _transaction_committed(transaction_fd: int) -> bool:
    try:
        entry = os.stat("committed", dir_fd=transaction_fd, follow_symlinks=False)
    except FileNotFoundError:
        return False
    if stat.S_ISLNK(entry.st_mode) or not stat.S_ISREG(entry.st_mode):
        raise RuntimeError("private export transaction marker is invalid")
    return _read_fd_bytes(transaction_fd, "committed") == b"committed\n"


def _finish_transaction(
    output_fd: int,
    transaction_name: str,
    transaction_fd: int,
    area_fds: dict[str, int],
    *,
    committed: bool,
) -> None:
    journal = _load_transaction_journal(transaction_fd)
    planned = {(item["area"], item["name"]): item for item in journal["planned"]}
    originals = {(item["area"], item["name"]): item for item in journal["originals"]}

    if committed:
        for (area, name), item in planned.items():
            try:
                identity, actual_hash = _hash_public_entry(area_fds[area], name)
            except FileNotFoundError as exc:
                raise RuntimeError("committed export is incomplete during recovery") from exc
            if identity != (item["dev"], item["ino"]) or actual_hash != item["sha256"]:
                raise RuntimeError("committed export changed before cleanup")
    else:
        for (area, name), item in planned.items():
            area_fd = area_fds[area]
            expected = (item["dev"], item["ino"])
            private = _regular_output_entry(transaction_fd, item["private"], context="staged output")
            public = _regular_output_entry(area_fd, name, context="recovery output")
            if _entry_identity(private) == expected:
                original = originals.get((area, name))
                original_identity = None if original is None else (original["dev"], original["ino"])
                if public is not None and _entry_identity(public) != original_identity:
                    raise RuntimeError("recovery refuses to move a foreign public entry")
                continue
            if private is not None or _entry_identity(public) != expected:
                raise RuntimeError("planned output recovery identity is ambiguous")
            identity, digest = _hash_public_entry(area_fd, name)
            if identity != expected or digest != item["sha256"]:
                raise RuntimeError("planned output changed before rollback")
            _rename_entry_noreplace_between(
                area_fd, name, transaction_fd, item["private"]
            )
            _fsync_directory(area_fd)
            _fsync_directory(transaction_fd)

        for (area, name), item in originals.items():
            area_fd = area_fds[area]
            expected = (item["dev"], item["ino"])
            private = _regular_output_entry(
                transaction_fd, item["private"], context="quarantined output"
            )
            public = _regular_output_entry(area_fd, name, context="recovery output")
            if private is None:
                if _entry_identity(public) != expected:
                    raise RuntimeError("original export is missing from recovery state")
                continue
            if _entry_identity(private) != expected or public is not None:
                raise RuntimeError("original export recovery identity is ambiguous")
            _inject("restore-original")
            try:
                _rename_entry_noreplace_between(
                    transaction_fd, item["private"], area_fd, name
                )
            except FileExistsError as exc:
                raise RuntimeError(
                    "original export destination appeared during recovery"
                ) from exc
            restored = _regular_output_entry(
                area_fd, name, context="restored original output"
            )
            if _entry_identity(restored) != expected:
                raise RuntimeError("restored original output identity changed")
            _fsync_directory(transaction_fd)
            _fsync_directory(area_fd)

    allowed = {"journal.json", "committed"}
    allowed.update(item["private"] for item in journal["originals"])
    allowed.update(item["private"] for item in journal["planned"])
    expected_private = {
        item["private"]: (item["dev"], item["ino"])
        for item in journal["originals"] + journal["planned"]
    }
    for name in sorted(os.listdir(transaction_fd)):
        if name not in allowed:
            raise RuntimeError("private export transaction contains an unowned entry")
        entry = os.stat(name, dir_fd=transaction_fd, follow_symlinks=False)
        if stat.S_ISLNK(entry.st_mode) or not stat.S_ISREG(entry.st_mode):
            raise RuntimeError("private export cleanup entry is not a regular file")
        expected = expected_private.get(name)
        if expected is not None and _entry_identity(entry) != expected:
            raise RuntimeError("private export cleanup entry is not owned")
        _inject("cleanup")
        visible = os.stat(name, dir_fd=transaction_fd, follow_symlinks=False)
        if not _same_file_identity(entry, visible):
            raise RuntimeError("private export cleanup identity changed")
        os.unlink(name, dir_fd=transaction_fd)
    _fsync_directory(transaction_fd)
    os.close(transaction_fd)
    os.rmdir(transaction_name, dir_fd=output_fd)
    _fsync_directory(output_fd)


def _recover_export_transactions(output_fd: int, area_fds: dict[str, int]) -> None:
    for name in sorted(os.listdir(output_fd)):
        if not name.startswith(TRANSACTION_PREFIX):
            continue
        entry = os.stat(name, dir_fd=output_fd, follow_symlinks=False)
        if stat.S_ISLNK(entry.st_mode) or not stat.S_ISDIR(entry.st_mode):
            raise RuntimeError("private export transaction path is ambiguous")
        transaction_fd = _open_child_directory(output_fd, name, create=False)
        if stat.S_IMODE(os.fstat(transaction_fd).st_mode) != 0o700:
            os.close(transaction_fd)
            raise RuntimeError("private export transaction permissions are insecure")
        _finish_transaction(
            output_fd,
            name,
            transaction_fd,
            area_fds,
            committed=_transaction_committed(transaction_fd),
        )


def export_final(
    output_root: Path,
    *,
    include_chapters: bool = False,
    include_bilingual: bool = False,
) -> dict:
    with exclusive_consistency_lock(REPO_ROOT):
        return _export_final_locked(
            output_root,
            include_chapters=include_chapters,
            include_bilingual=include_bilingual,
        )


def _recover_before_input_validation(output_root: Path) -> None:
    """Recover a prior durable transaction without consulting current inputs."""

    output_root = _validate_output_path(output_root, directory=True)
    zh_dir = _validate_output_path(output_root / "translated", directory=True)
    bi_dir = _validate_output_path(output_root / "bilingual", directory=True)
    handles = _prepare_output_directories((output_root, zh_dir, bi_dir))
    try:
        output_fd = handles.fd_for(output_root)
        if output_fd is None:
            return
        transaction_names = [
            name for name in os.listdir(output_fd) if name.startswith(TRANSACTION_PREFIX)
        ]
        if not transaction_names:
            return
        area_fds = {
            "root": output_fd,
            "translated": handles.fd_for(zh_dir),
            "bilingual": handles.fd_for(bi_dir),
        }
        if any(fd is None for fd in area_fds.values()):
            raise RuntimeError("private export recovery ancestry is incomplete")
        _recover_export_transactions(
            output_fd, {name: fd for name, fd in area_fds.items() if fd is not None}
        )
        handles.verify_visible()
    finally:
        handles.close()


def _export_final_locked(
    output_root: Path,
    *,
    include_chapters: bool = False,
    include_bilingual: bool = False,
) -> dict:
    _recover_before_input_validation(output_root)
    # Phase 1 is read-only: every source, canonical, segment, singleton, output,
    # and manifest invariant is established before cleanup or any write.
    active_numbers = discover_active_chapter_numbers(REPO_ROOT / "input_jp")
    chapters, sources = _load_canonical_chapters(active_numbers)
    missing_numbers = sorted(active_numbers - chapters.keys())
    if missing_numbers:
        raise RuntimeError("active chapters are missing from canonical segments")

    incomplete_numbers: list[int] = []
    for number in sorted(active_numbers):
        segments = chapters[number].get("segments")
        if (
            not isinstance(segments, list)
            or not segments
            or any(not isinstance(segment, dict) or not _segment_exportable(segment) for segment in segments)
        ):
            incomplete_numbers.append(number)
    if incomplete_numbers:
        raise RuntimeError("active canonical chapters contain empty or unexportable segments")

    zh_dir = output_root / "translated"
    bi_dir = output_root / "bilingual"
    singleton_path = zh_dir / "full_volume_cn.md"
    manifest_path = output_root / "final_export_manifest.json"
    output_root = _validate_output_path(output_root, directory=True)
    zh_dir = _validate_output_path(zh_dir, directory=True)
    bi_dir = _validate_output_path(bi_dir, directory=True)
    singleton_path = _validate_output_path(singleton_path, directory=False)
    manifest_path = _validate_output_path(manifest_path, directory=False)
    output_handles = _prepare_output_directories((output_root, zh_dir, bi_dir))
    try:
        # Existing output is validated as an untrusted public entry, but its
        # bytes are never reused: every successful export is rebuilt from the
        # current consistency-audited canonical segments.
        _filter_existing_singleton(
            singleton_path,
            active_numbers,
            directory_fd=output_handles.fd_for(zh_dir),
        )
        prospective_singleton = (
            "\n".join(
                _render_cn(chapters[number]).rstrip("\n")
                for number in sorted(active_numbers)
            )
            + "\n"
        ).encode("utf-8")
        validated_singleton = _filter_singleton_content(
            prospective_singleton, active_numbers, context="prospective singleton"
        )
        if validated_singleton != prospective_singleton:
            raise RuntimeError("prospective singleton contains non-authoritative chapters")

        prospective_files: dict[Path, bytes] = {singleton_path: prospective_singleton}
        full_bilingual: list[str] = []
        for number in sorted(active_numbers):
            ch = chapters[number]
            if include_chapters:
                prospective_files[zh_dir / f"chapter_{number:03d}_cn.md"] = (
                    _render_cn(ch).encode("utf-8")
                )
            if include_bilingual:
                bilingual = _render_bilingual(ch)
                if include_chapters:
                    prospective_files[bi_dir / f"chapter_{number:03d}_bilingual.md"] = (
                        bilingual.encode("utf-8")
                    )
                full_bilingual.append(bilingual.strip())

        full_volume_bilingual = bi_dir / "full_volume_bilingual.md"
        if include_bilingual:
            prospective_files[full_volume_bilingual] = (
                "\n\n".join(full_bilingual).strip() + "\n"
            ).encode("utf-8")
        for path in prospective_files:
            _validate_output_path(path, directory=False)

        translated_patterns = ("chapter_*_cn.md", "full_volume_cn.md")
        bilingual_patterns = (
            "chapter_*_bilingual.md",
            "full_volume_bilingual.md",
            "workbench_*_bilingual.md",
        )
        cleanup_snapshots = {
            "translated": _cleanup_snapshot(
                zh_dir,
                translated_patterns,
                directory_fd=output_handles.fd_for(zh_dir),
            ),
            "bilingual": _cleanup_snapshot(
                bi_dir,
                bilingual_patterns,
                directory_fd=output_handles.fd_for(bi_dir),
            ),
            "root": _cleanup_snapshot(
                output_root,
                (".DS_Store",),
                directory_fd=output_handles.fd_for(output_root),
            ),
        }
        planned_removed = {
            name: len(entries) for name, entries in cleanup_snapshots.items()
        }
        output_fd = output_handles.fd_for(output_root)
        manifest_expectation = (
            None
            if output_fd is None
            else _entry_identity(
                _regular_output_entry(
                    output_fd,
                    manifest_path.name,
                    context="manifest destination",
                )
            )
        )
        canonical_final_translation = str(singleton_path.relative_to(REPO_ROOT))
        manifest = {
            "schema": "consistency_final_export_v2",
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "output_root": str(output_root.relative_to(REPO_ROOT)),
            "canonical_final_translation": canonical_final_translation,
            "canonical_final_translation_count": 1,
            "final_translation_policy": "singleton_full_volume_cn",
            "chapters_discovered": len(active_numbers),
            "chapters_exported": len(active_numbers),
            "chapters_incomplete": [],
            "chapters_missing": [],
            "canonical_files": len(sources),
            "removed_old_generated_files": planned_removed,
            "translated_dir": str(zh_dir.relative_to(REPO_ROOT)),
            "bilingual_dir": str(bi_dir.relative_to(REPO_ROOT)),
            "full_volume_cn": canonical_final_translation,
            "full_volume_bilingual": (
                str(full_volume_bilingual.relative_to(REPO_ROOT))
                if include_bilingual
                else None
            ),
            "include_chapters": include_chapters,
            "include_bilingual": include_bilingual,
            "chapter_files_exported": len(active_numbers) if include_chapters else 0,
            "bilingual_chapter_files_exported": (
                len(active_numbers) if include_chapters and include_bilingual else 0
            ),
            "auxiliary_files_policy": (
                "chapter and bilingual exports are regenerable only with explicit CLI flags"
            ),
            "sources": sources,
        }
        manifest_bytes = (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode(
            "utf-8"
        )
        _validate_manifest_bytes(manifest_bytes, manifest, active_numbers)

        # Recheck the complete frozen preflight view before directory creation,
        # cleanup, or output writes.
        _assert_cleanup_snapshot(
            zh_dir,
            translated_patterns,
            cleanup_snapshots["translated"],
            directory_fd=output_handles.fd_for(zh_dir),
        )
        _assert_cleanup_snapshot(
            bi_dir,
            bilingual_patterns,
            cleanup_snapshots["bilingual"],
            directory_fd=output_handles.fd_for(bi_dir),
        )
        _assert_cleanup_snapshot(
            output_root,
            (".DS_Store",),
            cleanup_snapshots["root"],
            directory_fd=output_handles.fd_for(output_root),
        )
        if output_fd is not None:
            _assert_output_entry_identity(
                output_fd,
                manifest_path.name,
                manifest_expectation,
                context="manifest destination",
            )

        # Phase 2: all mutations use the same directory handles captured during
        # phase 1; path substitutions can never redirect cleanup or writes.
        output_handles.begin_mutation()
        zh_fd = output_handles.fd_for(zh_dir)
        bi_fd = output_handles.fd_for(bi_dir)
        output_fd = output_handles.fd_for(output_root)
        if zh_fd is None or bi_fd is None or output_fd is None:
            raise RuntimeError("output directory handles are incomplete")

        area_fds = {"root": output_fd, "translated": zh_fd, "bilingual": bi_fd}
        originals = {name: dict(entries) for name, entries in cleanup_snapshots.items()}
        if manifest_expectation is not None:
            originals["root"][manifest_path.name] = manifest_expectation
        planned: dict[str, dict[str, bytes]] = {
            "root": {manifest_path.name: manifest_bytes},
            "translated": {},
            "bilingual": {},
        }
        for path, content in prospective_files.items():
            area = "translated" if path.parent == zh_dir else "bilingual"
            planned[area][path.name] = content

        _inject("validation")
        transaction = _ExportTransaction(output_fd, area_fds, originals, planned)
        transaction_open = True
        committed = False
        try:
            transaction.quarantine()
            output_handles.verify_visible()
            transaction.publish()
            output_handles.verify_visible()
            for path, content in prospective_files.items():
                parent_fd = output_handles.fd_for(path.parent)
                if parent_fd is None:
                    raise RuntimeError("committed output parent handle is missing")
                _verify_committed_file(path, content, directory_fd=parent_fd)
            _verify_committed_file(manifest_path, manifest_bytes, directory_fd=output_fd)
            transaction.mark_committed()
            committed = True
            transaction.close()
            transaction_open = False
            recovery_fd = _open_child_directory(output_fd, transaction.name, create=False)
            _finish_transaction(
                output_fd,
                transaction.name,
                recovery_fd,
                area_fds,
                committed=True,
            )
        except BaseException:
            if transaction_open:
                transaction.close()
                transaction_open = False
            if not committed:
                recovery_fd = _open_child_directory(output_fd, transaction.name, create=False)
                marker_committed = _transaction_committed(recovery_fd)
                _finish_transaction(
                    output_fd,
                    transaction.name,
                    recovery_fd,
                    area_fds,
                    committed=marker_committed,
                )
            raise
        return manifest
    finally:
        output_handles.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Export consistency-audited final volume")
    parser.add_argument("--output-root", type=Path, default=REPO_ROOT / "output_cn")
    parser.add_argument(
        "--include-chapters",
        action="store_true",
        help="also write per-chapter files; default keeps a singleton final volume",
    )
    parser.add_argument(
        "--include-bilingual",
        action="store_true",
        help="also write bilingual output; default removes old bilingual final copies",
    )
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    output_root = args.output_root if args.output_root.is_absolute() else REPO_ROOT / args.output_root
    manifest = export_final(
        output_root,
        include_chapters=args.include_chapters,
        include_bilingual=args.include_bilingual,
    )
    if args.json:
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
    else:
        print(
            f"exported={manifest['chapters_exported']} "
            f"missing={len(manifest['chapters_missing'])} "
            f"incomplete={len(manifest['chapters_incomplete'])} "
            f"output={manifest['output_root']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
