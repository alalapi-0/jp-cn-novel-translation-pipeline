"""Tests for workspace review state persistence."""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import stat
import sys
import threading
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from assets import translation_memory as memory  # noqa: E402
from workbench import review_state as review  # noqa: E402
from workbench.review_state import (  # noqa: E402
    approval_identity,
    get_project_review_state,
    patch_project_review_state,
)


def test_review_state_persists_segment_and_issue(tmp_path: Path) -> None:
    (tmp_path / "workspace").mkdir()
    patch_project_review_state(
        tmp_path,
        "demo-jp-cn",
        segments={"seg-001": {"status": "approved"}},
        issues={"ri-0001": {"status": "resolved"}},
    )
    state = get_project_review_state(tmp_path, "demo-jp-cn")
    assert state["segments"]["seg-001"]["status"] == "approved"
    assert state["issues"]["ri-0001"]["status"] == "resolved"

    reloaded = get_project_review_state(tmp_path, "demo-jp-cn")
    assert reloaded["segments"]["seg-001"]["status"] == "approved"


def test_approval_identity_binds_every_canonical_dimension() -> None:
    base = {
        "project_id": "project-a",
        "language_direction": "JP_TO_CN",
        "segment": {"id": "seg-1", "source": " source ", "draft": " target "},
    }
    original = approval_identity(**base)
    variants = [
        {**base, "project_id": "project-b"},
        {**base, "language_direction": "CN_TO_JP"},
        {**base, "segment": {**base["segment"], "id": "seg-2"}},
        {**base, "segment": {**base["segment"], "source": "source"}},
        {**base, "segment": {**base["segment"], "draft": "target"}},
    ]
    assert original.startswith("sha256:")
    assert len(original) == 71
    assert all(approval_identity(**variant) != original for variant in variants)


def test_cross_project_review_patches_do_not_lose_updates(tmp_path: Path) -> None:
    (tmp_path / "workspace").mkdir()
    barrier = threading.Barrier(2)

    def patch(project_id: str) -> None:
        barrier.wait()
        for index in range(25):
            patch_project_review_state(
                tmp_path,
                project_id,
                segments={f"seg-{index}": {"status": "rejected"}},
            )

    first = threading.Thread(target=patch, args=("project-a",))
    second = threading.Thread(target=patch, args=("project-b",))
    first.start()
    second.start()
    first.join()
    second.join()

    assert len(get_project_review_state(tmp_path, "project-a")["segments"]) == 25
    assert len(get_project_review_state(tmp_path, "project-b")["segments"]) == 25


# These synthetic tests cover the read boundary, not the write boundary.
BODY = b'{"projects":{"p":{"segments":{},"issues":{}}}}'


@pytest.fixture(autouse=True)
def no_leaked_fds(monkeypatch):
    # Count only descriptors created by the reader; libraries and pytest may
    # lazily open unrelated process-wide descriptors during a test.
    opened = set()
    original_open, original_close, original_at2 = os.open, os.close, memory._open_at2
    def open_root(path, flags, *args, **kwargs):
        fd = original_open(path, flags, *args, **kwargs)
        if path == "/": opened.add(fd)
        return fd
    def open_at2(fd, relative, *, resolve):
        result = original_at2(fd, relative, resolve=resolve)
        opened.add(result)
        return result
    def close(fd):
        original_close(fd)
        opened.discard(fd)
    monkeypatch.setattr(os, "open", open_root)
    monkeypatch.setattr(memory, "_open_at2", open_at2)
    monkeypatch.setattr(os, "close", close)
    yield
    assert opened == set()


@pytest.fixture()
def fixture_root(tmp_path):
    root = tmp_path / "repo"
    (root / "workspace").mkdir(parents=True)
    return root


def guard_body_reads(monkeypatch, targets):
    identities = {(target.stat().st_dev, target.stat().st_ino) for target in targets}
    original = os.read
    def read(fd, count):
        current = os.fstat(fd)
        assert (current.st_dev, current.st_ino) not in identities, "forbidden fixture body read"
        return original(fd, count)
    monkeypatch.setattr(os, "read", read)


