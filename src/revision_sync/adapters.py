"""Read-only adapters for the repository's chapter-oriented revision inputs."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any, Iterable

from translation.chapter_parser import parse_chapter_file

_SOURCE_FILE_RE = re.compile(r"^0*(\d+)-")
_REVISION_FILE_RE = re.compile(r"^0*(\d+)_")
_H1_RE = re.compile(r"^#\s+(.+?)\s*$")
_CHAPTER_NUMBER_RE = re.compile(r"(?:第\s*)?0*(\d+)\s*(?:章|话|話|[.．、:_-]|\s|$)")


def _paragraphs(lines: Iterable[str]) -> list[str]:
    body = "\n".join(lines).strip()
    if not body:
        return []
    blocks = [part.strip() for part in re.split(r"\n\s*\n+", body) if part.strip()]
    nonblank = [line.strip() for line in body.splitlines() if line.strip()]
    # Match the existing source parser's handling of one-paragraph-per-line prose.
    if len(blocks) < max(8, len(nonblank) // 3):
        return nonblank
    return blocks


def _number_from_heading(value: str) -> int:
    match = _CHAPTER_NUMBER_RE.search(value)
    if not match:
        raise ValueError(f"canonical H1 does not contain a chapter number: {value!r}")
    return int(match.group(1))


def parse_source_dir(source_dir: Path, chapter_start: int, chapter_end: int) -> dict[int, list[dict[str, Any]]]:
    by_number: dict[int, Path] = {}
    for path in sorted(source_dir.iterdir()):
        match = _SOURCE_FILE_RE.match(path.name)
        if path.is_file() and match and path.suffix.lower() in {".md", ".txt"}:
            number = int(match.group(1))
            if chapter_start <= number <= chapter_end:
                if number in by_number:
                    raise ValueError(f"duplicate source chapter {number}")
                by_number[number] = path
    _require_coverage(by_number, chapter_start, chapter_end, "source")
    result: dict[int, list[dict[str, Any]]] = {}
    for number, path in by_number.items():
        parsed = parse_chapter_file(path)
        result[number] = [
            {"chapter_id": f"ch-{number}", "segment_id": segment.segment_id, "source_text": segment.source_text}
            for segment in parsed.segments
        ]
    return result


def parse_canonical_full_volume(path: Path, chapter_start: int, chapter_end: int) -> dict[int, list[str]]:
    chapters: dict[int, list[str]] = {}
    active: int | None = None
    body: list[str] = []

    def flush() -> None:
        nonlocal body
        if active is not None and chapter_start <= active <= chapter_end:
            if active in chapters:
                raise ValueError(f"duplicate canonical chapter {active}")
            chapters[active] = _paragraphs(body)
        body = []

    for line in path.read_text(encoding="utf-8").splitlines():
        heading = _H1_RE.match(line)
        if heading:
            flush()
            active = _number_from_heading(heading.group(1))
        elif active is not None:
            body.append(line)
    flush()
    _require_coverage(chapters, chapter_start, chapter_end, "canonical")
    return chapters


def parse_revision_dir(revision_dir: Path, chapter_start: int, chapter_end: int) -> dict[int, list[dict[str, Any]]]:
    files: dict[int, Path] = {}
    for path in sorted(revision_dir.iterdir()):
        match = _REVISION_FILE_RE.match(path.name)
        if path.is_file() and match and path.suffix.lower() in {".md", ".txt"}:
            number = int(match.group(1))
            if chapter_start <= number <= chapter_end:
                if number in files:
                    raise ValueError(f"duplicate revision chapter {number}")
                files[number] = path
    _require_coverage(files, chapter_start, chapter_end, "revision")
    result: dict[int, list[dict[str, Any]]] = {}
    for number, path in files.items():
        lines = path.read_text(encoding="utf-8").splitlines()
        first_nonblank = next((index for index, line in enumerate(lines) if line.strip()), None)
        body = [] if first_nonblank is None else lines[first_nonblank + 1 :]
        result[number] = [
            {"chapter_id": f"ch-{number}", "target_text": text}
            for text in _paragraphs(body)
        ]
    return result


def load_repository_inputs(
    source_dir: Path,
    canonical_full_volume: Path,
    revision_dir: Path,
    chapter_start: int,
    chapter_end: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Load actual input shapes and fail closed on canonical/source count mismatch."""
    if chapter_start < 1 or chapter_end < chapter_start:
        raise ValueError("invalid chapter range")
    source = parse_source_dir(source_dir, chapter_start, chapter_end)
    canonical = parse_canonical_full_volume(canonical_full_volume, chapter_start, chapter_end)
    revisions = parse_revision_dir(revision_dir, chapter_start, chapter_end)
    canonical_records: list[dict[str, Any]] = []
    revision_records: list[dict[str, Any]] = []
    for number in range(chapter_start, chapter_end + 1):
        source_records, targets = source[number], canonical[number]
        if len(source_records) != len(targets):
            raise ValueError(
                f"chapter {number} canonical/source paragraph mismatch: {len(targets)} != {len(source_records)}"
            )
        for source_record, target in zip(source_records, targets):
            canonical_records.append({**source_record, "target_text": target})
        revision_records.extend(revisions[number])
    return canonical_records, revision_records


def aggregate_input_hashes(paths: Iterable[Path]) -> str:
    digest = hashlib.sha256()
    files: list[Path] = []
    for path in paths:
        files.extend(sorted(item for item in path.rglob("*") if item.is_file()) if path.is_dir() else [path])
    for path in sorted(files, key=lambda item: str(item)):
        digest.update(str(path.name).encode("utf-8"))
        digest.update(b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _require_coverage(mapping: dict[int, Any], start: int, end: int, label: str) -> None:
    missing = [number for number in range(start, end + 1) if number not in mapping]
    if missing:
        raise ValueError(f"missing {label} chapters: {missing}")
