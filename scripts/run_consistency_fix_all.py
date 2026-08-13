#!/usr/bin/env python3
"""Run fix_terminology_consistency.py across draft/run segments files.

By default this only processes the canonical draft_stage_b segments.json
files for chapters that have a corresponding numbered file in ``input_jp/``.
Duplicate chapter-range coverage is resolved by latest mtime. Use --scope
all-runs for explicit workspace cleanup rounds that must repair stale target
text in historical runs too; that scope is still limited to current source IDs.

Usage:
    python3 scripts/run_consistency_fix_all.py --dry-run
    python3 scripts/run_consistency_fix_all.py            # writes changes
    python3 scripts/run_consistency_fix_all.py --scope all-runs --update-all-target-fields --dry-run
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import stat
import secrets
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.translation.chapter_parser import discover_numbered_source_files
from consistency_transaction_lock import ConsistencyLock, exclusive_consistency_lock
from secure_consistency_files import atomic_write_new_or_replace, create_bound_empty, open_parent, read_regular, unlink_regular

CANONICAL_CHAPTER_ID_RE = re.compile(r"^ch-(?P<number>\d+)$")


def canonical_chapter_number(chapter_id: object) -> int:
    match = CANONICAL_CHAPTER_ID_RE.fullmatch(str(chapter_id or ""))
    if not match or int(match.group("number")) <= 0:
        raise ValueError("malformed canonical chapter ID")
    return int(match.group("number"))


def discover_active_chapter_numbers(input_dir: Path | None = None) -> set[int]:
    """Return the exact chapter IDs represented by numbered source filenames.

    A missing or empty numbered corpus is an unsafe state: callers must stop
    instead of inferring a range from stale run/output artifacts.
    """

    source_dir = input_dir or REPO_ROOT / "input_jp"
    return set(discover_numbered_source_files(source_dir))


def _chapter_numbers_in_file(path: Path) -> list[int]:
    try:
        content, _identity = read_regular(path)
        doc = json.loads(content.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"invalid canonical segments file: {path.name}") from exc
    raw_chapters = doc.get("chapters") if isinstance(doc, dict) else None
    if not isinstance(raw_chapters, list):
        raise RuntimeError(f"canonical chapters must be a list: {path.name}")
    numbers: list[int] = []
    seen: set[int] = set()
    for chapter in raw_chapters:
        chapter_id = chapter.get("chapter_id") if isinstance(chapter, dict) else None
        try:
            number = canonical_chapter_number(chapter_id)
        except ValueError:
            raise RuntimeError(f"malformed canonical chapter ID in {path.name}")
        if number in seen:
            raise RuntimeError(f"duplicate normalized canonical chapter ID {number} in {path.name}")
        seen.add(number)
        numbers.append(number)
    return numbers


def _contiguous_ranges(numbers: set[int]) -> list[tuple[int, int]]:
    ordered = sorted(numbers)
    if not ordered:
        return []
    ranges: list[tuple[int, int]] = []
    start = end = ordered[0]
    for number in ordered[1:]:
        if number == end + 1:
            end = number
            continue
        ranges.append((start, end))
        start = end = number
    ranges.append((start, end))
    return ranges


def build_chapter_jobs(files: list[Path], active_numbers: set[int]) -> list[tuple[Path, int, int]]:
    """Build exact source-ID jobs, splitting gaps so stale IDs are never fixed."""

    jobs: list[tuple[Path, int, int]] = []
    for path in sorted(files, key=lambda item: str(item)):
        selected = set(_chapter_numbers_in_file(path)) & active_numbers
        jobs.extend((path, start, end) for start, end in _contiguous_ranges(selected))
    return jobs


def discover_canonical_files() -> list[Path]:
    files: list[str] = []
    for base in ("workspace/runs", "workspace/archived_runs"):
        base_path = REPO_ROOT / base
        try:
            base_fd, _leaf = open_parent(base_path / ".scan")
        except FileNotFoundError:
            continue
        try:
            for name in sorted(os.listdir(base_fd)):
                if not fnmatch.fnmatchcase(name, "run_*_draft_stage_b_50ch"):
                    continue
                entry = os.stat(name, dir_fd=base_fd, follow_symlinks=False)
                if stat.S_ISLNK(entry.st_mode) or not stat.S_ISDIR(entry.st_mode):
                    raise RuntimeError("canonical run ancestry must be real directories")
                files.append(str(base_path / name / "segments.json"))
        finally:
            os.close(base_fd)

    ranges: dict[tuple[int, int], list[tuple[str, float]]] = {}
    for f in files:
        nums = _chapter_numbers_in_file(Path(f))
        if not nums:
            continue
        key = (min(nums), max(nums))
        _content, identity = read_regular(Path(f))
        ranges.setdefault(key, []).append((f, os.stat(f, follow_symlinks=False).st_mtime))

    chosen = []
    for key, candidates in ranges.items():
        candidates.sort(key=lambda c: c[1], reverse=True)
        chosen.append(Path(candidates[0][0]))
    return chosen


def discover_all_run_files() -> list[Path]:
    files: set[Path] = set()
    for base in ("workspace/runs", "workspace/archived_runs"):
        root = REPO_ROOT / base
        try:
            root_fd, _leaf = open_parent(root / ".scan")
        except FileNotFoundError:
            continue
        try:
            _collect_segments_files(root_fd, root, files)
        finally:
            os.close(root_fd)
    return sorted(files)


def _collect_segments_files(directory_fd: int, path: Path, files: set[Path]) -> None:
    for name in sorted(os.listdir(directory_fd)):
        entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
        if stat.S_ISLNK(entry.st_mode):
            raise RuntimeError("run file ancestry and entries must not be symlinks")
        if stat.S_ISDIR(entry.st_mode):
            child_fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=directory_fd)
            try:
                _collect_segments_files(child_fd, path / name, files)
            finally:
                os.close(child_fd)
        elif name == "segments.json":
            if not stat.S_ISREG(entry.st_mode):
                raise RuntimeError("segments target must be a regular file")
            files.add(path / name)


def main(argv: list[str] | None = None) -> int:
    with exclusive_consistency_lock(REPO_ROOT) as lock:
        return _main_locked(argv, lock)


def _main_locked(argv: list[str] | None, lock: ConsistencyLock) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--diff-log", type=Path, default=None)
    parser.add_argument(
        "--scope",
        choices=("canonical", "all-runs"),
        default="canonical",
        help="canonical final-export inputs by default; all-runs repairs stale workspace run targets",
    )
    parser.add_argument(
        "--update-all-target-fields",
        action="store_true",
        help="forward to fix_terminology_consistency.py for explicit full workspace cleanup",
    )
    args = parser.parse_args(argv)

    active_numbers = discover_active_chapter_numbers()
    candidate_files = discover_canonical_files() if args.scope == "canonical" else discover_all_run_files()
    bound_identities = {path: read_regular(path)[1] for path in candidate_files}
    jobs = build_chapter_jobs(candidate_files, active_numbers)
    target_files = {path for path, _start, _end in jobs}
    print(
        f"{args.scope} files: {len(target_files)}; active source chapters: {len(active_numbers)}",
        file=sys.stderr,
    )

    total_changed = 0
    total_segments = 0
    total_rule_hits: dict[str, int] = {}
    total_skipped_hits: dict[str, int] = {}
    per_file = []
    diff_logs: list[Path] = []
    owned_temp_paths: dict[Path, tuple[int, int]] = {}
    failed = False
    try:
        for job_index, (f, chapter_start, chapter_end) in enumerate(jobs):
            tmp_diff = None
            if args.diff_log:
                tmp_diff = args.diff_log.with_name(
                    f".{args.diff_log.name}.job-{job_index:03d}.{secrets.token_hex(16)}.json"
                )
                temp_identity = create_bound_empty(tmp_diff)
                owned_temp_paths[tmp_diff] = temp_identity
            cmd = [
                sys.executable,
                str(REPO_ROOT / "scripts" / "fix_terminology_consistency.py"),
                "--segments-file", str(f),
                "--chapters", str(chapter_start), str(chapter_end),
            ]
            bound_identity = bound_identities[f]
            cmd.extend(["--expected-dev", str(bound_identity[0]), "--expected-ino", str(bound_identity[1])])
            if tmp_diff:
                cmd.extend(["--diff-log", str(tmp_diff)])
                cmd.extend(["--diff-log-expected-dev", str(temp_identity[0]), "--diff-log-expected-ino", str(temp_identity[1])])
            if args.update_all_target_fields:
                cmd.append("--update-all-target-fields")
            if args.dry_run:
                cmd.append("--dry-run")
            child_env = os.environ.copy()
            child_env.update(lock.child_environment())
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                cwd=REPO_ROOT,
                env=child_env,
                pass_fds=(lock.fd,),
            )
            if result.returncode != 0:
                try:
                    display_path = f.relative_to(REPO_ROOT)
                except ValueError:
                    display_path = Path(f.name)
                print(
                    f"FAILED file={display_path} job={chapter_start}-{chapter_end} "
                    f"status={result.returncode}",
                    file=sys.stderr,
                )
                failed = True
                break
            try:
                summary = json.loads(result.stdout)
                if not isinstance(summary, dict):
                    raise TypeError
                changed_segments = int(summary["changed_segments"])
                segment_count = int(summary["total_segments"])
                rule_hits = summary.get("rule_hits", {})
                skipped_hits = summary.get("skipped_ambiguous_hits", {})
                if not isinstance(rule_hits, dict) or not isinstance(skipped_hits, dict):
                    raise TypeError
                normalized_rule_hits = {str(key): int(value) for key, value in rule_hits.items()}
                normalized_skipped_hits = {str(key): int(value) for key, value in skipped_hits.items()}
            except (KeyError, TypeError, ValueError, json.JSONDecodeError):
                print(
                    f"FAILED file={f.name} job={chapter_start}-{chapter_end} status=invalid-summary",
                    file=sys.stderr,
                )
                failed = True
                break
            bound_identities[f] = read_regular(f)[1]
            total_changed += changed_segments
            total_segments += segment_count
            for variant, count in normalized_rule_hits.items():
                total_rule_hits[variant] = total_rule_hits.get(variant, 0) + count
            for variant, count in normalized_skipped_hits.items():
                total_skipped_hits[variant] = total_skipped_hits.get(variant, 0) + count
            if changed_segments:
                per_file.append({"file": str(f.relative_to(REPO_ROOT)), "changed": changed_segments})
            if tmp_diff:
                try:
                    read_regular(tmp_diff)
                except FileNotFoundError:
                    pass
                else:
                    diff_logs.append(tmp_diff)

        if failed:
            return 1

        if args.diff_log:
            combined = {"summary": {}, "diffs": []}
            for tmp in diff_logs:
                content, _identity = read_regular(tmp)
                doc = json.loads(content.decode("utf-8"))
                combined["diffs"].extend(doc.get("diffs", []))
            combined["summary"] = {
                "files_processed": len(target_files),
                "chapter_jobs_processed": len(jobs),
                "active_source_chapters": len(active_numbers),
                "total_segments": total_segments,
                "total_changed_segments": total_changed,
                "rule_hits": dict(sorted(total_rule_hits.items(), key=lambda kv: -kv[1])),
                "skipped_ambiguous_hits": dict(sorted(total_skipped_hits.items(), key=lambda kv: -kv[1])),
                "scope": args.scope,
                "target_field_mode": "all_target_fields" if args.update_all_target_fields else "effective_text",
                "dry_run": args.dry_run,
            }
            _write_json_atomic(args.diff_log, combined)

        print(json.dumps(
            {
                "files_processed": len(target_files),
                "chapter_jobs_processed": len(jobs),
                "active_source_chapters": len(active_numbers),
                "total_segments": total_segments,
                "total_changed_segments": total_changed,
                "files_with_changes": per_file,
                "rule_hits": dict(sorted(total_rule_hits.items(), key=lambda kv: -kv[1])),
                "skipped_ambiguous_hits": dict(sorted(total_skipped_hits.items(), key=lambda kv: -kv[1])),
                "scope": args.scope,
                "target_field_mode": "all_target_fields" if args.update_all_target_fields else "effective_text",
                "dry_run": args.dry_run,
            },
            ensure_ascii=False,
            indent=2,
        ))
        return 0
    finally:
        for tmp, identity in owned_temp_paths.items():
            try:
                unlink_regular(tmp, identity)
            except FileNotFoundError:
                pass


def _write_json_atomic(path: Path, value: dict) -> None:
    content = (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    atomic_write_new_or_replace(path, content)


if __name__ == "__main__":
    raise SystemExit(main())
