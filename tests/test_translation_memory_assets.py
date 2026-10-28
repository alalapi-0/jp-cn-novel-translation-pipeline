"""Tests for translation-memory asset deposition and consumption."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from assets.translation_memory import (  # noqa: E402
    ExternalAssetExtractionUnavailable,
    build_translation_memory_assets,
    render_translation_asset_context,
)
from translation.draft_runner import run_draft_stage_a  # noqa: E402
from translation.prompt_builder import build_batch_messages  # noqa: E402
from translation.chapter_parser import Segment  # noqa: E402
from workbench.export_service import run_export  # noqa: E402
from workbench.project_registry import (  # noqa: E402
    create_project_manifest,
    patch_project_review_state_cas,
    save_project_manifest,
)
from workbench.review_state import DecisionActor, approval_identity, patch_project_review_state  # noqa: E402


@pytest.mark.parametrize("kind", ["glossary", "character", "tm_pair"])
@pytest.mark.parametrize("scenario", ["root_link", "leaf_external", "leaf_internal", "hardlink", "rename_race"])
def test_manifest_dependency_rejects_unsafe_paths_before_reading_body(tmp_path, monkeypatch, kind, scenario):
    from assets import translation_memory as memory
    from workbench import project_registry

    repo = tmp_path / "repo"
    workspace = repo / "workspace"
    workspace.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    if kind == "tm_pair":
        (workspace / "assets").mkdir()
        folder = workspace / "assets" / "translation_memory"
        filename = "synthetic.json"
        key = "tm:one"
        descriptor = {"kind": kind, "asset": filename, "pair_id": "a" * 64}
    else:
        folder = workspace / "configs"
        filename = "glossary.yaml" if kind == "glossary" else "character_profile.yaml"
        key = "config:one"
        descriptor = {"kind": kind, "entry": "Synthetic"}

    external = outside / "synthetic-body"
    external.write_text("fixture body must not be read", encoding="utf-8")
    forbidden = [external.stat()]
    if scenario == "root_link":
        target = outside / filename
        target.write_text("fixture body must not be read", encoding="utf-8")
        forbidden.append(target.stat())
        folder.symlink_to(outside, target_is_directory=True)
    elif scenario == "leaf_external":
        folder.mkdir()
        (folder / filename).symlink_to(external)
    elif scenario == "leaf_internal":
        folder.mkdir()
        target = folder / "internal-body"
        target.write_text("fixture body must not be read", encoding="utf-8")
        forbidden.append(target.stat())
        (folder / filename).symlink_to(target.name)
    elif scenario == "hardlink":
        folder.mkdir()
        os.link(external, folder / filename)
    else:
        folder.mkdir()
        (folder / filename).write_text("fixture internal body", encoding="utf-8")
        replacement = outside / "replacement"
        replacement.mkdir()
        target = replacement / filename
        target.write_text("fixture body must not be read", encoding="utf-8")
        forbidden.append(target.stat())
        original_open = memory._open_beneath
        def switch_after_root_open(root_fd, relative):
            folder.rename(outside / "moved")
            folder.symlink_to(replacement, target_is_directory=True)
            return original_open(root_fd, relative)
        monkeypatch.setattr(memory, "_open_beneath", switch_after_root_open)

    original_read = os.read
    def read_without_forbidden_body(fd, amount):
        actual = os.fstat(fd)
        assert all((actual.st_dev, actual.st_ino) != (item.st_dev, item.st_ino) for item in forbidden)
        return original_read(fd, amount)
    def unexpected_parser(*_args, **_kwargs):
        raise AssertionError("unsafe dependency reached a body parser")
    monkeypatch.setattr(os, "read", read_without_forbidden_body)
    monkeypatch.setattr(project_registry.yaml, "safe_load", unexpected_parser)
    monkeypatch.setattr(memory, "_current_asset_context", unexpected_parser)
    data = {"dependency_sources": {key: descriptor}, "dependency_versions": {key: "0" * 64},
            "segments": [{"id": "affected", "dependency_keys": [key]}, {"id": "independent"}]}
    resolved = project_registry._resolve_manifest_dependencies(repo, data)
    assert resolved["segments"][0]["dependency_resolution_errors"] == [key]
    assert "dependency_resolution_errors" not in resolved["segments"][1]
    assert str(outside) not in json.dumps(resolved)


def test_manifest_tm_dependency_hands_verified_bytes_to_consumer(tmp_path, monkeypatch):
    from assets import translation_memory as memory
    from workbench.project_registry import _resolve_manifest_dependencies

    folder = tmp_path / "workspace" / "assets" / "translation_memory"
    folder.mkdir(parents=True)
    target = folder / "synthetic.json"
    body = b'{"asset_kind":"translation_memory","synthetic":true}'
    target.write_bytes(body)
    pair_id = "a" * 64
    calls = []
    def consume(path, *, repo_root, source_bytes):
        calls.append((path, repo_root, source_bytes))
        return {"translation_pairs": [{"pair_id": pair_id, "version_sha256": "b" * 64}]}
    def no_path_read(self, *_args, **_kwargs):
        if self == target:
            raise AssertionError("verified dependency was reopened by path")
        raise AssertionError("unexpected path read")
    monkeypatch.setattr(memory, "_current_asset_context", consume)
    monkeypatch.setattr(Path, "read_text", no_path_read)
    monkeypatch.setattr(Path, "read_bytes", no_path_read)
    data = {"dependency_sources": {"tm:one": {"kind": "tm_pair", "asset": target.name, "pair_id": pair_id}},
            "dependency_versions": {"tm:one": "0" * 64}, "segments": [{"dependency_keys": ["tm:one"]}]}
    resolved = _resolve_manifest_dependencies(tmp_path, data)
    assert calls == [(target, tmp_path, body)]
    assert resolved["dependency_versions"]["tm:one"] == "b" * 64
    assert memory.load_translation_asset_context(target, source_bytes=body)["synthetic"] is True


@pytest.mark.parametrize("kind", ["glossary", "character", "tm_pair"])
def test_manifest_dependency_withholds_file_changed_while_reading(tmp_path, monkeypatch, kind):
    from assets import translation_memory as memory
    from workbench import project_registry

    if kind == "tm_pair":
        folder = tmp_path / "workspace" / "assets" / "translation_memory"
        filename = "synthetic.json"
        key = "tm:one"
        descriptor = {"kind": kind, "asset": filename, "pair_id": "a" * 64}
    else:
        folder = tmp_path / "workspace" / "configs"
        filename = "glossary.yaml" if kind == "glossary" else "character_profile.yaml"
        key = "config:one"
        descriptor = {"kind": kind, "entry": "Synthetic"}
    folder.mkdir(parents=True)
    target = folder / filename
    target.write_text("synthetic original", encoding="utf-8")
    identity = target.stat()
    original_read = os.read
    changed = False
    def change_after_first_read(fd, amount):
        nonlocal changed
        result = original_read(fd, amount)
        actual = os.fstat(fd)
        if not changed and (actual.st_dev, actual.st_ino) == (identity.st_dev, identity.st_ino):
            target.write_text("synthetic changed and longer", encoding="utf-8")
            changed = True
        return result
    def unexpected_parser(*_args, **_kwargs):
        raise AssertionError("changed dependency reached a body parser")
    monkeypatch.setattr(os, "read", change_after_first_read)
    monkeypatch.setattr(project_registry.yaml, "safe_load", unexpected_parser)
    monkeypatch.setattr(memory, "_current_asset_context", unexpected_parser)
    data = {"dependency_sources": {key: descriptor}, "dependency_versions": {key: "0" * 64},
            "segments": [{"dependency_keys": [key]}, {"id": "independent"}]}
    resolved = project_registry._resolve_manifest_dependencies(tmp_path, data)
    assert changed is True
    assert resolved["segments"][0]["dependency_resolution_errors"] == [key]
    assert "dependency_resolution_errors" not in resolved["segments"][1]


def test_manifest_dependency_preserves_read_and_cleanup_failures(tmp_path, monkeypatch):
    from assets import translation_memory as memory
    from workbench.project_registry import _resolve_manifest_dependencies

    folder = tmp_path / "workspace" / "configs"
    folder.mkdir(parents=True)
    (folder / "glossary.yaml").write_text("synthetic fixture", encoding="utf-8")
    original_open, original_read, original_close = memory._open_beneath, os.read, os.close
    tracked = {"fd": None, "raised": False}
    def capture_open(root_fd, relative):
        tracked["fd"] = original_open(root_fd, relative)
        return tracked["fd"]
    def fail_read(fd, amount):
        if fd == tracked["fd"]:
            raise ValueError("synthetic read failure")
        return original_read(fd, amount)
    def fail_close(fd):
        original_close(fd)
        if fd == tracked["fd"] and not tracked["raised"]:
            tracked["raised"] = True
            raise OSError("synthetic cleanup failure")
    monkeypatch.setattr(memory, "_open_beneath", capture_open)
    monkeypatch.setattr(os, "read", fail_read)
    monkeypatch.setattr(os, "close", fail_close)
    data = {"dependency_sources": {"config:one": {"kind": "glossary", "entry": "Synthetic"}},
            "dependency_versions": {"config:one": "0" * 64}, "segments": [{"dependency_keys": ["config:one"]}]}
    with pytest.raises(ExceptionGroup) as error:
        _resolve_manifest_dependencies(tmp_path, data)
    assert any(isinstance(item, ValueError) for item in error.value.exceptions)
    assert any(isinstance(item, OSError) for item in error.value.exceptions)


def test_memory_context_caps_terms_names_and_pairs_independently(monkeypatch):
    from assets import translation_memory as memory
    data = {
        "term_candidates": [{"source": "term-one", "target": "one"}],
        "proper_noun_candidates": [{"source": f"name-{n}"} for n in range(4)],
        "translation_pairs": [{"source_text": "phrase-one", "target_text": "target"}],
    }
    monkeypatch.setattr(memory, "_current_asset_context", lambda *_args, **_kwargs: data)
    result = memory.select_batch_context_hits(
        Path("synthetic.json"), ["term-one name-0 name-1 name-2 name-3 phrase-one"],
        max_terms=8, max_character_notes=1, max_pairs=0,
    )
    assert result.count("- Term:") == 1
    assert result.count("- Name:") == 1
    assert "- Phrase:" not in result
    no_terms = memory.select_batch_context_hits(
        Path("synthetic.json"), ["term-one name-0"], max_terms=0, max_character_notes=1, max_pairs=0,
    )
    assert "- Term:" not in no_terms and no_terms.count("- Name:") == 1


def test_zero_memory_caps_avoid_reading_context(monkeypatch):
    from assets import translation_memory as memory
    def unexpected_read(*_args, **_kwargs):
        raise AssertionError("zero-cap request must not read a context")
    monkeypatch.setattr(memory, "_current_asset_context", unexpected_read)
    assert memory.select_batch_context_hits(
        Path("synthetic.json"), ["source"], max_terms=0, max_character_notes=0, max_pairs=0,
    ) == ""


@pytest.mark.parametrize("field, value", [
    ("max_terms", -1), ("max_character_notes", -1), ("max_pairs", -1), ("max_terms", True),
])
def test_memory_context_rejects_invalid_caps(monkeypatch, field, value):
    from assets import translation_memory as memory
    monkeypatch.setattr(memory, "_current_asset_context", lambda *_args, **_kwargs: {})
    with pytest.raises(ValueError, match="nonnegative integer"):
        memory.select_batch_context_hits(Path("synthetic.json"), ["source"], **{field: value})


@pytest.mark.parametrize("kind", ["root_link", "leaf_link"])
def test_memory_manifest_root_symlink_is_rejected_before_body_reader(tmp_path, monkeypatch, kind):
    from assets import translation_memory as memory
    from workbench import project_registry
    repo = tmp_path / "repo"
    (repo / "workspace").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "synthetic.json"
    target.write_text("synthetic body must not be opened", encoding="utf-8")
    manifests = repo / "workspace" / "manifests"
    if kind == "root_link":
        manifests.symlink_to(outside, target_is_directory=True)
    else:
        manifests.mkdir()
        (manifests / "synthetic.json").symlink_to(target)
    target_stat = target.stat(); original_read = os.read
    def checked_read(fd, amount):
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) == (target_stat.st_dev, target_stat.st_ino):
            raise AssertionError("outside manifest body opened")
        return original_read(fd, amount)
    monkeypatch.setattr(os, "read", checked_read)
    def unexpected_read(*_args, **_kwargs):
        raise AssertionError("outside manifest reader reached")
    monkeypatch.setattr(project_registry, "load_project_manifest", unexpected_read)
    with pytest.raises((KeyError, ValueError)):
        memory._collect_manifest_pairs(repo, "synthetic", status_mode="translated")


@pytest.mark.parametrize("kind", ["runs", "diagnostics"])
def test_memory_run_root_symlink_is_rejected_before_body_reader(tmp_path, monkeypatch, kind):
    from assets import translation_memory as memory
    repo = tmp_path / "repo"
    (repo / "workspace" / "diagnostics").mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    if kind == "runs":
        run = outside / "synthetic"
        (repo / "workspace" / "runs").symlink_to(outside, target_is_directory=True)
    else:
        run = outside / "synthetic" / "workspace" / "runs" / "synthetic"
        (repo / "workspace" / "diagnostics" / "real_api_runs").symlink_to(outside, target_is_directory=True)
    run.mkdir(parents=True)
    target = run / "segments.json"
    target.write_text("synthetic body must not be opened", encoding="utf-8")
    target_stat = target.stat(); original_read = os.read
    def checked_read(fd, amount):
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) == (target_stat.st_dev, target_stat.st_ino):
            raise AssertionError("outside segments body opened")
        return original_read(fd, amount)
    monkeypatch.setattr(os, "read", checked_read)
    original = Path.read_text
    def checked(path, *args, **kwargs):
        if path.name == "segments.json" and path.resolve().is_relative_to(outside):
            raise AssertionError("outside segments reader reached")
        return original(path, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", checked)
    with pytest.raises((FileNotFoundError, ValueError)):
        memory._collect_run_pairs(repo, "synthetic", status_mode="translated")


@pytest.mark.parametrize("kind", ["child_link", "leaf_link", "traversal", "absolute_outside"])
def test_memory_run_aliases_cannot_read_foreign_body(tmp_path, monkeypatch, kind):
    from assets import translation_memory as memory
    repo = tmp_path / "repo"
    runs = repo / "workspace" / "runs"
    runs.mkdir(parents=True)
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "segments.json"
    target.write_text("synthetic body must not be opened", encoding="utf-8")
    if kind == "child_link":
        (runs / "synthetic").symlink_to(outside, target_is_directory=True)
        source_run = "synthetic"
    elif kind == "leaf_link":
        run = runs / "synthetic"
        run.mkdir()
        (run / "segments.json").symlink_to(target)
        source_run = "synthetic"
    elif kind == "traversal":
        source_run = "../outside"
    else:
        source_run = str(outside)
    target_stat = target.stat(); original_read = os.read
    def checked_read(fd, amount):
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) == (target_stat.st_dev, target_stat.st_ino):
            raise AssertionError("outside body opened")
        return original_read(fd, amount)
    monkeypatch.setattr(os, "read", checked_read)
    with pytest.raises((FileNotFoundError, ValueError)):
        memory._collect_run_pairs(repo, source_run, status_mode="translated")


def test_memory_manifest_parent_swap_before_open_is_rejected(tmp_path, monkeypatch):
    from assets import translation_memory as memory
    repo = tmp_path / "repo"
    repo.mkdir()
    project_id = _r42_machine_project(repo)
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / f"{project_id}.json"
    target.write_text("synthetic body must not be opened", encoding="utf-8")
    manifests = repo / "workspace" / "manifests"
    original_open = memory._open_beneath; original_read = os.read; target_stat = target.stat(); swapped = False
    def checked_open(root_fd, relative):
        nonlocal swapped
        if relative.name == f"{project_id}.json" and not swapped:
            manifests.rename(repo / "workspace" / "saved-manifests")
            manifests.symlink_to(outside, target_is_directory=True)
            swapped = True
        return original_open(root_fd, relative)
    def checked_read(fd, amount):
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) == (target_stat.st_dev, target_stat.st_ino):
            raise AssertionError("outside body opened during parent swap")
        return original_read(fd, amount)
    monkeypatch.setattr(memory, "_open_beneath", checked_open)
    monkeypatch.setattr(os, "read", checked_read)
    with pytest.raises((KeyError, ValueError)):
        memory._collect_manifest_pairs(repo, project_id, status_mode="translated")
    assert swapped


def test_memory_manifest_directory_moved_outside_before_open_is_rejected(tmp_path, monkeypatch):
    from assets import translation_memory as memory
    repo = tmp_path / "repo"
    repo.mkdir()
    project_id = _r42_machine_project(repo)
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "foreign.json"
    target.write_text("synthetic body must not be opened", encoding="utf-8")
    target_stat = target.stat(); manifests = repo / "workspace" / "manifests"
    original_open = memory._open_beneath; original_read = os.read; moved = False
    def checked_open(root_fd, relative):
        nonlocal moved
        if relative.name == f"{project_id}.json" and not moved:
            manifests.rename(outside / "moved-manifests")
            (outside / "moved-manifests" / f"{project_id}.json").unlink()
            target.rename(outside / "moved-manifests" / f"{project_id}.json")
            moved = True
        return original_open(root_fd, relative)
    def checked_read(fd, amount):
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) == (target_stat.st_dev, target_stat.st_ino):
            raise AssertionError("foreign body opened after directory move")
        return original_read(fd, amount)
    monkeypatch.setattr(memory, "_open_beneath", checked_open)
    monkeypatch.setattr(os, "read", checked_read)
    with pytest.raises((KeyError, FileNotFoundError, ValueError)):
        memory._collect_manifest_pairs(repo, project_id, status_mode="translated")
    assert moved


@pytest.mark.parametrize("unsupported", ["host", "syscall"])
def test_memory_secure_direct_read_fails_closed_when_unavailable(tmp_path, monkeypatch, unsupported):
    import ctypes
    import platform
    from assets import translation_memory as memory
    repo = tmp_path / "repo"
    repo.mkdir()
    project_id = _r42_machine_project(repo)
    target = repo / "workspace" / "manifests" / f"{project_id}.json"
    target_stat = target.stat(); original_read = os.read
    def checked_read(fd, amount):
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) == (target_stat.st_dev, target_stat.st_ino):
            raise AssertionError("unsupported host read the source body")
        return original_read(fd, amount)
    monkeypatch.setattr(os, "read", checked_read)
    if unsupported == "host":
        monkeypatch.setattr(platform, "machine", lambda: "unsupported-synthetic-host")
    else:
        monkeypatch.setattr(ctypes, "CDLL", lambda *_args, **_kwargs: object())
    with pytest.raises(ValueError, match="unavailable"):
        memory._collect_manifest_pairs(repo, project_id, status_mode="translated")


def test_memory_direct_source_changed_during_read_is_rejected(tmp_path, monkeypatch):
    from assets import translation_memory as memory
    repo = tmp_path / "repo"
    repo.mkdir()
    project_id = _r42_machine_project(repo)
    target = repo / "workspace" / "manifests" / f"{project_id}.json"
    target_stat = target.stat(); original_read = os.read; changed = False
    def checked_read(fd, amount):
        nonlocal changed
        data = original_read(fd, amount)
        info = os.fstat(fd)
        if data and not changed and (info.st_dev, info.st_ino) == (target_stat.st_dev, target_stat.st_ino):
            target.write_text("synthetic changed source", encoding="utf-8")
            changed = True
        return data
    monkeypatch.setattr(os, "read", checked_read)
    with pytest.raises(ValueError, match="changed during read"):
        memory._collect_manifest_pairs(repo, project_id, status_mode="translated")
    assert changed


def test_memory_direct_reader_closes_root_when_file_close_fails(tmp_path, monkeypatch):
    from assets import translation_memory as memory
    repo = tmp_path / "repo"
    repo.mkdir()
    project_id = _r42_machine_project(repo)
    target = repo / "workspace" / "manifests" / f"{project_id}.json"
    target_stat = target.stat(); original_open = memory._open_beneath; original_close = os.close
    observed = {"root_fd": None, "root_closed": False, "file_close_failed": False}
    def tracked_open(root_fd, relative):
        observed["root_fd"] = root_fd
        return original_open(root_fd, relative)
    def checked_close(fd):
        info = os.fstat(fd)
        if ((info.st_dev, info.st_ino) == (target_stat.st_dev, target_stat.st_ino)
                and not observed["file_close_failed"]):
            observed["file_close_failed"] = True
            original_close(fd)
            raise OSError("synthetic file close failure")
        if fd == observed["root_fd"]:
            observed["root_closed"] = True
        return original_close(fd)
    monkeypatch.setattr(memory, "_open_beneath", tracked_open)
    monkeypatch.setattr(os, "close", checked_close)
    with pytest.raises(OSError, match="synthetic file close failure"):
        memory._collect_manifest_pairs(repo, project_id, status_mode="translated")
    assert observed["file_close_failed"] and observed["root_closed"]


def test_memory_direct_reader_preserves_read_and_cleanup_failures(tmp_path, monkeypatch):
    from assets import translation_memory as memory
    repo = tmp_path / "repo"
    repo.mkdir()
    project_id = _r42_machine_project(repo)
    target = repo / "workspace" / "manifests" / f"{project_id}.json"
    target_stat = target.stat(); original_open = memory._open_beneath
    original_read = os.read; original_close = os.close; observed = {"root_fd": None, "root_closed": False}
    def tracked_open(root_fd, relative):
        observed["root_fd"] = root_fd
        return original_open(root_fd, relative)
    def is_target(fd):
        info = os.fstat(fd)
        return (info.st_dev, info.st_ino) == (target_stat.st_dev, target_stat.st_ino)
    def checked_read(fd, amount):
        if is_target(fd):
            raise OSError("synthetic read failure")
        return original_read(fd, amount)
    def checked_close(fd):
        if is_target(fd):
            original_close(fd)
            raise OSError("synthetic close failure")
        if fd == observed["root_fd"]:
            observed["root_closed"] = True
        return original_close(fd)
    monkeypatch.setattr(memory, "_open_beneath", tracked_open)
    monkeypatch.setattr(os, "read", checked_read)
    monkeypatch.setattr(os, "close", checked_close)
    with pytest.raises(ExceptionGroup) as failure:
        memory._collect_manifest_pairs(repo, project_id, status_mode="translated")
    assert [type(e) for e in failure.value.exceptions] == [ValueError, OSError]
    assert observed["root_closed"]


@pytest.mark.parametrize("kind", ["manifest", "run"])
def test_memory_direct_hardlink_to_foreign_file_is_not_read(tmp_path, monkeypatch, kind):
    from assets import translation_memory as memory
    repo = tmp_path / "repo"
    outside = tmp_path / "outside"
    outside.mkdir()
    target = outside / "foreign.json"
    target.write_text("synthetic body must not be opened", encoding="utf-8")
    if kind == "manifest":
        folder = repo / "workspace" / "manifests"
        filename = "synthetic.json"
    else:
        folder = repo / "workspace" / "runs" / "synthetic"
        filename = "segments.json"
    folder.mkdir(parents=True)
    os.link(target, folder / filename)
    target_stat = target.stat(); original_read = os.read
    def checked_read(fd, amount):
        info = os.fstat(fd)
        if (info.st_dev, info.st_ino) == (target_stat.st_dev, target_stat.st_ino):
            raise AssertionError("foreign hard-linked body opened")
        return original_read(fd, amount)
    monkeypatch.setattr(os, "read", checked_read)
    with pytest.raises(ValueError):
        if kind == "manifest":
            memory._collect_manifest_pairs(repo, "synthetic", status_mode="translated")
        else:
            memory._collect_run_pairs(repo, "synthetic", status_mode="translated")


@pytest.mark.parametrize("kind", ["runs", "diagnostics"])
def test_memory_direct_run_references_keep_valid_physical_paths(tmp_path, kind):
    from assets import translation_memory as memory
    repo = tmp_path / "repo"
    if kind == "runs":
        run = repo / "workspace" / "runs" / "synthetic"
    else:
        run = repo / "workspace" / "diagnostics" / "real_api_runs" / "synthetic" / "workspace" / "runs" / "synthetic"
    run.mkdir(parents=True)
    doc = {"language_direction": "JP_TO_CN", "chapters": [{"chapter_id": "ch-001", "segments": [
        {"segment_id": "seg-001", "source_text": "synthetic source", "draft_text": "synthetic target",
         "status": "machine_translated"},
    ]}]}
    (run / "segments.json").write_text(json.dumps(doc), encoding="utf-8")
    for reference in ("synthetic", str(run.relative_to(repo)), str(run)):
        pairs, direction = memory._collect_run_pairs(repo, reference, status_mode="translated")
        assert direction == "JP_TO_CN" and [pair.target_text for pair in pairs] == ["synthetic target"]


def _seed_workbench_project(repo: Path) -> str:
    project_id = "asset-memory-test"
    approved_segment = {
        "id": "seg-001",
        "segment_id": "seg-001",
        "chapter": 1,
        "source": "アルファの森へ向かう。",
        "draft": "前往阿尔法之森。",
        "status": "pending",
    }
    rejected_segment = {
        "id": "seg-002",
        "segment_id": "seg-002",
        "chapter": 1,
        "source": "【レア】称号を獲得した。",
        "draft": "【稀有】获得了称号。",
        "status": "pending",
    }
    create_project_manifest(
        repo,
        project_id=project_id,
        name="Asset Memory",
        language_direction="JP_TO_CN",
        segments=[
            approved_segment,
            rejected_segment,
        ],
    )
    identity = approval_identity(
        project_id=project_id,
        language_direction="JP_TO_CN",
        segment=approved_segment,
    )
    rejected_identity = approval_identity(
        project_id=project_id,
        language_direction="JP_TO_CN",
        segment=rejected_segment,
    )
    patch_project_review_state_cas(
        repo,
        project_id,
        decision_actor=DecisionActor("agent", "synthetic-test-agent"),
        segments={
            "seg-001": {"status": "approved", "expected_identity": identity},
            "seg-002": {
                "status": "rejected",
                "expected_identity": rejected_identity,
            },
        },
    )
    return project_id


def test_agent_mode_builds_approved_translation_memory_without_api(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "must-not-be-used")
    project_id = _seed_workbench_project(tmp_path)

    doc = build_translation_memory_assets(repo_root=tmp_path, project_id=project_id)

    assert doc["mode"] == "agent"
    assert doc["stats"]["api_calls"] == 0
    assert doc["stats"]["pairs"] == 1
    assert doc["approved_pairs"][0]["segment_id"] == "seg-001"
    assert "seg-002" not in doc["segment_map"]
    assert Path(doc["asset_path"]).is_file()
    assert "アルファ" in doc["context_prompt"]


def test_manifest_memory_rejects_legacy_unbound_approval(tmp_path):
    project_id = "asset-memory-legacy"
    create_project_manifest(
        tmp_path,
        project_id=project_id,
        name="Legacy",
        language_direction="JP_TO_CN",
        segments=[
            {
                "id": "seg-001",
                "source": "原文",
                "draft": "译文",
                "status": "approved",
            }
        ],
    )
    patch_project_review_state(
        tmp_path,
        project_id,
        segments={"seg-001": {"status": "approved", "note": "keep"}},
    )

    with pytest.raises(ValueError, match="no approved translation pairs"):
        build_translation_memory_assets(repo_root=tmp_path, project_id=project_id)


@pytest.mark.parametrize(
    "project_id,segment",
    [
        (
            "asset-memory-blank-source",
            {"id": "seg-001", "source": "", "draft": "译文"},
        ),
        (
            "asset-memory-blank-target",
            {"id": "seg-001", "source": "原文", "draft": "   "},
        ),
    ],
)
def test_approved_consumers_share_blank_content_eligibility(
    tmp_path,
    project_id,
    segment,
):
    # Legacy malformed manifests remain readable; new imports reject blank sources.
    save_project_manifest(
        tmp_path,
        {
            "project_id": project_id,
            "name": "Blank",
            "language_direction": "JP_TO_CN",
            "segments": [segment],
        },
    )
    identity = approval_identity(
        project_id=project_id,
        language_direction="JP_TO_CN",
        segment=segment,
    )
    patch_project_review_state(
        tmp_path,
        project_id,
        segments={
            "seg-001": {"status": "approved", "approval_identity": identity},
        },
    )

    with pytest.raises(ValueError, match="no approved segments"):
        run_export(
            tmp_path,
            source="manifest",
            project_id=project_id,
            status_mode="approved",
        )
    with pytest.raises(ValueError, match="no approved translation pairs"):
        build_translation_memory_assets(repo_root=tmp_path, project_id=project_id)


def test_run_source_translated_mode_can_deposit_completed_pairs(tmp_path):
    run_id = "run-memory-source"
    run_root = tmp_path / "workspace" / "runs" / run_id
    run_root.mkdir(parents=True)
    (run_root / "segments.json").write_text(
        json.dumps(
            {
                "language_direction": "JP_TO_CN",
                "chapters": [
                    {
                        "chapter_id": "ch-001",
                        "segments": [
                            {
                                "segment_id": "ch-001-seg-001",
                                "source_text": "主人公はレベル1だった。",
                                "draft_text": "主角是等级1。",
                                "status": "machine_translated",
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    doc = build_translation_memory_assets(
        repo_root=tmp_path,
        source_run=run_id,
        status_mode="translated",
    )

    assert doc["stats"]["pairs"] == 1
    assert doc["segment_map"]["ch-001-seg-001"] == "主角是等级1。"


def test_external_api_mode_requires_explicit_enablement(tmp_path, monkeypatch):
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    project_id = _seed_workbench_project(tmp_path)

    with pytest.raises(ExternalAssetExtractionUnavailable):
        build_translation_memory_assets(
            repo_root=tmp_path,
            project_id=project_id,
            mode="external_api",
        )


def test_prompt_builder_withholds_unscoped_asset_context():
    messages = build_batch_messages(
        [Segment(segment_id="seg-003", source_text="テスト")],
        chapter_label="章",
        asset_context="Term: アルファ => 阿尔法",
    )

    assert "withheld_unscoped" in messages[1].content
    assert "アルファ => 阿尔法" not in messages[1].content


def test_draft_run_rejects_unscoped_asset_and_preserves_it(tmp_path, monkeypatch):
    monkeypatch.setenv("CONTROLLED_RUN_ENABLED", "true")
    monkeypatch.setenv("REAL_API_TESTS_ENABLED", "false")
    asset_path = tmp_path / "workspace" / "assets" / "translation_memory" / "ctx.json"
    asset_path.parent.mkdir(parents=True)
    asset_path.write_text(
        json.dumps(
            {
                "asset_kind": "translation_memory",
                "context_prompt": "Term: アルファ => 阿尔法",
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    input_dir = tmp_path / "input_jp"
    input_dir.mkdir()
    (input_dir / "001-test.md").write_text("# 测试\n\n## 节\n\nアルファです。\n", encoding="utf-8")

    seen_messages: list[str] = []

    class StubProvider:
        provider_id = "stub"
        model_name = "stub-model"

        def __init__(self, cost_guard=None):
            self.cost_guard = cost_guard

        def generate(self, messages, options=None):  # noqa: ARG002
            from providers.types import ModelResult

            seen_messages.append(messages[1].content)
            fixed = {"items": [{"segment_id": "ch-001-seg-001", "translation": "这是阿尔法。"}]}
            result = ModelResult(
                provider_id=self.provider_id,
                model_name=self.model_name,
                raw_output=json.dumps(fixed, ensure_ascii=False),
                parsed_output=fixed,
            )
            result.mark_finished("ok")
            return result

    before = asset_path.read_bytes()
    with pytest.raises(ValueError, match="unscoped asset"):
        run_draft_stage_a(
            repo_root=tmp_path, input_dir=input_dir, limit_chapters=1,
            run_id="asset-context-run", provider_factory=lambda g: StubProvider(cost_guard=g),
            asset_context_path=asset_path,
        )
    assert seen_messages == [] and asset_path.read_bytes() == before
    assert not (tmp_path / "workspace/runs/asset-context-run").exists()
    from assets.translation_memory import load_translation_asset_context
    assert load_translation_asset_context(asset_path)["context_prompt"] == "Term: アルファ => 阿尔法"
    assert render_translation_asset_context(asset_path) == ""  # audit-readable, unproven consumption withheld


def test_r42_baseline_same_size_same_second_prompt_edit_is_fresh(tmp_path):
    import os
    from translation.configs_asset_context import build_configs_asset_context, _DOC_CACHE
    path=tmp_path/'glossary.yaml';chars=tmp_path/'absent.yaml'
    path.write_text('entries:\n- source_term: Alpha\n  target_term: Old\n')
    _DOC_CACHE.clear()
    first=build_configs_asset_context(['Alpha'],glossary_path=path,character_path=chars)
    stamp=path.stat();raw=path.read_bytes();path.write_bytes(raw.replace(b'Old',b'New'))
    os.utime(path,ns=(stamp.st_atime_ns,stamp.st_mtime_ns))
    second=build_configs_asset_context(['Alpha'],glossary_path=path,character_path=chars)
    assert 'Old' in first.text and 'New' in second.text and 'Old' not in second.text


def test_r42_baseline_changed_target_invalidates_only_affected_memory(tmp_path):
    from workbench.project_registry import get_project_manifest
    pid='machine-memory'
    rows=[{'id':'one','source':'First source sentence.','draft':'OLD first target.','status':'machine_translated'},
          {'id':'two','source':'Second source sentence.','draft':'Stable second target.','status':'machine_translated'}]
    create_project_manifest(tmp_path,project_id=pid,name='Synthetic',language_direction='JP_TO_CN',segments=rows)
    doc=build_translation_memory_assets(repo_root=tmp_path,project_id=pid,status_mode='translated')
    path=Path(doc['asset_path']);before=path.read_bytes()
    manifest=get_project_manifest(tmp_path,pid);payload=json.loads(manifest.path.read_text());payload['segments'][0]['draft']='NEW first target.'
    save_project_manifest(tmp_path,payload)
    rendered=render_translation_asset_context(path)
    assert 'OLD first target.' not in rendered and 'Stable second target.' in rendered
    assert path.read_bytes()==before


def test_r42_baseline_revoked_acceptance_withholds_old_memory(tmp_path):
    pid=_seed_workbench_project(tmp_path);doc=build_translation_memory_assets(repo_root=tmp_path,project_id=pid)
    patch_project_review_state(tmp_path,pid,segments={'seg-001':{'status':'rejected'}})
    assert render_translation_asset_context(Path(doc['asset_path']))==''


def test_r42_baseline_machine_pairs_are_not_called_approved(tmp_path):
    pid='unreviewed'
    create_project_manifest(tmp_path,project_id=pid,name='Synthetic',language_direction='JP_TO_CN',
        segments=[{'id':'one','source':'Synthetic source.','draft':'Synthetic target.','status':'machine_translated'}])
    doc=build_translation_memory_assets(repo_root=tmp_path,project_id=pid,status_mode='translated')
    assert doc.get('approved_pairs')==[] and len(doc.get('machine_pairs',[]))==1


def _r42_machine_project(repo):
    pid='dependency-memory'
    create_project_manifest(repo,project_id=pid,name='Synthetic',language_direction='JP_TO_CN',segments=[
        {'id':'one','source':'First source sentence.','draft':'First target.','status':'machine_translated'},
        {'id':'two','source':'Second source sentence.','draft':'Second target.','status':'machine_translated'}])
    return pid


@pytest.mark.parametrize('field,new',[('source','Other source sentence.'),('draft','Other target.'),('status','rejected')])
def test_r42_source_target_or_eligibility_change_is_scoped(tmp_path,field,new):
    from workbench.project_registry import get_project_manifest
    from assets.translation_memory import select_batch_context_hits
    pid=_r42_machine_project(tmp_path)
    doc=build_translation_memory_assets(repo_root=tmp_path,project_id=pid,status_mode='translated');path=Path(doc['asset_path'])
    manifest=get_project_manifest(tmp_path,pid);payload=json.loads(manifest.path.read_text())
    payload['segments'][0][field]=new;save_project_manifest(tmp_path,payload)
    # Source changes invalidate necessary context through the existing scope revision.
    rendered=render_translation_asset_context(path)
    assert 'First target.' not in rendered
    if field!='source': assert 'Second target.' in rendered
    hits=select_batch_context_hits(path,['First source sentence.','Second source sentence.'])
    assert 'First target.' not in hits


def test_r42_explicit_tm_withdrawal_is_scoped_and_auditable(tmp_path):
    pid=_r42_machine_project(tmp_path);doc=build_translation_memory_assets(repo_root=tmp_path,project_id=pid,status_mode='translated')
    path=Path(doc['asset_path']);saved=json.loads(path.read_text())
    saved['withdrawn_pair_ids']=[saved['translation_pairs'][0]['pair_id']]
    path.write_text(json.dumps(saved));before=path.read_bytes()
    result=render_translation_asset_context(path)
    assert 'First target.' not in result and 'Second target.' in result and path.read_bytes()==before
    saved['withdrawn']=True;path.write_text(json.dumps(saved));assert render_translation_asset_context(path)==''


@pytest.mark.parametrize('tamper',['payload','digest','duplicate','missing_source','legacy','direction'])
def test_r42_unknown_or_forged_tm_is_withheld(tmp_path,tamper):
    pid=_r42_machine_project(tmp_path);doc=build_translation_memory_assets(repo_root=tmp_path,project_id=pid,status_mode='translated')
    path=Path(doc['asset_path']);saved=json.loads(path.read_text());row=saved['translation_pairs'][0]
    if tamper=='payload': row['target_text']='FORGED target.'
    elif tamper=='digest': row['version_sha256']='0'*64
    elif tamper=='duplicate': saved['translation_pairs'].append(dict(row))
    elif tamper=='missing_source': saved['source_refs']=['manifest:unknown-project']
    elif tamper=='legacy': saved['schema_version']=1
    else:saved['language_direction']='CN_TO_JP'
    saved['context_prompt']='FORGED prompt';saved['term_candidates']=[{'source':'FORGED','target':'FORGED'}]
    path.write_text(json.dumps(saved));before=path.read_bytes();result=render_translation_asset_context(path)
    assert 'First target.' not in result and 'FORGED' not in result and path.read_bytes()==before


def _r42_run(repo, *, project_id=None, source='アルファの森へ向かう。', target='前往阿尔法之森。'):
    run=repo/'workspace/runs/run_synthetic_tm';run.mkdir(parents=True,exist_ok=True)
    payload={'language_direction':'JP_TO_CN','chapters':[{'chapter_id':'ch-001','segments':[
        {'segment_id':'seg-001','source_text':source,'draft_text':target,
         'refined_text':'STALE refined text must not win.','status':'machine_translated'}]}]}
    if project_id:payload['project_id']=project_id
    path=run/'segments.json';path.write_text(json.dumps(payload,ensure_ascii=False));return path


def test_r42_run_and_manifest_share_current_acceptance_eligibility(tmp_path):
    pid=_seed_workbench_project(tmp_path);run=_r42_run(tmp_path,project_id=pid)
    doc=build_translation_memory_assets(repo_root=tmp_path,source_run=run.parent.name)
    assert doc['approved_pairs'][0]['qualification']=='nonhuman_candidate'
    assert doc['approved_pairs'][0]['acceptance_provenance']['actor_type']=='agent'
    assert 'STALE' not in doc['context_prompt']
    path=Path(doc['asset_path']);assert '前往阿尔法之森' in render_translation_asset_context(path)
    patch_project_review_state(tmp_path,pid,segments={'seg-001':{'status':'rejected'}})
    assert render_translation_asset_context(path)==''


@pytest.mark.parametrize('mismatch',['source','target','direction','project','label_only','revoked_run'])
def test_r42_run_labels_or_mismatched_content_cannot_supply_acceptance(tmp_path,mismatch):
    pid=_seed_workbench_project(tmp_path);run=_r42_run(tmp_path,project_id=pid)
    data=json.loads(run.read_text());row=data['chapters'][0]['segments'][0]
    if mismatch=='source':row['source_text']='Other source.'
    elif mismatch=='target':row['draft_text']='Other target.'
    elif mismatch=='direction':data['language_direction']='CN_TO_JP'
    elif mismatch=='project':data['project_id']='unknown-project'
    elif mismatch=='revoked_run':row['status']='rejected'
    else:data.pop('project_id');row['status']='approved'
    run.write_text(json.dumps(data))
    with pytest.raises((ValueError,KeyError)):
        build_translation_memory_assets(repo_root=tmp_path,source_run=run.parent.name)


def test_r42_run_machine_mode_uses_draft_and_revalidates_content(tmp_path):
    run=_r42_run(tmp_path)
    doc=build_translation_memory_assets(repo_root=tmp_path,source_run=run.parent.name,status_mode='translated')
    assert doc['approved_pairs']==[] and doc['machine_pairs'][0]['qualification']=='unreviewed_translation'
    path=Path(doc['asset_path']);assert 'STALE' not in render_translation_asset_context(path)
    data=json.loads(run.read_text());data['chapters'][0]['segments'][0]['draft_text']='Changed target.'
    run.write_text(json.dumps(data));assert render_translation_asset_context(path)==''


def test_r42_external_asset_requires_explicit_repo_context(tmp_path):
    pid=_r42_machine_project(tmp_path);path=tmp_path/'chosen-local-output.json'
    build_translation_memory_assets(repo_root=tmp_path,project_id=pid,status_mode='translated',output_path=path)
    assert render_translation_asset_context(path)==''
    assert 'First target.' in render_translation_asset_context(path,repo_root=tmp_path)


def test_r42_prompt_dependencies_track_only_emitted_entries_and_withdrawal(tmp_path):
    from translation.configs_asset_context import build_configs_asset_context
    import yaml
    path=tmp_path/'glossary.yaml';chars=tmp_path/'characters.yaml'
    data={'entries':[{'source_term':'Alpha','target_term':'One','knowledge_claims':[{'claim_id':'c1','withdrawn':False}]},
                     {'source_term':'Beta','target_term':'Two'}]}
    chars.write_text('characters: []');path.write_text(yaml.safe_dump(data))
    def build():return build_configs_asset_context(['Alpha'],glossary_path=path,character_path=chars)
    first=build();data['entries'][1]['target_term']='Unrelated';path.write_text(yaml.safe_dump(data));other=build()
    assert first.dependency_versions==other.dependency_versions
    data['entries'][0]['knowledge_claims'][0]['withdrawn']=True;path.write_text(yaml.safe_dump(data));withdraw=build()
    assert first.text==withdraw.text and first.dependency_sha256!=withdraw.dependency_sha256
    data['entries'][0]['withdrawn']=True;path.write_text(yaml.safe_dump(data));assert build().empty


def test_r42_memory_reads_only_explicit_manifest_and_keeps_unrelated_data_unopened(tmp_path,monkeypatch):
    pid=_r42_machine_project(tmp_path)
    other=tmp_path/'workspace/manifests/unrelated.json';other.write_text('UNREADABLE UNRELATED DATA')
    original=Path.read_bytes;original_text=Path.read_text
    def checked(self,*args,**kwargs):
        assert self!=other
        return original(self,*args,**kwargs)
    def checked_text(self,*args,**kwargs):
        assert self!=other
        return original_text(self,*args,**kwargs)
    monkeypatch.setattr(Path,'read_bytes',checked);monkeypatch.setattr(Path,'read_text',checked_text)
    doc=build_translation_memory_assets(repo_root=tmp_path,project_id=pid,status_mode='translated')
    assert 'First target.' in render_translation_asset_context(Path(doc['asset_path']))


def test_r42_serialized_run_reference_cannot_open_outside_registered_roots(tmp_path,monkeypatch):
    pid=_r42_machine_project(tmp_path);doc=build_translation_memory_assets(repo_root=tmp_path,project_id=pid,status_mode='translated')
    path=Path(doc['asset_path']);outside=tmp_path/'unregistered';outside.mkdir();secret=outside/'segments.json'
    secret.write_text('MUST NOT BE READ')
    data=json.loads(path.read_text());data['source_refs']=['run:'+str(outside)];path.write_text(json.dumps(data))
    original=Path.read_text
    def checked(self,*args,**kwargs):
        assert self!=secret
        return original(self,*args,**kwargs)
    monkeypatch.setattr(Path,'read_text',checked)
    assert render_translation_asset_context(path)==''


def test_r42_malformed_tm_identity_withholds_instead_of_resurrecting_saved_prompt(tmp_path):
    pid=_r42_machine_project(tmp_path);doc=build_translation_memory_assets(repo_root=tmp_path,project_id=pid,status_mode='translated')
    path=Path(doc['asset_path']);data=json.loads(path.read_text())
    data['translation_pairs'][0]['pair_id']={'invalid':'identity'};data['context_prompt']='FORGED'
    path.write_text(json.dumps(data));text=render_translation_asset_context(path)
    assert 'First target.' not in text and 'Second target.' in text and 'FORGED' not in text


@pytest.mark.parametrize('kind,mutation',[('glossary','term'),('glossary','knowledge'),('glossary','withdraw'),
    ('character','term'),('character','missing'),('glossary','malformed')])
def test_r42_live_config_edits_invalidate_scoped_memory_without_manifest_rewrite(tmp_path,kind,mutation):
    import yaml
    from translation.source_versions import text_sha
    from workbench.project_registry import get_project_manifest
    from workbench.review_state import approval_identity
    pid=_r42_machine_project(tmp_path);manifest=get_project_manifest(tmp_path,pid)
    data=json.loads(manifest.path.read_text());data['dependency_versions']={'config:one':text_sha('placeholder')}
    data['dependency_sources']={'config:one':{'kind':kind,'entry':'Alpha'}}
    data['segments'][0]['dependency_keys']=['config:one'];data['segments'][1]['dependency_keys']=[]
    cfg=tmp_path/'workspace/configs';cfg.mkdir();path=cfg/('glossary.yaml' if kind=='glossary' else 'character_profile.yaml')
    field='entries' if kind=='glossary' else 'characters';idfield='source_term' if kind=='glossary' else 'name'
    entry={idfield:'Alpha','target_term':'One','knowledge_claims':[{'claim_id':'c','withdrawn':False}]}
    path.write_text(yaml.safe_dump({field:[entry]}));save_project_manifest(tmp_path,data)
    original=get_project_manifest(tmp_path,pid).segments[0]
    doc=build_translation_memory_assets(repo_root=tmp_path,project_id=pid,status_mode='translated');asset=Path(doc['asset_path'])
    before=manifest.path.read_bytes()
    if mutation=='term':entry['target_term']='New'
    elif mutation=='knowledge':entry['knowledge_claims'][0]['withdrawn']=True
    elif mutation=='withdraw':entry['withdrawn']=True
    if mutation=='missing':path.unlink()
    elif mutation=='malformed':path.write_text('entries: [unterminated')
    else:path.write_text(yaml.safe_dump({field:[entry]}))
    current=get_project_manifest(tmp_path,pid).segments[0]
    def identity(row):return approval_identity(project_id=pid,language_direction='JP_TO_CN',segment=row)
    assert identity(original)!=identity(current)
    text=render_translation_asset_context(asset)
    assert 'First target.' not in text and 'Second target.' in text
    assert manifest.path.read_bytes()==before


@pytest.mark.parametrize('mutation',['withdraw','source_changed','cycle'])
def test_r42_live_tm_dependency_is_validated_through_its_source(tmp_path,mutation):
    from translation.source_versions import text_sha
    from workbench.project_registry import get_project_manifest
    parent=_r42_machine_project(tmp_path);parentdoc=build_translation_memory_assets(repo_root=tmp_path,project_id=parent,status_mode='translated')
    parentpath=Path(parentdoc['asset_path']);pair=parentdoc['translation_pairs'][0]
    consumer=parent if mutation=='cycle' else 'tm-consumer'
    if consumer!=parent:
        create_project_manifest(tmp_path,project_id=consumer,name='Synthetic',language_direction='JP_TO_CN',segments=[
            {'id':'one','source':'Consumer source.','draft':'Consumer target.','status':'machine_translated'},
            {'id':'two','source':'Unrelated source.','draft':'Unrelated target.','status':'machine_translated'}])
    manifest=get_project_manifest(tmp_path,consumer);data=json.loads(manifest.path.read_text())
    data['dependency_versions']={'tm:one':text_sha('placeholder')}
    data['dependency_sources']={'tm:one':{'kind':'tm_pair','asset':parentpath.name,'pair_id':pair['pair_id']}}
    data['segments'][0]['dependency_keys']=['tm:one'];data['segments'][1]['dependency_keys']=[]
    save_project_manifest(tmp_path,data)
    if mutation=='cycle':
        current=get_project_manifest(tmp_path,parent)
        assert current.segments[0]['dependency_resolution_errors']==['tm:one']
        assert render_translation_asset_context(parentpath)=='' or 'First target.' not in render_translation_asset_context(parentpath)
        return
    child=build_translation_memory_assets(repo_root=tmp_path,project_id=consumer,status_mode='translated');childpath=Path(child['asset_path'])
    if mutation=='withdraw':
        saved=json.loads(parentpath.read_text());saved['withdrawn_pair_ids']=[pair['pair_id']];parentpath.write_text(json.dumps(saved))
    else:
        p=get_project_manifest(tmp_path,parent);changed=json.loads(p.path.read_text());changed['segments'][0]['draft']='Changed parent target.'
        save_project_manifest(tmp_path,changed)
    text=render_translation_asset_context(childpath)
    assert 'Consumer target.' not in text and 'Unrelated target.' in text


def test_r42_run_memory_revalidates_same_live_dependency_contract(tmp_path):
    from translation.source_versions import text_sha
    run=_r42_run(tmp_path);data=json.loads(run.read_text())
    data['dependency_sources']={'glossary:one':{'kind':'glossary','entry':'Alpha'}}
    data['dependency_versions']={'glossary:one':text_sha('placeholder')}
    data['chapters'][0]['segments'][0]['dependency_keys']=['glossary:one'];run.write_text(json.dumps(data))
    cfg=tmp_path/'workspace/configs';cfg.mkdir();path=cfg/'glossary.yaml'
    path.write_text('entries:\n- source_term: Alpha\n  target_term: One\n')
    doc=build_translation_memory_assets(repo_root=tmp_path,source_run=run.parent.name,status_mode='translated');asset=Path(doc['asset_path'])
    assert render_translation_asset_context(asset)
    before=run.read_bytes();path.write_text('entries:\n- source_term: Alpha\n  target_term: New\n')
    assert render_translation_asset_context(asset)=='' and run.read_bytes()==before


@pytest.mark.parametrize('route',['manifest','run'])
@pytest.mark.parametrize('mutation',['catalog','direct','unknown','bad_selection'])
def test_r42_malformed_runtime_dependency_does_not_discard_independent_rows(tmp_path,route,mutation):
    from translation.source_versions import text_sha
    from workbench.project_registry import get_project_manifest
    pid=_r42_machine_project(tmp_path)
    if route=='manifest':
        manifest=get_project_manifest(tmp_path,pid);source=manifest.path;data=json.loads(source.read_text());rows=data['segments']
    else:
        source=_r42_run(tmp_path);data=json.loads(source.read_text());rows=data['chapters'][0]['segments']
        rows[0].update(source_text='First source sentence.',draft_text='First target.',segment_id='one')
        rows.append({'segment_id':'two','source_text':'Second source sentence.','draft_text':'Second target.','status':'machine_translated'})
    data['dependency_versions']={'term:a':text_sha('v1'),'term:b':text_sha('v1')}
    rows[0]['dependency_keys']=['term:a'];rows[1]['dependency_keys']=['term:b'];source.write_text(json.dumps(data))
    kwargs={'project_id':pid} if route=='manifest' else {'source_run':source.parent.name}
    asset=Path(build_translation_memory_assets(repo_root=tmp_path,status_mode='translated',**kwargs)['asset_path'])
    if mutation=='catalog':data['dependency_versions']['term:a']='bad'
    elif mutation=='direct':rows[0].pop('dependency_keys');rows[0]['dependency_versions']={'term:a':'bad'}
    elif mutation=='unknown':rows[0]['dependency_keys']=['unknown:key']
    else:rows[0]['dependency_keys']=['term:a','term:a']
    source.write_text(json.dumps(data));before=source.read_bytes()
    text=render_translation_asset_context(asset)
    assert 'First target.' not in text and 'Second target.' in text
    assert source.read_bytes()==before