def test_trusted_missing_leaf_and_valid_snapshot(fixture_root, monkeypatch):
    root = fixture_root
    missing = review.read_review_state_snapshot(root)
    assert missing.state["projects"] == {}
    assert review.read_review_state_snapshot(root).identity == missing.identity
    leaf = root / "workspace" / review.REVIEW_STATE_FILE
    leaf.write_bytes(BODY)
    original_bytes, original_text = Path.read_bytes, Path.read_text
    def guard_bytes(path):
        if path == leaf:
            raise AssertionError("review state reopened by ordinary path")
        return original_bytes(path)
    def guard_text(path, *args, **kwargs):
        if path == leaf:
            raise AssertionError("review state reopened by ordinary path")
        return original_text(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_bytes", guard_bytes)
    monkeypatch.setattr(Path, "read_text", guard_text)
    project, identity = review.get_project_review_snapshot(root, "p")
    assert project == {"segments": {}, "issues": {}}
    assert identity != missing.identity
    assert review.read_review_state_snapshot(root).identity == identity


def test_missing_or_untrusted_roots_are_unavailable(fixture_root, tmp_path):
    root = fixture_root
    linked_root = tmp_path / "linked-root"
    linked_root.symlink_to(root, target_is_directory=True)
    ancestor = tmp_path / "linked-parent"
    ancestor.symlink_to(tmp_path, target_is_directory=True)
    for target in (tmp_path / "absent", linked_root, ancestor / "repo", ancestor / ".." / "repo"):
        with pytest.raises(review.ReviewStateUnavailableError):
            review.load_review_state(target)
    (root / "workspace").rmdir()
    with pytest.raises(review.ReviewStateUnavailableError):
        review.load_review_state(root)


@pytest.mark.parametrize("kind", ["workspace_link", "leaf_link", "magic_link", "hardlink", "directory", "fifo", "device"])
def test_unsafe_objects_rejected_before_body_read(fixture_root, tmp_path, monkeypatch, kind):
    root = fixture_root
    folder = root / "workspace"
    leaf = folder / review.REVIEW_STATE_FILE
    outside = tmp_path / "external"
    outside.mkdir()
    target = outside / "body"
    target.write_bytes(BODY)
    extra_fd = None
    if kind == "workspace_link":
        folder.rmdir()
        (outside / review.REVIEW_STATE_FILE).write_bytes(BODY)
        target = outside / review.REVIEW_STATE_FILE
        folder.symlink_to(outside, target_is_directory=True)
    elif kind == "leaf_link":
        leaf.symlink_to(target)
    elif kind == "magic_link":
        extra_fd = os.open(target, os.O_RDONLY)
        leaf.symlink_to(f"/proc/self/fd/{extra_fd}")
    elif kind == "hardlink":
        os.link(target, leaf)
    elif kind == "directory":
        leaf.mkdir()
    elif kind == "fifo":
        os.mkfifo(leaf)
    else:
        leaf.write_bytes(BODY)
        original_open, original_stat = memory._open_at2, os.fstat
        selected = []
        def capture(fd, relative, *, resolve):
            opened = original_open(fd, relative, resolve=resolve)
            if relative == Path(review.REVIEW_STATE_FILE):
                selected.append(opened)
            return opened
        def device(fd):
            actual = original_stat(fd)
            if fd in selected:
                fields = list(actual)
                fields[stat.ST_MODE] = stat.S_IFCHR | 0o600
                return os.stat_result(fields)
            return actual
        monkeypatch.setattr(memory, "_open_at2", capture)
        monkeypatch.setattr(os, "fstat", device)
        target = leaf
    try:
        guard_body_reads(monkeypatch, [target])
        with pytest.raises(review.ReviewStateUnavailableError):
            review.load_review_state(root)
    finally:
        if extra_fd is not None:
            os.close(extra_fd)


def test_swap_before_open_cannot_read_external_body(fixture_root, tmp_path, monkeypatch):
    leaf = fixture_root / "workspace" / review.REVIEW_STATE_FILE
    leaf.write_bytes(BODY)
    external = tmp_path / "external"
    external.write_bytes(BODY)
    original = memory._open_at2
    changed = []
    def swap(fd, relative, *, resolve):
        if relative == Path(review.REVIEW_STATE_FILE):
            leaf.rename(tmp_path / "old")
            leaf.symlink_to(external)
            changed.append(True)
        return original(fd, relative, resolve=resolve)
    monkeypatch.setattr(memory, "_open_at2", swap)
    guard_body_reads(monkeypatch, [external])
    with pytest.raises(review.ReviewStateUnavailableError):
        review.load_review_state(fixture_root)
    assert changed == [True]


def test_workspace_swap_before_open_cannot_read_external_body(fixture_root, tmp_path, monkeypatch):
    workspace = fixture_root / "workspace"
    (workspace / review.REVIEW_STATE_FILE).write_bytes(BODY)
    outside = tmp_path / "external-dir"
    outside.mkdir()
    target = outside / review.REVIEW_STATE_FILE
    target.write_bytes(BODY)
    original = memory._open_at2
    changed = []
    def swap(fd, relative, *, resolve):
        if relative == Path("workspace"):
            workspace.rename(tmp_path / "old-workspace")
            workspace.symlink_to(outside, target_is_directory=True)
            changed.append(True)
        return original(fd, relative, resolve=resolve)
    monkeypatch.setattr(memory, "_open_at2", swap)
    guard_body_reads(monkeypatch, [target])
    with pytest.raises(review.ReviewStateUnavailableError):
        review.load_review_state(fixture_root)
    assert changed == [True]


@pytest.mark.parametrize("body", [b"{", b"\xff", b"[]", b'{"version":true}',
    b'{"version":2}', b'{"projects":[]}', b'{"projects":{"p":[]}}',
    b'{"projects":{"p":{"segments":[]}}}', b'{"projects":{"p":{"issues":{"i":null}}}}',
    b'{"projects":{},"projects":{}}', b'{"projects":{},"value":NaN}'])
def test_invalid_state_is_unavailable(fixture_root, body):
    (fixture_root / "workspace" / review.REVIEW_STATE_FILE).write_bytes(body)
    with pytest.raises(review.ReviewStateUnavailableError) as error:
        review.load_review_state(fixture_root)
    assert str(fixture_root) not in str(error.value)


def test_size_permission_and_unsupported_fail_closed(fixture_root, monkeypatch):
    leaf = fixture_root / "workspace" / review.REVIEW_STATE_FILE
    leaf.write_bytes(BODY)
    guard_body_reads(monkeypatch, [leaf])
    monkeypatch.setattr(review, "REVIEW_STATE_MAX_BYTES", 4)
    with pytest.raises(review.ReviewStateUnavailableError):
        review.load_review_state(fixture_root)
    monkeypatch.setattr(review, "REVIEW_STATE_MAX_BYTES", 1024)
    original = memory._open_at2
    def denied(fd, relative, *, resolve):
        if relative == Path(review.REVIEW_STATE_FILE):
            raise PermissionError("synthetic permission denial")
        return original(fd, relative, resolve=resolve)
    monkeypatch.setattr(memory, "_open_at2", denied)
    with pytest.raises(review.ReviewStateUnavailableError):
        review.load_review_state(fixture_root)
    monkeypatch.setattr(memory, "_open_at2", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("unsupported")))
    with pytest.raises(review.ReviewStateUnavailableError):
        review.load_review_state(fixture_root)


