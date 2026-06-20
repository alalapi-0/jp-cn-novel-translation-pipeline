"""Glossary import/export in CSV / YAML / JSON (FS-014).

Round-trip guarantee: export -> import -> entries compare equal (to_dict).
CSV nullable convention: empty cell == None for nullable fields
(reading / description / first_seen_chapter / confidence / notes);
target_term is always a plain string ("" allowed).

Import protection rules (spec §7.8 + FS-014 acceptance):
- locked entries are never changed by import; attempts are counted as
  conflicts in the report;
- approved_by_user entries are never silently overwritten: differing
  incoming data is skipped and counted (human resolves via store API).
"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

import yaml

from .models import GlossaryEntry, GlossaryError
from .store import GlossaryStore

FORMATS = ("csv", "yaml", "json")

_CSV_COLUMNS = [
    "source_term",
    "target_term",
    "reading",
    "category",
    "description",
    "first_seen_chapter",
    "confidence",
    "locked",
    "approved_by_user",
    "aliases",
    "notes",
    "created_at",
    "updated_at",
    "conflict",
    "deleted",
]

_ALIAS_SEP = "|"


class GlossaryIOError(GlossaryError):
    pass


def detect_format(path: Path | str) -> str:
    suffix = Path(path).suffix.lower().lstrip(".")
    fmt = {"yml": "yaml"}.get(suffix, suffix)
    if fmt not in FORMATS:
        raise GlossaryIOError(f"unsupported format: {Path(path).name} (use one of {FORMATS})")
    return fmt


# ---------------------------------------------------------------------------
# export
# ---------------------------------------------------------------------------


def _doc_from_entries(entries: list[GlossaryEntry]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "meta": {"description": "glossary export (FS-014)"},
        "entries": [e.to_dict() for e in entries],
    }


def _entry_to_csv_row(entry: GlossaryEntry) -> dict[str, str]:
    row: dict[str, str] = {}
    for col in _CSV_COLUMNS:
        if col == "aliases":
            row[col] = _ALIAS_SEP.join(entry.aliases)
        elif col in ("locked", "approved_by_user", "conflict", "deleted"):
            row[col] = "true" if getattr(entry, col) else "false"
        else:
            value = getattr(entry, col)
            row[col] = "" if value is None else str(value)
    return row


def export_glossary(
    store: GlossaryStore,
    path: Path | str,
    *,
    fmt: str | None = None,
    include_deleted: bool = False,
) -> int:
    """Write all entries to path in csv/yaml/json; returns exported count."""
    out = Path(path)
    fmt = fmt or detect_format(out)
    if fmt not in FORMATS:
        raise GlossaryIOError(f"unsupported format: {fmt}")
    entries = store.entries(include_deleted=include_deleted)
    out.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "yaml":
        out.write_text(
            yaml.safe_dump(_doc_from_entries(entries), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
    elif fmt == "json":
        out.write_text(
            json.dumps(_doc_from_entries(entries), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    else:  # csv
        with out.open("w", encoding="utf-8", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=_CSV_COLUMNS)
            writer.writeheader()
            for entry in entries:
                writer.writerow(_entry_to_csv_row(entry))
    return len(entries)


# ---------------------------------------------------------------------------
# import
# ---------------------------------------------------------------------------


def _csv_row_to_dict(row: dict[str, str]) -> dict[str, Any]:
    def _nullable(value: str | None) -> str | None:
        return None if value is None or value == "" else value

    def _bool(value: str | None) -> bool:
        return (value or "").strip().lower() in ("true", "1", "yes")

    data: dict[str, Any] = {
        "source_term": row.get("source_term") or "",
        "target_term": row.get("target_term") or "",
        "reading": _nullable(row.get("reading")),
        "category": row.get("category") or "other",
        "description": _nullable(row.get("description")),
        "notes": _nullable(row.get("notes")),
        "locked": _bool(row.get("locked")),
        "approved_by_user": _bool(row.get("approved_by_user")),
        "conflict": _bool(row.get("conflict")),
        "deleted": _bool(row.get("deleted")),
        "aliases": [a for a in (row.get("aliases") or "").split(_ALIAS_SEP) if a],
        "created_at": row.get("created_at") or "",
        "updated_at": row.get("updated_at") or "",
    }
    chapter = _nullable(row.get("first_seen_chapter"))
    data["first_seen_chapter"] = int(chapter) if chapter is not None else None
    confidence = _nullable(row.get("confidence"))
    data["confidence"] = float(confidence) if confidence is not None else None
    return data


def read_entries(path: Path | str, *, fmt: str | None = None) -> list[GlossaryEntry]:
    """Parse a csv/yaml/json glossary file into entries (no store side effects)."""
    src = Path(path)
    if not src.is_file():
        raise GlossaryIOError(f"import file not found: {src}")
    fmt = fmt or detect_format(src)
    raw_entries: Iterable[dict[str, Any]]
    if fmt == "yaml":
        doc = yaml.safe_load(src.read_text(encoding="utf-8"))
        raw_entries = (doc or {}).get("entries") or []
    elif fmt == "json":
        doc = json.loads(src.read_text(encoding="utf-8"))
        raw_entries = (doc or {}).get("entries") or []
    else:  # csv
        with src.open("r", encoding="utf-8", newline="") as handle:
            raw_entries = [_csv_row_to_dict(row) for row in csv.DictReader(handle)]
    entries = []
    for raw in raw_entries:
        if not isinstance(raw, dict):
            raise GlossaryIOError(f"malformed entry (not a mapping) in {src.name}")
        entries.append(GlossaryEntry.from_dict(raw))
    return entries


_COMPARABLE_FIELDS = (
    "target_term",
    "reading",
    "category",
    "description",
    "first_seen_chapter",
    "confidence",
    "aliases",
    "notes",
)


def _payload_differs(existing: GlossaryEntry, incoming: GlossaryEntry) -> bool:
    return any(getattr(existing, f) != getattr(incoming, f) for f in _COMPARABLE_FIELDS)


@dataclass
class ImportReport:
    total: int = 0
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    skipped_locked: int = 0
    skipped_approved: int = 0
    conflicts: list[dict[str, str]] = field(default_factory=list)

    @property
    def conflict_count(self) -> int:
        return len(self.conflicts)

    def to_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "added": self.added,
            "updated": self.updated,
            "unchanged": self.unchanged,
            "skipped_locked": self.skipped_locked,
            "skipped_approved": self.skipped_approved,
            "conflict_count": self.conflict_count,
            "conflicts": list(self.conflicts),
        }


def import_glossary(
    store: GlossaryStore,
    path: Path | str,
    *,
    fmt: str | None = None,
) -> ImportReport:
    """Merge entries from file into store, honoring locked/approved protection."""
    incoming_entries = read_entries(path, fmt=fmt)
    report = ImportReport(total=len(incoming_entries))
    for incoming in incoming_entries:
        try:
            existing = store.get(incoming.source_term, include_deleted=True)
        except GlossaryError:
            existing = None
        if existing is None:
            store.add(incoming, preserve_audit_fields=True)
            report.added += 1
            continue
        if not _payload_differs(existing, incoming):
            report.unchanged += 1
            continue
        if existing.locked:
            # locked terms stay untouched; difference recorded as a conflict
            report.skipped_locked += 1
            report.conflicts.append(
                {
                    "source_term": existing.source_term,
                    "reason": "locked",
                    "incoming_target": incoming.target_term,
                    "kept_target": existing.target_term,
                }
            )
            continue
        if existing.approved_by_user:
            # never silently overwrite human-approved terms
            report.skipped_approved += 1
            report.conflicts.append(
                {
                    "source_term": existing.source_term,
                    "reason": "approved_by_user",
                    "incoming_target": incoming.target_term,
                    "kept_target": existing.target_term,
                }
            )
            continue
        store.update(
            incoming.source_term,
            {f: getattr(incoming, f) for f in _COMPARABLE_FIELDS},
        )
        report.updated += 1
    return report
