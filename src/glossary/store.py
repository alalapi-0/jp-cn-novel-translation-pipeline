"""File-backed glossary CRUD store with cross-process write lock (FS-013).

Backend: YAML document shaped like schemas/glossary.schema.json
(schema_version / meta / entries). Default path is the FS-012 migrated real
data file workspace/configs/glossary.yaml; tests use tmp paths.

Concurrency: every mutation runs inside _write_lock() which combines a
process-local threading.Lock with an O_CREAT|O_EXCL lock file (same pattern
as scheduler.control). Writes are atomic (tmp file + os.replace).

Machine-vs-human protection: mutating calls take by_machine; locked entries
reject machine modifications with LockedEntryError (spec: locked terms must
never be overwritten by machine suggestions).
"""

from __future__ import annotations

import os
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

import yaml

from .models import (
    DuplicateEntryError,
    EntryNotFoundError,
    GlossaryEntry,
    GlossaryError,
    LockedEntryError,
    StoreLockTimeoutError,
    utc_now_iso,
    validate_category,
)

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
DEFAULT_GLOSSARY_PATH = _REPO_ROOT / "workspace" / "configs" / "glossary.yaml"

# One threading.Lock per store path (process-local layer of the write lock).
_THREAD_LOCKS: dict[str, threading.Lock] = {}
_THREAD_LOCKS_GUARD = threading.Lock()


def _thread_lock_for(path: Path) -> threading.Lock:
    key = str(path)
    with _THREAD_LOCKS_GUARD:
        if key not in _THREAD_LOCKS:
            _THREAD_LOCKS[key] = threading.Lock()
        return _THREAD_LOCKS[key]