def test_changed_during_read_is_rejected(fixture_root, monkeypatch):
    leaf = fixture_root / "workspace" / review.REVIEW_STATE_FILE
    leaf.write_bytes(b'{"projects":{},"padding":"' + b'x' * 70000 + b'"}')
    original = os.read
    changed = []
    def mutate(fd, count):
        data = original(fd, count)
        if data and not changed:
            changed.append(True)
            leaf.write_bytes(BODY)
        return data
    monkeypatch.setattr(os, "read", mutate)
    with pytest.raises(review.ReviewStateUnavailableError):
        review.load_review_state(fixture_root)
    assert changed == [True]


def test_read_and_cleanup_errors_are_preserved_and_fds_closed(fixture_root, monkeypatch):
    (fixture_root / "workspace" / review.REVIEW_STATE_FILE).write_bytes(BODY)
    original_open, original_close = memory._open_at2, os.close
    selected = []
    def capture(fd, relative, *, resolve):
        opened = original_open(fd, relative, resolve=resolve)
        if relative == Path(review.REVIEW_STATE_FILE): selected.append(opened)
        return opened
    def failed_read(fd, count):
        if fd in selected: raise ValueError("synthetic read failure")
        raise AssertionError("unexpected read")
    def failed_close(fd):
        original_close(fd)
        if fd in selected: raise OSError("synthetic close failure")
    monkeypatch.setattr(memory, "_open_at2", capture)
    monkeypatch.setattr(os, "read", failed_read)
    monkeypatch.setattr(os, "close", failed_close)
    with pytest.raises(review.ReviewStateUnavailableError) as error:
        review.load_review_state(fixture_root)
    cause = error.value.__cause__
    assert isinstance(cause, ExceptionGroup)
    assert {type(item) for item in cause.exceptions} == {ValueError, OSError}


