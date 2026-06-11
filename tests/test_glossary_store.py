"""Tests for FS-013: src/glossary kernel (models + CRUD store).

Acceptance (docs/final_state_round_task_list.md FS-013):
- every CRUD operation tested;
- locked terms cannot be overwritten by machine suggestions;
- updated_at auto-maintained;
- concurrent writes protected by file lock;
- delete is soft by default, physical only with explicit force.

Fixtures use fictional sample terms only.
"""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from glossary import (  # noqa: E402
    CATEGORIES,
    CategoryError,
    DuplicateEntryError,
    EntryNotFoundError,
    GlossaryEntry,
    GlossaryError,
    GlossaryStore,
    LockedEntryError,
)


@pytest.fixture()
def store(tmp_path) -> GlossaryStore:
    return GlossaryStore(tmp_path / "glossary.yaml")


@pytest.fixture()
def seeded(store: GlossaryStore) -> GlossaryStore:
    store.add(
        {
            "source_term": "サンプル王国",
            "target_term": "示例王国",
            "category": "place_name",
            "aliases": ["サンプル国"],
        }
    )
    store.add(
        {
            "source_term": "サンプル・タロウ",
            "target_term": "示例太郎",
            "category": "person_name",
        }
    )
    return store


# ---------------------------------------------------------------------------
# models
# ---------------------------------------------------------------------------


def test_categories_match_schema():
    schema = json.loads((REPO_ROOT / "schemas" / "glossary.schema.json").read_text(encoding="utf-8"))
    enum = schema["definitions"]["glossary_entry"]["properties"]["category"]["enum"]
    assert set(CATEGORIES) == set(enum) and len(CATEGORIES) == 12


def test_entry_requires_source_term():
    with pytest.raises(GlossaryError):
        GlossaryEntry(source_term="")


def test_entry_invalid_category_rejected():
    with pytest.raises(CategoryError):
        GlossaryEntry(source_term="サンプル", category="nope")


def test_entry_confidence_range():
    with pytest.raises(GlossaryError):
        GlossaryEntry(source_term="サンプル", confidence=1.2)


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def test_add_and_get(seeded: GlossaryStore):
    entry = seeded.get("サンプル王国")
    assert entry.target_term == "示例王国"
    assert entry.created_at and entry.updated_at


def test_add_duplicate_rejected(seeded: GlossaryStore):
    with pytest.raises(DuplicateEntryError):
        seeded.add({"source_term": "サンプル王国", "target_term": "другое"})


def test_get_missing_raises(store: GlossaryStore):
    with pytest.raises(EntryNotFoundError):
        store.get("サンプル不存在")


def test_update_field_and_auto_updated_at(seeded: GlossaryStore):
    before = seeded.get("サンプル王国")
    entry = seeded.update("サンプル王国", {"target_term": "示例皇国"})
    assert entry.target_term == "示例皇国"
    assert entry.updated_at >= before.updated_at
    assert entry.created_at == before.created_at


def test_update_rejects_unknown_or_protected_fields(seeded: GlossaryStore):
    with pytest.raises(GlossaryError):
        seeded.update("サンプル王国", {"locked": True})
    with pytest.raises(GlossaryError):
        seeded.update("サンプル王国", {"created_at": "2020-01-01T00:00:00Z"})


def test_update_validates_category(seeded: GlossaryStore):
    with pytest.raises(CategoryError):
        seeded.update("サンプル王国", {"category": "bogus"})
    entry = seeded.update("サンプル王国", {"category": "organization_name"})
    assert entry.category == "organization_name"


def test_soft_delete_then_restore(seeded: GlossaryStore):
    assert seeded.delete("サンプル王国") is True
    with pytest.raises(EntryNotFoundError):
        seeded.get("サンプル王国")
    tombstone = seeded.get("サンプル王国", include_deleted=True)
    assert tombstone.deleted is True
    restored = seeded.restore("サンプル王国")
    assert restored.deleted is False
    assert seeded.get("サンプル王国").target_term == "示例王国"


def test_force_delete_removes_record(seeded: GlossaryStore):
    seeded.delete("サンプル王国", force=True)
    with pytest.raises(EntryNotFoundError):
        seeded.get("サンプル王国", include_deleted=True)
    raw = yaml.safe_load(seeded.path.read_text(encoding="utf-8"))
    assert all(e["source_term"] != "サンプル王国" for e in raw["entries"])


def test_add_over_tombstone_supersedes(seeded: GlossaryStore):
    seeded.delete("サンプル王国")  # soft
    fresh = seeded.add({"source_term": "サンプル王国", "target_term": "示例新王国", "category": "place_name"})
    assert fresh.target_term == "示例新王国"
    assert seeded.get("サンプル王国").deleted is False
    raw = yaml.safe_load(seeded.path.read_text(encoding="utf-8"))
    assert sum(1 for e in raw["entries"] if e["source_term"] == "サンプル王国") == 1


# ---------------------------------------------------------------------------
# locked / approved / conflict state machine
# ---------------------------------------------------------------------------


def test_locked_blocks_machine_suggestion(seeded: GlossaryStore):
    seeded.lock("サンプル・タロウ")
    with pytest.raises(LockedEntryError):
        seeded.suggest("サンプル・タロウ", "机器译名")
    assert seeded.get("サンプル・タロウ").target_term == "示例太郎"  # unchanged


