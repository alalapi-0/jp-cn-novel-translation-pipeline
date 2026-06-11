"""Glossary kernel (FS-013): models + file-backed CRUD store.

Public API:
    from glossary import GlossaryStore, GlossaryEntry, CATEGORIES
"""

from .io import (
    FORMATS,
    GlossaryIOError,
    ImportReport,
    detect_format,
    export_glossary,
    import_glossary,
    read_entries,
)
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
    "FORMATS",
    "GlossaryEntry",
    "GlossaryError",
    "GlossaryIOError",
    "GlossaryStore",
    "ImportReport",
    "LockedEntryError",
    "StoreLockTimeoutError",
    "detect_format",
    "export_glossary",
    "import_glossary",
    "read_entries",
]
