#!/usr/bin/env python3
"""Create or verify a deterministic, metadata-only workspace file baseline."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import stat
import tempfile
from pathlib import Path, PurePosixPath
from typing import Any


REPO_ROOT = Path(__file__).absolute().parent.parent
DEFAULT_ROOT = REPO_ROOT / "workspace"
DEFAULT_BASELINE = REPO_ROOT / ".agent_runtime" / "inspection_reports" / "workspace_file_baseline.json"
SCHEMA = "workspace_file_baseline"
VERSION = 1
HASH_BUFFER_SIZE = 1024 * 1024
SHA256_HEX_LENGTH = 64


class BaselineError(RuntimeError):
    """The baseline could not be safely created or verified."""


def _absolute(path: Path) -> Path:
    return Path(os.path.abspath(os.fspath(path)))


def _kind(file_stat: os.stat_result) -> str:
    mode = file_stat.st_mode
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISDIR(mode):
        return "directory"
    return "other"


def _stat_signature(file_stat: os.stat_result) -> tuple[int, ...]:
    return (
        file_stat.st_dev,
        file_stat.st_ino,
        file_stat.st_mode,
        file_stat.st_nlink,
        file_stat.st_uid,
        file_stat.st_gid,
        file_stat.st_size,
        file_stat.st_mtime_ns,
        file_stat.st_ctime_ns,
    )


def _safe_relative_path(value: Any, *, label: str = "relative_path") -> str:
    if type(value) is not str or not value or "\x00" in value:
        raise BaselineError(f"{label} must be a non-empty string")
    try:
        value.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise BaselineError(f"{label} must be valid UTF-8") from exc
    path = PurePosixPath(value)
    if path.is_absolute() or path.as_posix() != value or any(part in ("", ".", "..") for part in path.parts):
        raise BaselineError(f"{label} must be a normalized safe POSIX relative path")
    return value


def _root_id(root: Path) -> str:
    name = root.name
    _safe_relative_path(name, label="root_id")
    if "/" in name:
        raise BaselineError("root_id must contain one path component")
    return name


def _lstat_at(name: str, dir_fd: int, relative_path: str) -> os.stat_result:
    try:
        return os.lstat(name, dir_fd=dir_fd)
    except OSError as exc:
        raise BaselineError(f"I/O error while lstat-ing {relative_path}") from exc


def _directory_names(dir_fd: int, relative_path: str) -> list[str]:
    try:
        with os.scandir(dir_fd) as entries:
            names = sorted(entry.name for entry in entries)
    except OSError as exc:
        label = relative_path or "root"
        raise BaselineError(f"I/O error while scanning {label}") from exc
    for name in names:
        if not name or name in (".", "..") or "/" in name or "\x00" in name:
            raise BaselineError("tree contains an unsafe path component")
    return names


def _open_at(name: str, dir_fd: int, *, directory: bool, relative_path: str) -> int:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    if directory:
        flags |= getattr(os, "O_DIRECTORY", 0)
    try:
        return os.open(name, flags, dir_fd=dir_fd)
    except OSError as exc:
        raise BaselineError(f"I/O error while opening {relative_path} without following symlinks") from exc


def _hash_regular_file(
    dir_fd: int,
    name: str,
    relative_path: str,
    expected_stat: os.stat_result,
) -> dict[str, Any]:
    fd = _open_at(name, dir_fd, directory=False, relative_path=relative_path)
    try:
        opened_stat = os.fstat(fd)
        expected_signature = _stat_signature(expected_stat)
        if not stat.S_ISREG(opened_stat.st_mode) or _stat_signature(opened_stat) != expected_signature:
            raise BaselineError(f"tree changed while collecting {relative_path}")
        digest = hashlib.sha256()
        bytes_read = 0
        while True:
            block = os.read(fd, HASH_BUFFER_SIZE)
            if not block:
                break
            digest.update(block)
            bytes_read += len(block)
        after_stat = os.fstat(fd)
        if _stat_signature(after_stat) != expected_signature or bytes_read != expected_stat.st_size:
            raise BaselineError(f"tree changed while collecting {relative_path}")
    except OSError as exc:
        raise BaselineError(f"I/O error while hashing {relative_path}") from exc
    finally:
        os.close(fd)

    final_stat = _lstat_at(name, dir_fd, relative_path)
    if _stat_signature(final_stat) != _stat_signature(expected_stat):
        raise BaselineError(f"tree changed while collecting {relative_path}")
    return {
        "relative_path": relative_path,
        "size": expected_stat.st_size,
        "sha256": digest.hexdigest(),
    }


def _capture_once(root: Path, *, hash_files: bool) -> dict[str, Any]:
    try:
        root_before = os.lstat(root)
    except OSError as exc:
        raise BaselineError("root cannot be lstat-ed") from exc
    if stat.S_ISLNK(root_before.st_mode) or not stat.S_ISDIR(root_before.st_mode):
        raise BaselineError("root must be a non-symlink directory")

    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    flags |= getattr(os, "O_DIRECTORY", 0)
    try:
        root_fd = os.open(root, flags)
    except OSError as exc:
        raise BaselineError("root cannot be opened without following symlinks") from exc

    inventory: dict[str, tuple[str, tuple[int, ...]]] = {}
    files: list[dict[str, Any]] = []
    symlinks_skipped = 0

    def walk(dir_fd: int, prefix: str) -> None:
        nonlocal symlinks_skipped
        names_before = _directory_names(dir_fd, prefix)
        for name in names_before:
            relative_path = f"{prefix}/{name}" if prefix else name
            _safe_relative_path(relative_path)
            entry_stat = _lstat_at(name, dir_fd, relative_path)
            entry_kind = _kind(entry_stat)
            entry_signature = _stat_signature(entry_stat)
            inventory[relative_path] = (entry_kind, entry_signature)

            if entry_kind == "symlink":
                symlinks_skipped += 1
                continue
            if entry_kind == "directory":
                child_fd = _open_at(name, dir_fd, directory=True, relative_path=relative_path)
                try:
                    if _stat_signature(os.fstat(child_fd)) != entry_signature:
                        raise BaselineError(f"tree changed while collecting {relative_path}")
                    walk(child_fd, relative_path)
                finally:
                    os.close(child_fd)
                if _stat_signature(_lstat_at(name, dir_fd, relative_path)) != entry_signature:
                    raise BaselineError(f"tree changed while collecting {relative_path}")
            elif entry_kind == "file" and hash_files:
                files.append(_hash_regular_file(dir_fd, name, relative_path, entry_stat))
            elif entry_kind == "file":
                if _stat_signature(_lstat_at(name, dir_fd, relative_path)) != entry_signature:
                    raise BaselineError(f"tree changed while collecting {relative_path}")

        if _directory_names(dir_fd, prefix) != names_before:
            label = prefix or "root"
            raise BaselineError(f"tree membership changed while collecting {label}")

    try:
        if _stat_signature(os.fstat(root_fd)) != _stat_signature(root_before):
            raise BaselineError("root changed while collection started")
        walk(root_fd, "")
        if _stat_signature(os.fstat(root_fd)) != _stat_signature(root_before):
            raise BaselineError("root changed while collecting")
    finally:
        os.close(root_fd)

    try:
        root_after = os.lstat(root)
    except OSError as exc:
        raise BaselineError("root changed while collecting") from exc
    if _stat_signature(root_after) != _stat_signature(root_before):
        raise BaselineError("root changed while collecting")

    files.sort(key=lambda item: item["relative_path"])
    return {
        "root_signature": _stat_signature(root_before),
        "inventory": inventory,
        "files": files,
        "symlinks_skipped": symlinks_skipped,
    }


def _capture_stable_tree(root: Path) -> tuple[list[dict[str, Any]], int]:
    first = _capture_once(root, hash_files=True)
    second = _capture_once(root, hash_files=False)
    if (
        first["root_signature"] != second["root_signature"]
        or first["inventory"] != second["inventory"]
        or first["symlinks_skipped"] != second["symlinks_skipped"]
    ):
        raise BaselineError("tree changed during collection")
    return first["files"], first["symlinks_skipped"]


def _aggregate(files: list[dict[str, Any]]) -> str:
    digest = hashlib.sha256()
    for item in files:
        digest.update(item["relative_path"].encode("utf-8"))
        digest.update(b"\x00")
        digest.update(bytes.fromhex(item["sha256"]))
    return digest.hexdigest()


def build_manifest(root: Path) -> tuple[dict[str, Any], int]:
    root = _absolute(root)
    files, symlinks_skipped = _capture_stable_tree(root)
    manifest = {
        "schema": SCHEMA,
        "version": VERSION,
        "root_id": _root_id(root),
        "file_count": len(files),
        "aggregate_sha256": _aggregate(files),
        "files": files,
    }
    return manifest, symlinks_skipped


def _json_bytes(manifest: dict[str, Any]) -> bytes:
    return (json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")


def _path_is_within(path: Path, directory: Path) -> bool:
    try:
        return os.path.commonpath((os.fspath(path), os.fspath(directory))) == os.fspath(directory)
    except ValueError:
        return False


def _check_baseline_location(root: Path, baseline: Path) -> None:
    if _path_is_within(baseline, root):
        raise BaselineError("baseline must be outside root to avoid self-inclusion")


def _atomic_write(path: Path, data: bytes) -> None:
    try:
        parent_stat = os.lstat(path.parent)
    except OSError as exc:
        raise BaselineError("baseline parent cannot be lstat-ed") from exc
    if stat.S_ISLNK(parent_stat.st_mode) or not stat.S_ISDIR(parent_stat.st_mode):
        raise BaselineError("baseline parent must be a non-symlink directory")
    try:
        existing = os.lstat(path)
    except FileNotFoundError:
        existing = None
    except OSError as exc:
        raise BaselineError("baseline cannot be lstat-ed") from exc
    if existing is not None and not stat.S_ISREG(existing.st_mode):
        raise BaselineError("baseline must be absent or a regular file")

    temp_name: str | None = None
    try:
        fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
        temp_name = None
    except (OSError, ValueError) as exc:
        raise BaselineError("baseline atomic replacement failed") from exc
    finally:
        if temp_name is not None:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass


def create_baseline(root: Path, baseline: Path) -> dict[str, Any]:
    root = _absolute(root)
    baseline = _absolute(baseline)
    _check_baseline_location(root, baseline)
    manifest, symlinks_skipped = build_manifest(root)
    _atomic_write(baseline, _json_bytes(manifest))
    return {
        "command": "create",
        "status": "created",
        "root_id": manifest["root_id"],
        "file_count": manifest["file_count"],
        "aggregate_sha256": manifest["aggregate_sha256"],
        "symlinks_skipped": symlinks_skipped,
    }


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise BaselineError("baseline JSON contains duplicate object keys")
        result[key] = value
    return result


def _read_manifest(path: Path) -> Any:
    try:
        before = os.lstat(path)
    except OSError as exc:
        raise BaselineError("baseline cannot be lstat-ed") from exc
    if not stat.S_ISREG(before.st_mode):
        raise BaselineError("baseline must be a regular file")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        fd = os.open(path, flags)
        try:
            if _stat_signature(os.fstat(fd)) != _stat_signature(before):
                raise BaselineError("baseline changed while reading")
            chunks: list[bytes] = []
            while True:
                chunk = os.read(fd, HASH_BUFFER_SIZE)
                if not chunk:
                    break
                chunks.append(chunk)
            if _stat_signature(os.fstat(fd)) != _stat_signature(before):
                raise BaselineError("baseline changed while reading")
        finally:
            os.close(fd)
        if _stat_signature(os.lstat(path)) != _stat_signature(before):
            raise BaselineError("baseline changed while reading")
    except BaselineError:
        raise
    except OSError as exc:
        raise BaselineError("I/O error while reading baseline") from exc
    try:
        return json.loads(b"".join(chunks).decode("utf-8"), object_pairs_hook=_reject_duplicate_keys)
    except BaselineError:
        raise
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BaselineError("baseline is not valid UTF-8 JSON") from exc


def validate_manifest(document: Any) -> dict[str, Any]:
    if type(document) is not dict:
        raise BaselineError("baseline top level must be an object")
    expected_keys = {"schema", "version", "root_id", "file_count", "aggregate_sha256", "files"}
    if set(document) != expected_keys:
        raise BaselineError("baseline top-level schema keys are invalid")
    if document["schema"] != SCHEMA or type(document["schema"]) is not str:
        raise BaselineError("baseline schema is invalid")
    if type(document["version"]) is not int or document["version"] != VERSION:
        raise BaselineError("baseline version is invalid")
    _safe_relative_path(document["root_id"], label="root_id")
    if "/" in document["root_id"]:
        raise BaselineError("root_id must contain one path component")
    if type(document["file_count"]) is not int or document["file_count"] < 0:
        raise BaselineError("file_count must be a non-negative integer")
    if type(document["aggregate_sha256"]) is not str or not _is_sha256(document["aggregate_sha256"]):
        raise BaselineError("aggregate_sha256 is invalid")
    if type(document["files"]) is not list:
        raise BaselineError("files must be an array")

    previous_path: str | None = None
    for item in document["files"]:
        if type(item) is not dict or set(item) != {"relative_path", "size", "sha256"}:
            raise BaselineError("file entry schema is invalid")
        relative_path = _safe_relative_path(item["relative_path"])
        if previous_path is not None and relative_path <= previous_path:
            raise BaselineError("file entries must be strictly sorted without duplicates")
        previous_path = relative_path
        if type(item["size"]) is not int or item["size"] < 0:
            raise BaselineError("file size must be a non-negative integer")
        if type(item["sha256"]) is not str or not _is_sha256(item["sha256"]):
            raise BaselineError("file sha256 is invalid")

    if document["file_count"] != len(document["files"]):
        raise BaselineError("file_count does not match files")
    if document["aggregate_sha256"] != _aggregate(document["files"]):
        raise BaselineError("aggregate_sha256 is not self-consistent")
    return document


def _is_sha256(value: str) -> bool:
    return len(value) == SHA256_HEX_LENGTH and all(character in "0123456789abcdef" for character in value)


def verify_baseline(root: Path, baseline: Path) -> tuple[int, dict[str, Any]]:
    root = _absolute(root)
    baseline = _absolute(baseline)
    _check_baseline_location(root, baseline)
    expected = validate_manifest(_read_manifest(baseline))
    actual_root_id = _root_id(root)
    if expected["root_id"] != actual_root_id:
        raise BaselineError("baseline root_id does not match root")

    actual_files, symlinks_skipped = _capture_stable_tree(root)
    actual_by_path = {item["relative_path"]: item for item in actual_files}
    expected_by_path = {item["relative_path"]: item for item in expected["files"]}
    added = sorted(actual_by_path.keys() - expected_by_path.keys())
    removed = sorted(expected_by_path.keys() - actual_by_path.keys())
    changed: list[dict[str, Any]] = []
    for relative_path in sorted(actual_by_path.keys() & expected_by_path.keys()):
        actual_item = actual_by_path[relative_path]
        expected_item = expected_by_path[relative_path]
        if actual_item["size"] != expected_item["size"] or actual_item["sha256"] != expected_item["sha256"]:
            changed.append(
                {
                    "relative_path": relative_path,
                    "expected": {"size": expected_item["size"], "sha256": expected_item["sha256"]},
                    "actual": {"size": actual_item["size"], "sha256": actual_item["sha256"]},
                }
            )

    actual_aggregate = _aggregate(actual_files)
    drift = bool(added or removed or changed)
    summary = {
        "command": "verify",
        "status": "drift" if drift else "ok",
        "root_id": actual_root_id,
        "expected_file_count": expected["file_count"],
        "actual_file_count": len(actual_files),
        "expected_aggregate_sha256": expected["aggregate_sha256"],
        "actual_aggregate_sha256": actual_aggregate,
        "symlinks_skipped": symlinks_skipped,
        "added": added,
        "removed": removed,
        "changed": changed,
    }
    return (1 if drift else 0), summary


def _resolve_cli_path(path: Path) -> Path:
    return path if path.is_absolute() else REPO_ROOT / path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create or verify the deterministic workspace file baseline")
    parser.add_argument("command", choices=("create", "verify"))
    parser.add_argument("--json", action="store_true", help="compatibility flag; output is always JSON")
    parser.add_argument("--root", type=Path, default=DEFAULT_ROOT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args(argv)
    root = _resolve_cli_path(args.root)
    baseline = _resolve_cli_path(args.baseline)
    try:
        if args.command == "create":
            summary = create_baseline(root, baseline)
            exit_code = 0
        else:
            exit_code, summary = verify_baseline(root, baseline)
    except BaselineError as exc:
        summary = {"command": args.command, "status": "error", "error": str(exc)}
        exit_code = 2
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
