"""Batch-scoped asset context from configs assets (FS-016, spec §22).

Selects ONLY the glossary entries and character notes hit by the current
batch's source texts - never the full glossary / character profile / world
bible. Output is a compact text block for prompt injection plus statistics
for budget assertions.

Data sources (real data lives under workspace/configs/, gitignored):
- glossary:          workspace/configs/glossary.yaml   (FS-012/013)
- character profile: workspace/configs/character_profile.yaml
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_GLOSSARY_PATH = _REPO_ROOT / "workspace" / "configs" / "glossary.yaml"
DEFAULT_CHARACTER_PATH = _REPO_ROOT / "workspace" / "configs" / "character_profile.yaml"

DEFAULT_MAX_GLOSSARY_TERMS = 24
DEFAULT_MAX_CHARACTERS = 6
DEFAULT_CHAR_BUDGET = 2000  # characters as a cheap token proxy for CJK text

# (path, size, mtime) -> parsed doc; cheap process-local cache
_DOC_CACHE: dict[tuple[str, int, int], Any] = {}


def _load_yaml_cached(path: Path) -> Any:
    if not path.is_file():
        return None
    stat = path.stat()
    key = (str(path), stat.st_size, int(stat.st_mtime))
    if key not in _DOC_CACHE:
        _DOC_CACHE.clear()  # keep at most one generation per file set
        _DOC_CACHE[key] = yaml.safe_load(path.read_text(encoding="utf-8"))
    return _DOC_CACHE[key]


@dataclass
class ConfigsAssetContext:
    text: str = ""
    glossary_terms: list[str] = field(default_factory=list)
    characters: list[str] = field(default_factory=list)
    char_count: int = 0
    truncated: bool = False

    @property
    def empty(self) -> bool:
        return not self.text


def _glossary_entries(path: Path) -> list[dict[str, Any]]:
    doc = _load_yaml_cached(path)
    if not isinstance(doc, dict):
        return []
    entries = doc.get("entries")
    return [e for e in entries if isinstance(e, dict)] if isinstance(entries, list) else []


def _characters(path: Path) -> list[dict[str, Any]]:
    doc = _load_yaml_cached(path)
    if not isinstance(doc, dict):
        return []
    chars = doc.get("characters")
    return [c for c in chars if isinstance(c, dict)] if isinstance(chars, list) else []


def _entry_hit(entry: dict[str, Any], haystack: str) -> bool:
    source = str(entry.get("source_term") or "")
    if source and source in haystack:
        return True
    return any(a and str(a) in haystack for a in entry.get("aliases") or [])


def _character_hit(char: dict[str, Any], haystack: str) -> bool:
    name = str(char.get("name") or "")
    if name and name in haystack:
        return True
    return any(a and str(a) in haystack for a in char.get("aliases") or [])


def _glossary_line(entry: dict[str, Any]) -> str:
    source = str(entry.get("source_term") or "")
    target = str(entry.get("target_term") or "")
    flags: list[str] = []
    if entry.get("locked"):
        flags.append("locked")
    if entry.get("approved_by_user"):
        flags.append("approved")
    suffix = f" [{','.join(flags)}]" if flags else ""
    if target:
        return f"- {source} => {target}{suffix}"
    return f"- {source} (译名未定，保持全书一致){suffix}"


def _character_line(char: dict[str, Any]) -> str:
    name = str(char.get("name") or "")
    target = str(char.get("target_name") or "")
    bits: list[str] = []
    if char.get("first_person"):
        bits.append(f"一人称={char['first_person']}")
    tics = [t for t in char.get("speech_tics") or [] if t]
    if tics:
        bits.append(f"口癖={'、'.join(tics[:2])}")
    if char.get("honorific_style"):
        bits.append(f"敬语={char['honorific_style']}")
    addresses = [
        f"{a.get('to')}→{a.get('address')}"
        for a in (char.get("address_map") or [])[:2]
        if isinstance(a, dict) and a.get("to") and a.get("address")
    ]
    if addresses:
        bits.append(f"称呼: {'; '.join(addresses)}")
    forbidden = [f for f in char.get("forbidden") or [] if f]
    if forbidden:
        bits.append(f"禁止: {forbidden[0]}")
    label = f"{name}（{target}）" if target else name
    return f"- {label}: {'; '.join(bits)}" if bits else f"- {label}"


def _entry_priority(entry: dict[str, Any]) -> tuple[int, int]:
    """locked first, then approved, then the rest (stable within groups)."""
    return (0 if entry.get("locked") else 1, 0 if entry.get("approved_by_user") else 1)


def build_configs_asset_context(
    batch_source_texts: list[str],
    *,
    glossary_path: Path = DEFAULT_GLOSSARY_PATH,
    character_path: Path = DEFAULT_CHARACTER_PATH,
    max_glossary_terms: int = DEFAULT_MAX_GLOSSARY_TERMS,
    max_characters: int = DEFAULT_MAX_CHARACTERS,
    char_budget: int = DEFAULT_CHAR_BUDGET,
) -> ConfigsAssetContext:
    """Build the batch-hit subset context (spec §22: never full assets)."""
    result = ConfigsAssetContext()
    if not batch_source_texts:
        return result
    haystack = "\n".join(batch_source_texts)

    hit_entries = [e for e in _glossary_entries(glossary_path) if not e.get("deleted") and _entry_hit(e, haystack)]
    hit_entries.sort(key=_entry_priority)
    hit_chars = [c for c in _characters(character_path) if _character_hit(c, haystack)]

    lines: list[str] = []
    used = 0
    truncated = False

    def _try_add(line: str) -> bool:
        nonlocal used, truncated
        cost = len(line) + 1
        if used + cost > char_budget:
            truncated = True
            return False
        lines.append(line)
        used += cost
        return True

    if hit_entries:
        _try_add("Glossary (batch hits; locked terms must be used verbatim):")
        for entry in hit_entries[:max_glossary_terms]:
            if not _try_add(_glossary_line(entry)):
                break
            result.glossary_terms.append(str(entry.get("source_term") or ""))
        if len(hit_entries) > max_glossary_terms:
            truncated = True

    if hit_chars:
        _try_add("Character notes (batch hits):")
        for char in hit_chars[:max_characters]:
            if not _try_add(_character_line(char)):
                break
            result.characters.append(str(char.get("name") or ""))
        if len(hit_chars) > max_characters:
            truncated = True

    result.text = "\n".join(lines) if (result.glossary_terms or result.characters) else ""
    result.char_count = len(result.text)
    result.truncated = truncated
    return result