class GlossaryStore:
    def __init__(
        self,
        path: Path | str = DEFAULT_GLOSSARY_PATH,
        *,
        lock_timeout_s: float = 5.0,
    ) -> None:
        self.path = Path(path)
        self.lock_timeout_s = float(lock_timeout_s)

    # ------------------------------------------------------------------
    # locking + persistence
    # ------------------------------------------------------------------

    @property
    def _lock_path(self) -> Path:
        return self.path.with_suffix(self.path.suffix + ".lock")

    @contextmanager
    def _write_lock(self) -> Iterator[None]:
        thread_lock = _thread_lock_for(self.path)
        if not thread_lock.acquire(timeout=self.lock_timeout_s):
            raise StoreLockTimeoutError(f"thread lock timeout on {self.path}")
        fd: int | None = None
        try:
            deadline = time.monotonic() + self.lock_timeout_s
            self._lock_path.parent.mkdir(parents=True, exist_ok=True)
            while True:
                try:
                    fd = os.open(str(self._lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                    os.write(fd, str(os.getpid()).encode("ascii"))
                    break
                except FileExistsError:
                    if time.monotonic() >= deadline:
                        raise StoreLockTimeoutError(
                            f"write lock held too long: {self._lock_path}"
                        ) from None
                    time.sleep(0.02)
            yield
        finally:
            if fd is not None:
                os.close(fd)
                self._lock_path.unlink(missing_ok=True)
            thread_lock.release()

    def _empty_doc(self) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "meta": {
                "project": "real",
                "description": "glossary store (FS-013); local only, never commit real terms",
                "language_pair": "ja-zh",
            },
            "entries": [],
        }

    def load_doc(self) -> dict[str, Any]:
        if not self.path.is_file():
            return self._empty_doc()
        data = yaml.safe_load(self.path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise GlossaryError(f"glossary file malformed (not a mapping): {self.path}")
        data.setdefault("schema_version", 1)
        data.setdefault("entries", [])
        if not isinstance(data["entries"], list):
            raise GlossaryError(f"glossary entries malformed (not a list): {self.path}")
        return data

    def _save_doc(self, doc: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        tmp.write_text(
            yaml.safe_dump(doc, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        os.replace(tmp, self.path)

    # ------------------------------------------------------------------
    # read API
    # ------------------------------------------------------------------

    def entries(self, *, include_deleted: bool = False) -> list[GlossaryEntry]:
        doc = self.load_doc()
        loaded = [GlossaryEntry.from_dict(e) for e in doc["entries"] if isinstance(e, dict)]
        if include_deleted:
            return loaded
        return [e for e in loaded if not e.deleted]

    def get(self, source_term: str, *, include_deleted: bool = False) -> GlossaryEntry:
        for entry in self.entries(include_deleted=True):
            if entry.source_term == source_term:
                if entry.deleted and not include_deleted:
                    raise EntryNotFoundError(f"entry soft-deleted: {source_term!r}")
                return entry
        raise EntryNotFoundError(f"entry not found: {source_term!r}")

    def search(
        self,
        query: str = "",
        *,
        category: str | None = None,
        locked: bool | None = None,
        approved_by_user: bool | None = None,
        conflict: bool | None = None,
        include_deleted: bool = False,
    ) -> list[GlossaryEntry]:
        """Substring search over source/target/aliases/notes + state filters."""
        if category is not None:
            validate_category(category)
        needle = (query or "").strip().lower()
        results: list[GlossaryEntry] = []
        for entry in self.entries(include_deleted=include_deleted):
            if category is not None and entry.category != category:
                continue
            if locked is not None and entry.locked != locked:
                continue
            if approved_by_user is not None and entry.approved_by_user != approved_by_user:
                continue
            if conflict is not None and entry.conflict != conflict:
                continue
            if needle:
                haystack = " ".join(
                    [
                        entry.source_term,
                        entry.target_term or "",
                        " ".join(entry.aliases),
                        entry.notes or "",
                        entry.description or "",
                    ]
                ).lower()
                if needle not in haystack:
                    continue
            results.append(entry)
        return results

    # ------------------------------------------------------------------
    # write API
    # ------------------------------------------------------------------

    def add(
        self,
        entry: GlossaryEntry | dict[str, Any],
        *,
        preserve_audit_fields: bool = False,
    ) -> GlossaryEntry:
        """Insert a new entry; source_term must be unique among active entries.

        Adding over a soft-deleted term replaces the tombstone with the new
        entry (the deleted record is superseded, not resurrected). Normal
        interactive adds refresh updated_at; import/migration callers can
        preserve exported audit fields for lossless roundtrips.
        """
        new_entry = entry if isinstance(entry, GlossaryEntry) else GlossaryEntry.from_dict(entry)
        with self._write_lock():
            doc = self.load_doc()
            kept: list[dict[str, Any]] = []
            for raw in doc["entries"]:
                if not isinstance(raw, dict):
                    kept.append(raw)
                    continue
                if raw.get("source_term") == new_entry.source_term:
                    if not raw.get("deleted"):
                        raise DuplicateEntryError(
                            f"entry already exists: {new_entry.source_term!r}"
                        )
                    continue  # drop tombstone, superseded by the new entry
                kept.append(raw)
            if not preserve_audit_fields:
                new_entry.touch()
            kept.append(new_entry.to_dict())
            doc["entries"] = kept
            self._save_doc(doc)
        return new_entry

    def _mutate(
        self,
        source_term: str,
        *,
        by_machine: bool,
        allow_deleted: bool = False,
        mutator,
    ) -> GlossaryEntry:
        with self._write_lock():
            doc = self.load_doc()
            for idx, raw in enumerate(doc["entries"]):
                if not isinstance(raw, dict) or raw.get("source_term") != source_term:
                    continue
                entry = GlossaryEntry.from_dict(raw)
                if entry.deleted and not allow_deleted:
                    raise EntryNotFoundError(f"entry soft-deleted: {source_term!r}")
                if entry.locked and by_machine:
                    raise LockedEntryError(
                        f"locked entry cannot be modified by machine suggestion: {source_term!r}"
                    )
                mutator(entry)
                entry.touch()
                doc["entries"][idx] = entry.to_dict()
                self._save_doc(doc)
                return entry
            raise EntryNotFoundError(f"entry not found: {source_term!r}")

    # mutable business fields; identity/audit fields stay store-managed
    _UPDATABLE_FIELDS = {
        "target_term",
        "reading",
        "category",
        "description",
        "first_seen_chapter",
        "confidence",
        "aliases",
        "notes",
    }

    def update(
        self,
        source_term: str,
        updates: dict[str, Any],
        *,
        by_machine: bool = False,
    ) -> GlossaryEntry:
        unknown = set(updates) - self._UPDATABLE_FIELDS
        if unknown:
            raise GlossaryError(
                f"non-updatable field(s): {sorted(unknown)} "
                f"(use lock/unlock/approve/mark_conflict/delete for state changes)"
            )

        def _apply(entry: GlossaryEntry) -> None:
            data = entry.to_dict()
            data.update(updates)
            data["deleted"] = entry.deleted
            data["conflict"] = entry.conflict
            refreshed = GlossaryEntry.from_dict(data)  # re-validates category/confidence
            for fname in self._UPDATABLE_FIELDS:
                setattr(entry, fname, getattr(refreshed, fname))

        return self._mutate(source_term, by_machine=by_machine, mutator=_apply)

    def delete(self, source_term: str, *, force: bool = False, by_machine: bool = False) -> bool:
        """Soft-delete by default; force=True removes the record physically."""
        if not force:
            self._mutate(
                source_term,
                by_machine=by_machine,
                mutator=lambda e: setattr(e, "deleted", True),
            )
            return True
        with self._write_lock():
            doc = self.load_doc()
            for idx, raw in enumerate(doc["entries"]):
                if isinstance(raw, dict) and raw.get("source_term") == source_term:
                    entry = GlossaryEntry.from_dict(raw)
                    if entry.locked and by_machine:
                        raise LockedEntryError(
                            f"locked entry cannot be force-deleted by machine: {source_term!r}"
                        )
                    del doc["entries"][idx]
                    self._save_doc(doc)
                    return True
            raise EntryNotFoundError(f"entry not found: {source_term!r}")

    def restore(self, source_term: str) -> GlossaryEntry:
        """Bring a soft-deleted entry back (human operation)."""
        return self._mutate(
            source_term,
            by_machine=False,
            allow_deleted=True,
            mutator=lambda e: setattr(e, "deleted", False),
        )

    # ------------------------------------------------------------------
    # state machine: locked / approved_by_user / conflict
    # ------------------------------------------------------------------

    def lock(self, source_term: str) -> GlossaryEntry:
        return self._mutate(
            source_term, by_machine=False, mutator=lambda e: setattr(e, "locked", True)
        )

    def unlock(self, source_term: str) -> GlossaryEntry:
        """Unlock is always a human decision (machine may never unlock)."""
        return self._mutate(
            source_term, by_machine=False, mutator=lambda e: setattr(e, "locked", False)
        )

    def approve(self, source_term: str) -> GlossaryEntry:
        """Mark human-confirmed; clears any machine-conflict flag."""

        def _apply(entry: GlossaryEntry) -> None:
            entry.approved_by_user = True
            entry.conflict = False

        return self._mutate(source_term, by_machine=False, mutator=_apply)

    def unapprove(self, source_term: str) -> GlossaryEntry:
        return self._mutate(
            source_term,
            by_machine=False,
            mutator=lambda e: setattr(e, "approved_by_user", False),
        )

    def mark_conflict(self, source_term: str, note: str | None = None) -> GlossaryEntry:
        """Flag an entry as conflicted (allowed for machine even when locked:
        flagging is not an overwrite of the locked translation)."""

        def _apply(entry: GlossaryEntry) -> None:
            entry.conflict = True
            if note:
                stamp = f"conflict: {note} ({utc_now_iso()})"
                entry.notes = stamp if not entry.notes else f"{entry.notes}; {stamp}"

        # by_machine=False on purpose: conflict flagging never rewrites the
        # locked target_term, so the locked-protection does not apply.
        return self._mutate(source_term, by_machine=False, mutator=_apply)

    def suggest(self, source_term: str, target_term: str, *, confidence: float | None = None) -> GlossaryEntry:
        """Machine suggestion entry point: update target on unlocked entries,
        raise LockedEntryError on locked ones (never silently overwrite)."""
        updates: dict[str, Any] = {"target_term": target_term}
        if confidence is not None:
            updates["confidence"] = confidence
        return self.update(source_term, updates, by_machine=True)
