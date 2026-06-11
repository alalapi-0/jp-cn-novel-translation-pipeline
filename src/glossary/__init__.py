"""Glossary kernel (FS-013): models + file-backed CRUD store.

Public API:
    from glossary import GlossaryStore, GlossaryEntry, CATEGORIES
"""

from .models import (
    CATEGORIES,
    CategoryError,
    DuplicateEntryError,
    EntryNotFoundError,
    GlossaryEntry,
    GlossaryError,
    LockedEntryError,
    StoreLockTimeoutError,
)
from .store import GlossaryStore

__all__ = [
    "CATEGORIES",
    "CategoryError",
    "DuplicateEntryError",
    "EntryNotFoundError",
    "GlossaryEntry",
    "GlossaryError",
    "GlossaryStore",
    "LockedEntryError",
    "StoreLockTimeoutError",
]
