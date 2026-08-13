"""Parse markdown chapter files into paragraph segments."""

from __future__ import annotations

import os
import re
import stat
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Segment:
    segment_id: str
    source_text: str
    draft_text: str = ""
    status: str = "pending"


@dataclass
class ParsedChapter:
    chapter_id: str
    source_path: str
    chapter_label: str
    segments: list[Segment]


_CHAPTER_FILE_NUM_RE = re.compile(r"^(\d+)-")


class ChapterDiscoveryError(RuntimeError):
    """The authoritative numbered source corpus is absent or ambiguous."""


def _claimed_numbered_source_id(name: str) -> int | None:
    """Return the positive ID lexically claimed by a source filename."""

    if Path(name).suffix.lower() not in (".md", ".txt"):
        return None
    match = _CHAPTER_FILE_NUM_RE.match(name)
    if not match:
        return None
    number = int(match.group(1))
    return number if number > 0 else None


def numbered_source_id(path: Path) -> int | None:
    """Return an eligible ID, rejecting unsafe entries that claim one."""

    number = _claimed_numbered_source_id(path.name)
    if number is None:
        return None

    try:
        mode = path.lstat().st_mode
    except OSError as exc:
        raise ChapterDiscoveryError(f"numbered source entry cannot be inspected safely: {path.name}") from exc
    if stat.S_ISLNK(mode) or not stat.S_ISREG(mode):
        raise ChapterDiscoveryError(
            f"numbered source entry must be a regular file: {path.name}"
        )
    return number


def _same_file_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return (left.st_dev, left.st_ino) == (right.st_dev, right.st_ino)


def _open_source_directory(input_dir: Path) -> tuple[int, os.stat_result]:
    """Open a real source directory without following its final component."""

    if not hasattr(os, "O_DIRECTORY") or not hasattr(os, "O_NOFOLLOW"):
        raise ChapterDiscoveryError("safe source directory discovery is unsupported")
    try:
        before = input_dir.lstat()
    except OSError as exc:
        raise ChapterDiscoveryError(f"source directory is missing: {input_dir}") from exc
    if stat.S_ISLNK(before.st_mode):
        raise ChapterDiscoveryError(f"source directory must not be a symlink: {input_dir}")
    if not stat.S_ISDIR(before.st_mode):
        raise ChapterDiscoveryError(f"source path is not a directory: {input_dir}")

    flags = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    try:
        directory_fd = os.open(input_dir, flags)
    except OSError as exc:
        raise ChapterDiscoveryError(f"source directory cannot be opened safely: {input_dir}") from exc
    try:
        opened = os.fstat(directory_fd)
        after = input_dir.lstat()
        if (
            not stat.S_ISDIR(opened.st_mode)
            or stat.S_ISLNK(after.st_mode)
            or not _same_file_identity(before, opened)
            or not _same_file_identity(opened, after)
        ):
            raise ChapterDiscoveryError(f"source directory changed during discovery: {input_dir}")
    except BaseException:
        os.close(directory_fd)
        raise
    return directory_fd, opened


