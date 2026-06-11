"""Glossary entry model and state machine (FS-013).

Field set mirrors spec §7.8 / schemas/glossary.schema.json (13 required
fields). Two optional extension fields are store-managed and allowed by the
schema's additionalProperties:
    conflict  - bool flag set by mark_conflict() (spec §7.8 "标记冲突")
    deleted   - soft-delete marker (FS-013 forbids hard delete without force)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

CATEGORIES: tuple[str, ...] = (
    "person_name",
    "place_name",
    "organization_name",
    "skill_name",
    "item_name",
    "title",
    "race",
    "magic",
    "system_term",
    "game_term",
    "do_not_translate",
    "other",
)


class GlossaryError(Exception):
    """Base error for the glossary kernel."""


class EntryNotFoundError(GlossaryError):
    pass


class DuplicateEntryError(GlossaryError):
    pass


class LockedEntryError(GlossaryError):
    """Raised when a machine suggestion tries to modify a locked entry."""


class CategoryError(GlossaryError):
    pass


class StoreLockTimeoutError(GlossaryError):
    """Raised when the cross-process write lock cannot be acquired in time."""


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def validate_category(category: str) -> str:
    if category not in CATEGORIES:
        raise CategoryError(f"invalid category: {category!r} (must be one of {', '.join(CATEGORIES)})")
    return category


def validate_confidence(confidence: float | None) -> float | None:
    if confidence is None:
        return None
    value = float(confidence)
    if not 0.0 <= value <= 1.0:
        raise GlossaryError(f"confidence out of range [0,1]: {value}")
    return value


@dataclass
class GlossaryEntry:
    source_term: str
    target_term: str = ""
    reading: str | None = None
    category: str = "other"
    description: str | None = None
    first_seen_chapter: int | None = None
    confidence: float | None = None
    locked: bool = False
    approved_by_user: bool = False
    aliases: list[str] = field(default_factory=list)
    notes: str | None = None
    created_at: str = ""
    updated_at: str = ""
    # store-managed extension fields (schema additionalProperties: true)
    conflict: bool = False
    deleted: bool = False

    def __post_init__(self) -> None:
        if not self.source_term or not str(self.source_term).strip():
            raise GlossaryError("source_term must be a non-empty string")
        self.source_term = str(self.source_term)
        validate_category(self.category)
        self.confidence = validate_confidence(self.confidence)
        now = utc_now_iso()
        self.created_at = self.created_at or now
        self.updated_at = self.updated_at or now

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "GlossaryEntry":
        known = {f for f in cls.__dataclass_fields__}  # noqa: C416
        kwargs = {k: v for k, v in data.items() if k in known}
        kwargs.setdefault("aliases", [])
        kwargs["aliases"] = list(kwargs["aliases"] or [])
        kwargs.setdefault("conflict", bool(data.get("conflict", False)))
        kwargs.setdefault("deleted", bool(data.get("deleted", False)))
        return cls(**kwargs)

    def to_dict(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "source_term": self.source_term,
            "target_term": self.target_term,
            "reading": self.reading,
            "category": self.category,
            "description": self.description,
            "first_seen_chapter": self.first_seen_chapter,
            "confidence": self.confidence,
            "locked": self.locked,
            "approved_by_user": self.approved_by_user,
            "aliases": list(self.aliases),
            "notes": self.notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        # extension fields written only when set, keeping migrated/template
        # files byte-stable until these states are actually used
        if self.conflict:
            doc["conflict"] = True
        if self.deleted:
            doc["deleted"] = True
        return doc

    def touch(self) -> None:
        self.updated_at = utc_now_iso()