def test_cancel_during_read_closes_owned_descriptors(fixture_root, monkeypatch):
    (fixture_root / "workspace" / review.REVIEW_STATE_FILE).write_bytes(BODY)
    def cancel(_fd, _count):
        raise KeyboardInterrupt()
    monkeypatch.setattr(os, "read", cancel)
    with pytest.raises(KeyboardInterrupt):
        review.load_review_state(fixture_root)


@pytest.mark.parametrize("entry", ["workbench", "script"])
@pytest.mark.parametrize("change", ["same", "both_missing", "appears", "disappears", "content",
    "same_content_new_inode", "leaf_link", "hardlink", "corrupt", "unsupported"])
def test_export_rechecks_the_same_validated_snapshot(fixture_root, tmp_path, monkeypatch, entry, change):
    root = fixture_root
    leaf = root / "workspace" / review.REVIEW_STATE_FILE
    if change not in {"both_missing", "appears"}: leaf.write_bytes(BODY)
    outside = tmp_path / "outside"
    outside.write_bytes(BODY)
    guard_body_reads(monkeypatch, [outside])
    original_read = Path.read_bytes
    def guarded_read(path):
        if path == leaf: raise AssertionError("ordinary review-state read")
        return original_read(path)
    monkeypatch.setattr(Path, "read_bytes", guarded_read)
    manifest = root / "workspace" / "manifests" / "p.json"
    manifest.parent.mkdir()
    manifest_raw = json.dumps({"project_id": "p"}).encode()
    manifest.write_bytes(manifest_raw)
    committed = []
    def export(*_args, before_commit, **_kwargs):
        if change == "appears": leaf.write_bytes(BODY)
        if change == "disappears": leaf.unlink()
        if change == "content": leaf.write_bytes(b'{"projects":{}}')
        if change == "same_content_new_inode":
            leaf.rename(tmp_path / "old-review")
            leaf.write_bytes(BODY)
        if change in {"leaf_link", "hardlink"}:
            leaf.unlink()
            if change == "leaf_link": leaf.symlink_to(outside)
            else: os.link(outside, leaf)
        if change == "corrupt": leaf.write_bytes(b"{")
        if change == "unsupported":
            monkeypatch.setattr(memory, "_open_at2", lambda *_a, **_k: (_ for _ in ()).throw(ValueError("unsupported")))
        before_commit()
        committed.append(True)
        return {"ok": True}
    if entry == "workbench":
        from workbench import canonical_service
        from translation import canonical_export
        monkeypatch.setattr(canonical_service, "_read", lambda *_a, **_k: (manifest, manifest_raw, {"project_id": "p"}, "0" * 64))
        monkeypatch.setattr(canonical_export, "export_accepted_revision", export)
        run = lambda: canonical_service.export_selected(root, "p", expected_manifest_sha256="0" * 64)
    else:
        spec = importlib.util.spec_from_file_location("synthetic_export_cli", REPO_ROOT / "scripts/export_consistency_final_volume.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        monkeypatch.setattr(module, "export_accepted_revision", export)
        run = lambda: module.export_final(None, repo_root=root, selection_manifest=manifest,
                                         selection_sha256=hashlib.sha256(manifest_raw).hexdigest())
    if change in {"same", "both_missing"}:
        assert run() == {"ok": True}
        assert committed == [True]
    else:
        with pytest.raises((review.ReviewStateUnavailableError, RuntimeError, ValueError)):
            run()
        assert committed == []
