"""Parse markdown chapter files into paragraph segments."""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Segment:
    segment_id: str
    source_text: str
    draft_text: str = ""
    status: str = "pending"
    source_binding: dict | None = None


@dataclass
class ParsedChapter:
    chapter_id: str
    source_path: str
    chapter_label: str
    segments: list[Segment]
    source_revision: str = ""
    parser_version: str = ""


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


def parse_chapter_file(path: Path, *, source_bytes: bytes | None = None) -> ParsedChapter:
    text = source_bytes.decode("utf-8") if source_bytes is not None else path.read_text(encoding="utf-8")
    lines = text.splitlines()
    title = ""
    subtitle = ""
    for line in lines:
        if line.startswith("# ") and not title:
            title = line[2:].strip()
        elif line.startswith("## ") and not subtitle:
            subtitle = line[3:].strip()
    chapter_label = f"{title} / {subtitle}".strip(" /") or path.stem

    body_lines = []; line_maps = []; cursor = 0
    for raw in text.splitlines(keepends=True):
        parts = raw.splitlines(); line = parts[0] if parts else ''
        if not line.startswith('#'):
            body_lines.append(line)
            line_maps.append(([(cursor+i,cursor+i+1) for i in range(len(line))],
                              (cursor+len(line),cursor+len(raw))))
        cursor += len(raw)
    joined = '\n'.join(body_lines); mapping = []
    for i, (chars, newline) in enumerate(line_maps):
        mapping.extend(chars)
        if i < len(line_maps)-1: mapping.append(newline)
    left = len(joined)-len(joined.lstrip()); right = len(joined.rstrip())
    body = joined[left:right]; mapping = mapping[left:right]
    raw_paras = [p.strip() for p in re.split(r"\n\n+", body) if p.strip()]
    line_paras = [ln.strip() for ln in body.splitlines() if ln.strip()]
    if not raw_paras:
        raw_paras = line_paras
    elif len(raw_paras) < max(8, len(line_paras) // 3):
        # Narou-style chapters often use single newlines between paragraphs.
        raw_paras = line_paras

    ch_id = chapter_id_from_path(path)
    from .source_versions import make_source_binding, text_sha, validate_source_binding
    revision = text_sha(text); counts = Counter(raw_paras); occurrences = Counter(); position = 0
    segments: list[Segment] = []
    for idx, para in enumerate(raw_paras, start=1):
        start = body.find(para,position); end = start+len(para); position=end; spans=[]
        if start < 0: raise ValueError('parsed source cannot be located in selected bytes')
        for a,b in mapping[start:end]:
            if a >= b: raise ValueError('unbound normalized source character')
            if spans and spans[-1][1]==a: spans[-1][1]=b
            else: spans.append([a,b])
        occurrences[para]+=1
        binding=make_source_binding(chapter_id=ch_id,source_revision=revision,document_length=len(text),
            source_text=para,source_spans=spans,occurrence=occurrences[para],duplicate_count=counts[para])
        validate_source_binding(binding,para,document_text=text)
        segments.append(
            Segment(
                segment_id=f"{ch_id}-seg-{idx:03d}",
                source_text=para,
                source_binding=binding,
            )
        )
    return ParsedChapter(
        chapter_id=ch_id,
        source_path=str(path),
        chapter_label=chapter_label,
        segments=segments,
        source_revision=revision,
        parser_version='chapter-source-spans/1',
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
