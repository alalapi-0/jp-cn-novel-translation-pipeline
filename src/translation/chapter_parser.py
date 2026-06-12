"""Parse markdown chapter files into paragraph segments."""

from __future__ import annotations

import re
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


def chapter_id_from_path(path: Path) -> str:
    stem = path.stem
    m = re.match(r"^(\d+)", stem)
    return f"ch-{m.group(1)}" if m else f"ch-{path.stem[:32]}"


def chapter_numbers_in_input_dir(input_dir: Path) -> set[int]:
    """Numbered chapter files only (excludes README.md and non-numbered .md)."""
    out: set[int] = set()
    if not input_dir.is_dir():
        return out
    for path in input_dir.iterdir():
        if not path.is_file() or path.suffix.lower() not in (".md", ".txt"):
            continue
        if path.name == "README.md":
            continue
        match = _CHAPTER_FILE_NUM_RE.match(path.name)
        if match:
            out.add(int(match.group(1)))
    return out


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
        if p.is_file() and p.suffix.lower() in (".md", ".txt") and p.name != "README.md"
    )
    if offset < 0:
        raise ValueError("chapter offset must be >= 0")
    if offset >= len(files):
        return []
    end = offset + limit
    return files[offset:end]
