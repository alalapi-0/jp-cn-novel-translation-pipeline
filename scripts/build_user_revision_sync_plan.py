#!/usr/bin/env python3
"""Build a user-revision sync plan on stdout; never apply proposed writes."""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import re
import secrets
import stat
import sys
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from revision_sync.adapters import aggregate_input_hashes, load_repository_inputs  # noqa: E402
from revision_sync.plan import build_sync_plan, validate_sync_plan  # noqa: E402

APPROVED_OUTPUT_ROOT = REPO_ROOT / "artifacts" / "user_revision_sync"
_PLAN_NAME_RE = re.compile(r"^(?:user_revision_sync_plan(?:_[a-z0-9][a-z0-9_-]*)?|ch\d{3}_\d{3}_sync_plan)\.json$")


def _load_payload(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _segments(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [dict(item) for item in payload]
    if isinstance(payload, dict):
        if isinstance(payload.get("segments"), list):
            return [dict(item) for item in payload["segments"]]
        chapters = payload.get("chapters")
        if isinstance(chapters, list):
            result: list[dict[str, Any]] = []
            for chapter in chapters:
                chapter_id = chapter.get("chapter_id")
                for item in chapter.get("segments", []):
                    record = dict(item)
                    record.setdefault("chapter_id", chapter_id)
                    result.append(record)
            return result
    raise ValueError("JSON input must be a segment list or contain segments/chapters")


def _hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _absolute_lexical(path: Path) -> Path:
    """Return an absolute normalized path without resolving symlinks."""
    return Path(os.path.abspath(os.fspath(path)))


def _validate_output_name(output: Path, args: argparse.Namespace) -> Path:
    """Validate everything that can be checked before touching the artifact root."""
    normalized = _absolute_lexical(output)
    approved = _absolute_lexical(APPROVED_OUTPUT_ROOT)
    repo = _absolute_lexical(REPO_ROOT)
    if not _is_within(approved, repo):
        raise ValueError("approved plan artifact root escapes repository")
    if normalized.parent != approved or not _PLAN_NAME_RE.fullmatch(normalized.name):
        raise ValueError(f"output must be a recognized JSON sync plan directly under {APPROVED_OUTPUT_ROOT}")
    input_files = [
        args.canonical, args.revision, args.canonical_full_volume, args.policy_json,
        args.term_proposals, args.character_proposals,
    ]
    for input_path in (path for path in input_files if path is not None):
        input_normalized = _absolute_lexical(input_path)
        if normalized == input_normalized or normalized == input_path.resolve(strict=False):
            raise ValueError(f"output path would overwrite an input: {normalized}")
    return normalized


_DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
_NOFOLLOW = getattr(os, "O_NOFOLLOW", 0)


def _rollback_created_directories(created: list[tuple[int, str]]) -> None:
    for parent_fd, name in reversed(created):
        try:
            os.rmdir(name, dir_fd=parent_fd)
        except OSError:
            # A non-empty or replaced directory is no longer exclusively ours.
            pass


@contextmanager
def _approved_output_directory() -> Iterator[tuple[int, list[int]]]:
    """Open/create the fixed output root without following any component symlink."""
    fds: list[int] = []
    created: list[tuple[int, str]] = []
    succeeded = False
    try:
        repo_fd = os.open(REPO_ROOT, _DIRECTORY_FLAGS)
        fds.append(repo_fd)
        parent_fd = repo_fd
        for name in ("artifacts", "user_revision_sync"):
            try:
                child_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
            except FileNotFoundError:
                try:
                    os.mkdir(name, mode=0o755, dir_fd=parent_fd)
                    created.append((parent_fd, name))
                except FileExistsError:
                    pass
                child_fd = os.open(name, _DIRECTORY_FLAGS, dir_fd=parent_fd)
            except OSError as exc:
                if exc.errno in (errno.ELOOP, errno.ENOTDIR):
                    raise ValueError(f"approved output component must be a real directory: {name}") from exc
                raise
            fds.append(child_fd)
            parent_fd = child_fd
        yield fds[-1], fds
        succeeded = True
    finally:
        if not succeeded:
            _rollback_created_directories(created)
        for descriptor in reversed(fds):
            os.close(descriptor)


def _revalidate_directory_chain(fds: list[int]) -> None:
    for parent_fd, child_fd, name in zip(fds, fds[1:], ("artifacts", "user_revision_sync")):
        current = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
        opened = os.fstat(child_fd)
        if not stat.S_ISDIR(current.st_mode) or (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError(f"approved output component changed during write: {name}")


def _validate_existing_output(directory_fd: int, name: str, args: argparse.Namespace) -> None:
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NONBLOCK | getattr(os, "O_CLOEXEC", 0) | _NOFOLLOW,
            dir_fd=directory_fd,
        )
    except FileNotFoundError:
        return
    except OSError as exc:
        if exc.errno in (errno.ELOOP, errno.ENOTDIR):
            raise ValueError("output path must not be a symlink") from exc
        raise
    try:
        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode):
            raise ValueError("existing output must be a regular generated plan artifact")
        current = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if (current.st_dev, current.st_ino) != (opened.st_dev, opened.st_ino):
            raise ValueError("output path changed during validation")
        for input_path in (
            args.canonical, args.revision, args.canonical_full_volume, args.policy_json,
            args.term_proposals, args.character_proposals,
        ):
            if input_path is None:
                continue
            try:
                input_stat = os.stat(input_path, follow_symlinks=True)
            except FileNotFoundError:
                continue
            if (input_stat.st_dev, input_stat.st_ino) == (opened.st_dev, opened.st_ino):
                raise ValueError(f"output path would overwrite an input: {input_path}")
        with os.fdopen(os.dup(descriptor), encoding="utf-8") as stream:
            existing = json.load(stream)
        if not isinstance(existing, dict) or existing.get("plan_type") != "user_revision_sync_plan" or existing.get("schema_version") != 1:
            raise ValueError("refusing to overwrite an unrecognized existing file")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("refusing to overwrite an unrecognized existing file") from exc
    finally:
        os.close(descriptor)


def _atomic_write_json(path: Path, payload: dict[str, Any], args: argparse.Namespace) -> None:
    rendered = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    with _approved_output_directory() as (directory_fd, chain_fds):
        _revalidate_directory_chain(chain_fds)
        _validate_existing_output(directory_fd, path.name, args)
        temporary_name = f".{path.name}.{secrets.token_hex(12)}.tmp"
        temporary_fd = os.open(
            temporary_name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_CLOEXEC", 0) | _NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        try:
            with os.fdopen(temporary_fd, mode="w", encoding="utf-8", closefd=False) as handle:
                handle.write(rendered)
                handle.flush()
                os.fsync(handle.fileno())
            _revalidate_directory_chain(chain_fds)
            _validate_existing_output(directory_fd, path.name, args)
            os.replace(temporary_name, path.name, src_dir_fd=directory_fd, dst_dir_fd=directory_fd)
        except BaseException:
            try:
                os.unlink(temporary_name, dir_fd=directory_fd)
            except FileNotFoundError:
                pass
            raise
        finally:
            os.close(temporary_fd)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--canonical", type=Path, help="structured canonical JSON")
    parser.add_argument("--revision", type=Path, help="structured revised JSON")
    parser.add_argument("--source-dir", type=Path)
    parser.add_argument("--canonical-full-volume", type=Path)
    parser.add_argument("--revision-dir", type=Path)
    parser.add_argument("--chapter-start", type=int, default=1)
    parser.add_argument("--chapter-end", type=int, default=86)
    parser.add_argument("--chapter-87-disposition")
    parser.add_argument("--term-proposals", type=Path)
    parser.add_argument("--character-proposals", type=Path)
    parser.add_argument("--policy-json", type=Path)
    parser.add_argument("--output", type=Path, help="atomically write this generated plan artifact")
    args = parser.parse_args(argv)

    structured = args.canonical is not None or args.revision is not None
    repository = any(value is not None for value in (args.source_dir, args.canonical_full_volume, args.revision_dir))
    if structured == repository:
        parser.error("choose exactly one input mode: --canonical/--revision or repository input trio")
    policy = _load_payload(args.policy_json) if args.policy_json else {}
    if not isinstance(policy, dict):
        parser.error("--policy-json must contain an object")
    chapter_87_disposition = args.chapter_87_disposition or policy.get("chapter_87_disposition")
    if not chapter_87_disposition:
        parser.error("--chapter-87-disposition is required directly or through --policy-json")
    if structured:
        if not args.canonical or not args.revision:
            parser.error("structured mode requires both --canonical and --revision")
        canonical = _segments(_load_payload(args.canonical))
        revised = _segments(_load_payload(args.revision))
        input_hashes = {
            "canonical_sha256": _hash(args.canonical),
            "revision_sha256": _hash(args.revision),
        }
    else:
        if not all((args.source_dir, args.canonical_full_volume, args.revision_dir)):
            parser.error("repository mode requires --source-dir, --canonical-full-volume, and --revision-dir")
        try:
            canonical, revised = load_repository_inputs(
                args.source_dir, args.canonical_full_volume, args.revision_dir,
                args.chapter_start, args.chapter_end,
            )
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        input_hashes = {
            "source_aggregate_sha256": aggregate_input_hashes([args.source_dir]),
            "canonical_sha256": aggregate_input_hashes([args.canonical_full_volume]),
            "revision_aggregate_sha256": aggregate_input_hashes([args.revision_dir]),
        }
    terms = _load_payload(args.term_proposals) if args.term_proposals else policy.get("term_proposals", [])
    characters = _load_payload(args.character_proposals) if args.character_proposals else policy.get("character_proposals", [])
    if args.policy_json:
        input_hashes["policy_sha256"] = _hash(args.policy_json)
    if args.term_proposals:
        input_hashes["term_proposals_sha256"] = _hash(args.term_proposals)
    if args.character_proposals:
        input_hashes["character_proposals_sha256"] = _hash(args.character_proposals)
    policy_paths = dict(policy.get("paths", {}))
    if repository:
        policy_paths = {
            "source_dir": str(args.source_dir),
            "revision_dir": str(args.revision_dir),
            "canonical_full_volume": str(args.canonical_full_volume),
            **policy_paths,
        }
    if args.output:
        policy_paths["report_target"] = str(args.output)
    try:
        plan = build_sync_plan(
            canonical,
            revised,
            input_hashes=input_hashes,
            chapter_87_disposition=chapter_87_disposition,
            term_proposals=terms,
            character_proposals=characters,
            classified_decisions=policy.get("classified_decisions", []),
            forum_formatting_policy=policy.get("forum_formatting_policy"),
            paths=policy_paths,
            owner_decisions=policy.get("owner_decisions", []),
            content_policies=policy.get("content_policies", {}),
            application_authorization=policy.get("application_authorization", {}),
            validation_evidence=policy.get("validation_evidence", {}),
        )
        validate_sync_plan(plan)
    except ValueError as exc:
        parser.error(str(exc))
    if args.output:
        try:
            output = _validate_output_name(args.output, args)
            _atomic_write_json(output, plan, args)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
    else:
        json.dump(plan, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