def discover_numbered_source_files(input_dir: Path) -> dict[int, Path]:
    """Strictly discover direct, positive, numbered Markdown/text sources.

    IDs are normalized as integers, so names such as ``1-a.md`` and
    ``001-b.txt`` are an ambiguous duplicate and make discovery fail.
    """

    directory_fd, opened = _open_source_directory(input_dir)
    discovered: dict[int, Path] = {}
    try:
        try:
            names = sorted(os.listdir(directory_fd))
        except OSError as exc:
            raise ChapterDiscoveryError(f"source directory cannot be enumerated safely: {input_dir}") from exc
        for name in names:
            number = _claimed_numbered_source_id(name)
            try:
                entry = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
            except OSError as exc:
                raise ChapterDiscoveryError(
                    f"source entry cannot be inspected safely: {name}"
                ) from exc
            path = input_dir / name
            if number is None:
                continue
            if stat.S_ISLNK(entry.st_mode) or not stat.S_ISREG(entry.st_mode):
                raise ChapterDiscoveryError(
                    f"numbered source entry must be a regular file: {name}"
                )
            previous = discovered.get(number)
            if previous is not None:
                raise ChapterDiscoveryError(
                    f"duplicate normalized source chapter ID {number}: "
                    f"{previous.name}, {path.name}"
                )
            discovered[number] = path

        try:
            after = input_dir.lstat()
        except OSError as exc:
            raise ChapterDiscoveryError(f"source directory changed during discovery: {input_dir}") from exc
        if stat.S_ISLNK(after.st_mode) or not _same_file_identity(opened, after):
            raise ChapterDiscoveryError(f"source directory changed during discovery: {input_dir}")
    finally:
        os.close(directory_fd)

    if not discovered:
        raise ChapterDiscoveryError(f"no numbered source corpus found in {input_dir}")
    return discovered


def chapter_id_from_path(path: Path) -> str:
    stem = path.stem
    m = re.match(r"^(\d+)", stem)
    return f"ch-{m.group(1)}" if m else f"ch-{path.stem[:32]}"


def chapter_numbers_in_input_dir(input_dir: Path) -> set[int]:
    """Numbered chapter files only (excludes README.md and non-numbered .md)."""
    try:
        return set(discover_numbered_source_files(input_dir))
    except ChapterDiscoveryError:
        # Historical counting/range callers intentionally treat an unavailable
        # corpus as empty. Mutation entrypoints use the strict API directly.
        return set()


def count_source_chapters(repo_root: Path) -> int:
    """Count numbered source chapters across input_jp / input_zh (max of dirs)."""
    best = 0
    for dirname in ("input_jp", "input_zh"):
        nums = chapter_numbers_in_input_dir(repo_root / dirname)
        if nums:
            best = max(best, len(nums))
    return best


def chapter_numbers_in_range(
    repo_root: Path,
    ch_start: int,
    ch_end: int,
) -> set[int]:
    nums: set[int] = set()
    for dirname in ("input_jp", "input_zh"):
        nums |= {
            n
            for n in chapter_numbers_in_input_dir(repo_root / dirname)
            if ch_start <= n <= ch_end
        }
    return nums


def parse_chapter_file(path: Path) -> ParsedChapter:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = ""
    subtitle = ""
    for line in lines:
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        elif line.startswith("## ") and not subtitle:
            subtitle = line[3:].strip()
    chapter_label = f"{title} / {subtitle}".strip(" /") or path.stem

    body_lines: list[str] = []
    past_header = False
    for line in lines:
        if line.startswith("#"):
            past_header = True
            continue
        if past_header or not line.startswith("#"):
            if line.startswith("#"):
                continue
            body_lines.append(line)

    body = "\n".join(body_lines).strip()
    raw_paras = [p.strip() for p in re.split(r"\n\n+", body) if p.strip()]
    line_paras = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if not raw_paras:
        raw_paras = line_paras
    elif len(raw_paras) < max(8, len(line_paras) // 3):
        # Narou-style chapters often use single newlines between paragraphs.
        raw_paras = line_paras

    ch_id = chapter_id_from_path(path)
    segments: list[Segment] = []
    for idx, para in enumerate(raw_paras, start=1):
        segments.append(
            Segment(
                segment_id=f"{ch_id}-seg-{idx:03d}",
                source_text=para,
            )
        )
    return ParsedChapter(
        chapter_id=ch_id,
        source_path=str(path),
        chapter_label=chapter_label,
        segments=segments,
    )


def list_chapter_files(input_dir: Path, limit: int, *, offset: int = 0) -> list[Path]:
    files = sorted(
        p
        for p in input_dir.iterdir()
        if numbered_source_id(p) is not None
    )
    if offset < 0:
        raise ValueError("chapter offset must be >= 0")
    if offset >= len(files):
        return []
    end = offset + limit
    return files[offset:end]