def test_locked_blocks_machine_update_and_force_delete(seeded: GlossaryStore):
    seeded.lock("サンプル・タロウ")
    with pytest.raises(LockedEntryError):
        seeded.update("サンプル・タロウ", {"target_term": "机器改名"}, by_machine=True)
    with pytest.raises(LockedEntryError):
        seeded.delete("サンプル・タロウ", force=True, by_machine=True)


def test_locked_allows_human_edit_and_unlock(seeded: GlossaryStore):
    seeded.lock("サンプル・タロウ")
    entry = seeded.update("サンプル・タロウ", {"target_term": "示例太郎（人工）"})
    assert entry.target_term == "示例太郎（人工）"
    seeded.unlock("サンプル・タロウ")
    entry = seeded.suggest("サンプル・タロウ", "示例太郎v2", confidence=0.8)
    assert entry.target_term == "示例太郎v2"
    assert entry.confidence == 0.8


def test_machine_suggestion_updates_unlocked(seeded: GlossaryStore):
    entry = seeded.suggest("サンプル王国", "示例王国v2", confidence=0.7)
    assert entry.target_term == "示例王国v2"


def test_approve_and_conflict_flow(seeded: GlossaryStore):
    seeded.mark_conflict("サンプル王国", note="同源多译候选")
    entry = seeded.get("サンプル王国")
    assert entry.conflict is True
    assert entry.notes and "conflict" in entry.notes
    approved = seeded.approve("サンプル王国")
    assert approved.approved_by_user is True
    assert approved.conflict is False  # approval resolves the conflict flag
    assert seeded.unapprove("サンプル王国").approved_by_user is False


def test_conflict_flag_allowed_on_locked_entry(seeded: GlossaryStore):
    seeded.lock("サンプル・タロウ")
    entry = seeded.mark_conflict("サンプル・タロウ", note="机器另一候选")
    assert entry.conflict is True
    assert entry.target_term == "示例太郎"  # translation untouched


# ---------------------------------------------------------------------------
# search / categories
# ---------------------------------------------------------------------------


def test_search_by_substring_and_alias(seeded: GlossaryStore):
    assert len(seeded.search("王国")) == 1
    assert len(seeded.search("サンプル国")) == 1  # alias hit
    assert len(seeded.search("タロウ")) == 1
    assert seeded.search("不存在词") == []


def test_search_filters(seeded: GlossaryStore):
    seeded.lock("サンプル・タロウ")
    assert {e.source_term for e in seeded.search(category="person_name")} == {"サンプル・タロウ"}
    assert {e.source_term for e in seeded.search(locked=True)} == {"サンプル・タロウ"}
    seeded.mark_conflict("サンプル王国")
    assert {e.source_term for e in seeded.search(conflict=True)} == {"サンプル王国"}
    with pytest.raises(CategoryError):
        seeded.search(category="bad_category")


def test_search_excludes_deleted_by_default(seeded: GlossaryStore):
    seeded.delete("サンプル王国")
    assert seeded.search("王国") == []
    assert len(seeded.search("王国", include_deleted=True)) == 1


# ---------------------------------------------------------------------------
# concurrency / persistence
# ---------------------------------------------------------------------------


def test_concurrent_adds_no_loss(store: GlossaryStore):
    errors: list[Exception] = []

    def _worker(n: int) -> None:
        try:
            store.add({"source_term": f"サンプル並行{n}", "target_term": f"示例并发{n}"})
        except Exception as exc:  # noqa: BLE001
            errors.append(exc)

    threads = [threading.Thread(target=_worker, args=(i,)) for i in range(30)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors
    assert len(store.entries()) == 30


def test_file_lock_blocks_second_writer(store: GlossaryStore, tmp_path):
    """Simulate another process holding the lock file: writer must time out."""
    store.add({"source_term": "サンプル先行", "target_term": "示例先行"})
    lock_path = store.path.with_suffix(store.path.suffix + ".lock")
    lock_path.write_text("99999999", encoding="utf-8")  # foreign holder
    fast = GlossaryStore(store.path, lock_timeout_s=0.2)
    from glossary import StoreLockTimeoutError

    with pytest.raises(StoreLockTimeoutError):
        fast.add({"source_term": "サンプル受阻", "target_term": "示例受阻"})
    lock_path.unlink()
    fast.add({"source_term": "サンプル受阻", "target_term": "示例受阻"})  # recovers
    assert len(fast.entries()) == 2


def test_store_output_passes_glossary_schema(seeded: GlossaryStore):
    import jsonschema

    seeded.lock("サンプル・タロウ")
    seeded.mark_conflict("サンプル王国")
    seeded.delete("サンプル王国")  # soft tombstone serialized too
    schema = json.loads((REPO_ROOT / "schemas" / "glossary.schema.json").read_text(encoding="utf-8"))
    data = yaml.safe_load(seeded.path.read_text(encoding="utf-8"))
    jsonschema.Draft7Validator(schema).validate(data)


def test_loads_fs012_migrated_real_data_if_present():
    """Loader smoke on the FS-012 migration output (read-only)."""
    real = REPO_ROOT / "workspace" / "configs" / "glossary.yaml"
    if not real.is_file():
        pytest.skip("no migrated real data on this machine")
    store = GlossaryStore(real)
    entries = store.entries()
    assert isinstance(entries, list) and len(entries) >= 1
