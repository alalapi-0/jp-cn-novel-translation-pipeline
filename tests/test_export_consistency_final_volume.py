"""Synthetic security and compatibility tests for singleton final export."""

from __future__ import annotations

import fcntl
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent


def _load_modules():
    scripts_dir = REPO_ROOT / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        run_spec = importlib.util.spec_from_file_location(
            "run_consistency_fix_all_test", scripts_dir / "run_consistency_fix_all.py"
        )
        assert run_spec and run_spec.loader
        run_mod = importlib.util.module_from_spec(run_spec)
        sys.modules[run_spec.name] = run_mod
        run_spec.loader.exec_module(run_mod)
        sys.modules["run_consistency_fix_all"] = run_mod
        export_spec = importlib.util.spec_from_file_location(
            "export_consistency_final_volume_test",
            scripts_dir / "export_consistency_final_volume.py",
        )
        assert export_spec and export_spec.loader
        exporter = importlib.util.module_from_spec(export_spec)
        sys.modules[export_spec.name] = exporter
        export_spec.loader.exec_module(exporter)
        return run_mod, exporter
    finally:
        sys.path.pop(0)


def _load_fixer():
    scripts_dir = REPO_ROOT / "scripts"
    sys.path.insert(0, str(scripts_dir))
    try:
        spec = importlib.util.spec_from_file_location(
            "fix_terminology_consistency_test", scripts_dir / "fix_terminology_consistency.py"
        )
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    finally:
        sys.path.pop(0)


def _fixture(root: Path, numbers=(1, 3)) -> Path:
    source = root / "input_jp"
    source.mkdir(parents=True)
    for number in numbers:
        (source / f"{number:03d}-source.md").write_text("synthetic source\n", encoding="utf-8")
    segments = root / "workspace/runs/run_fixture_draft_stage_b_50ch/segments.json"
    segments.parent.mkdir(parents=True)
    chapters = [
        {
            "chapter_id": f"ch-{number:03d}",
            "chapter_label": f"chapter {number}",
            "source_path": f"input_jp/{number:03d}-source.md",
            "segments": [
                {
                    "segment_id": f"ch-{number:03d}-seg-001",
                    "source_text": "synthetic source",
                    "refined_text": f"synthetic translation {number}",
                }
            ],
        }
        for number in numbers
    ]
    segments.write_text(json.dumps({"chapters": chapters}), encoding="utf-8")
    return segments


def _bind(root: Path):
    run_mod, exporter = _load_modules()
    run_mod.REPO_ROOT = root
    exporter.REPO_ROOT = root
    return run_mod, exporter


def _sentinels(output: Path) -> tuple[Path, Path]:
    singleton = output / "translated/full_volume_cn.md"
    singleton.parent.mkdir(parents=True)
    singleton.write_bytes(b"# 1 prior\n\nold one\n\n# 3 prior\n\nold three\n")
    manifest = output / "final_export_manifest.json"
    manifest.write_bytes(b"old manifest sentinel\n")
    return singleton, manifest


def test_fresh_export_preserves_singleton_manifest_contract_and_leaves_no_residue(tmp_path):
    _fixture(tmp_path)
    _run, exporter = _bind(tmp_path)
    output = tmp_path / "output_cn"
    manifest = exporter.export_final(output)
    assert manifest["schema"] == "consistency_final_export_v2"
    assert manifest["canonical_final_translation_count"] == 1
    assert manifest["final_translation_policy"] == "singleton_full_volume_cn"
    assert manifest["chapters_exported"] == 2
    assert manifest["chapters_missing"] == manifest["chapters_incomplete"] == []
    assert manifest["full_volume_cn"] == "output_cn/translated/full_volume_cn.md"
    assert json.loads((output / "final_export_manifest.json").read_text()) == manifest
    assert sorted(path.name for path in (output / "translated").iterdir()) == ["full_volume_cn.md"]
    assert not list(output.glob(f"{exporter.TRANSACTION_PREFIX}*"))
    assert not [path for path in output.rglob(".*") if path.name != ".gitkeep"]


def test_auxiliary_flags_remain_manifest_compatible(tmp_path):
    _fixture(tmp_path, (1,))
    _run, exporter = _bind(tmp_path)
    output = tmp_path / "output_cn"
    manifest = exporter.export_final(output, include_chapters=True, include_bilingual=True)
    assert manifest["include_chapters"] is True
    assert manifest["include_bilingual"] is True
    assert manifest["chapter_files_exported"] == 1
    assert manifest["bilingual_chapter_files_exported"] == 1
    assert (output / "translated/chapter_001_cn.md").is_file()
    assert (output / "bilingual/full_volume_bilingual.md").is_file()


def test_missing_or_incomplete_canonical_preserves_public_sentinels(tmp_path):
    _fixture(tmp_path, (1,))
    segments = next(tmp_path.glob("workspace/runs/*/segments.json"))
    segments.write_text(json.dumps({"chapters": []}), encoding="utf-8")
    _run, exporter = _bind(tmp_path)
    singleton, manifest = _sentinels(tmp_path / "output_cn")
    with pytest.raises(RuntimeError, match="missing"):
        exporter.export_final(tmp_path / "output_cn")
    assert singleton.read_bytes().startswith(b"# 1 prior")
    assert manifest.read_bytes() == b"old manifest sentinel\n"


def test_source_and_public_ancestry_symlinks_fail_closed(tmp_path):
    external = tmp_path / "external"
    external.mkdir()
    (external / "001-source.md").write_bytes(b"external source sentinel")
    (tmp_path / "input_jp").symlink_to(external, target_is_directory=True)
    _run, exporter = _bind(tmp_path)
    with pytest.raises(RuntimeError, match="symlink"):
        exporter.export_final(tmp_path / "output_cn")
    assert (external / "001-source.md").read_bytes() == b"external source sentinel"


def test_public_singleton_symlink_target_is_unchanged(tmp_path):
    _fixture(tmp_path, (1,))
    _run, exporter = _bind(tmp_path)
    external = tmp_path / "external.md"
    external.write_bytes(b"external output sentinel")
    singleton = tmp_path / "output_cn/translated/full_volume_cn.md"
    singleton.parent.mkdir(parents=True)
    singleton.symlink_to(external)
    with pytest.raises(RuntimeError, match="symlink"):
        exporter.export_final(tmp_path / "output_cn")
    assert external.read_bytes() == b"external output sentinel"


def test_active_kernel_lock_contends_and_persistent_unlocked_inode_is_reused(tmp_path):
    _fixture(tmp_path, (1,))
    _run, exporter = _bind(tmp_path)
    from consistency_transaction_lock import exclusive_consistency_lock

    with exclusive_consistency_lock(tmp_path):
        lock_path = tmp_path / ".agent_runtime/locks/consistency_transaction.lock"
        identity = lock_path.stat().st_ino
        with pytest.raises(RuntimeError, match="holds the lock"):
            exporter.export_final(tmp_path / "output_cn")
        assert lock_path.stat().st_ino == identity
    exporter.export_final(tmp_path / "output_cn")
    assert lock_path.stat().st_ino == identity


def test_runner_passes_exact_locked_descriptor_to_direct_child(tmp_path, monkeypatch):
    segments = _fixture(tmp_path, (1,))
    run_mod, _exporter = _bind(tmp_path)
    monkeypatch.setattr(run_mod, "discover_canonical_files", lambda: [segments])
    observed = {}

    def child(_cmd, **kwargs):
        assert "--expected-dev" in _cmd and "--expected-ino" in _cmd
        fd = kwargs["pass_fds"][0]
        observed["fd"] = fd
        observed["env"] = kwargs["env"]["LIGHT_NOVEL_CONSISTENCY_LOCK_FD"]
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {
                    "changed_segments": 0,
                    "total_segments": 1,
                    "rule_hits": {},
                    "skipped_ambiguous_hits": {},
                }
            ),
            stderr="",
        )

    monkeypatch.setattr(run_mod.subprocess, "run", child)
    assert run_mod.main(["--dry-run"]) == 0
    assert observed["env"] == str(observed["fd"])


def test_runner_refreshes_identity_between_sparse_jobs_after_atomic_replace(tmp_path, monkeypatch):
    segments = _fixture(tmp_path, (1, 3))
    run_mod, _exporter = _bind(tmp_path)
    monkeypatch.setattr(run_mod, "discover_canonical_files", lambda: [segments])
    seen = []

    def child(cmd, **_kwargs):
        expected = (int(cmd[cmd.index("--expected-dev") + 1]), int(cmd[cmd.index("--expected-ino") + 1]))
        seen.append(expected)
        if len(seen) == 1:
            replacement = segments.with_name("replacement.json")
            replacement.write_bytes(segments.read_bytes())
            os.replace(replacement, segments)
        return SimpleNamespace(returncode=0, stdout=json.dumps({"changed_segments": 0, "total_segments": 1, "rule_hits": {}, "skipped_ambiguous_hits": {}}), stderr="")

    monkeypatch.setattr(run_mod.subprocess, "run", child)
    assert run_mod.main(["--dry-run"]) == 0
    assert len(seen) == 2 and seen[0] != seen[1]


@pytest.mark.parametrize("kind", ["regular", "symlink"])
def test_runner_unpredictable_diff_collision_preserves_foreign(tmp_path, monkeypatch, kind):
    segments = _fixture(tmp_path, (1,))
    run_mod, _exporter = _bind(tmp_path)
    monkeypatch.setattr(run_mod, "discover_canonical_files", lambda: [segments])
    monkeypatch.setattr(run_mod.secrets, "token_hex", lambda _size: "fixedcollisiontoken")
    final = tmp_path / "combined.json"
    collision = tmp_path / ".combined.json.job-000.fixedcollisiontoken.json"
    external = tmp_path / "external-diff.json"
    external.write_bytes(b"external sentinel")
    if kind == "regular":
        collision.write_bytes(b"foreign collision")
    else:
        collision.symlink_to(external)
    with pytest.raises(FileExistsError):
        run_mod.main(["--dry-run", "--diff-log", str(final)])
    if kind == "regular":
        assert collision.read_bytes() == b"foreign collision"
    else:
        assert collision.is_symlink() and external.read_bytes() == b"external sentinel"
    assert not final.exists()
    assert sorted(tmp_path.glob(".combined.json.job-000.*.json")) == [collision]


def test_runner_child_failure_cleans_only_bound_temp_identity(tmp_path, monkeypatch):
    segments = _fixture(tmp_path, (1,))
    run_mod, _exporter = _bind(tmp_path)
    monkeypatch.setattr(run_mod, "discover_canonical_files", lambda: [segments])
    monkeypatch.setattr(run_mod.subprocess, "run", lambda *_a, **_k: SimpleNamespace(returncode=7, stdout="", stderr=""))
    final = tmp_path / "combined.json"
    assert run_mod.main(["--dry-run", "--diff-log", str(final)]) == 1
    assert not final.exists()
    assert not list(tmp_path.glob(".combined.json.job-*.json"))


@pytest.mark.parametrize("boundary", ["validation", "publish", "quarantine"])
def test_injected_precommit_failure_rolls_back_old_public_set(tmp_path, monkeypatch, boundary):
    _fixture(tmp_path)
    _run, exporter = _bind(tmp_path)
    singleton, manifest = _sentinels(tmp_path / "output_cn")
    stale = singleton.with_name("chapter_999_cn.md")
    stale.write_bytes(b"stale sentinel")
    original = (singleton.read_bytes(), manifest.read_bytes(), stale.read_bytes())
    fired = False

    def inject(name):
        nonlocal fired
        if name == boundary and not fired:
            fired = True
            raise RuntimeError(f"injected {boundary}")

    monkeypatch.setattr(exporter, "_inject", inject)
    with pytest.raises(RuntimeError, match="injected"):
        exporter.export_final(tmp_path / "output_cn")
    assert fired
    assert (singleton.read_bytes(), manifest.read_bytes(), stale.read_bytes()) == original
    assert not list((tmp_path / "output_cn").glob(f"{exporter.TRANSACTION_PREFIX}*"))


def test_interrupted_rollback_is_mechanically_recovered_on_next_export(tmp_path, monkeypatch):
    _fixture(tmp_path)
    _run, exporter = _bind(tmp_path)
    singleton, manifest = _sentinels(tmp_path / "output_cn")
    old = singleton.read_bytes(), manifest.read_bytes()
    real_finish = exporter._finish_transaction

    def stop_publish(name):
        if name == "publish":
            raise RuntimeError("synthetic process interruption")

    monkeypatch.setattr(exporter, "_inject", stop_publish)
    monkeypatch.setattr(
        exporter,
        "_finish_transaction",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("recovery deferred")),
    )
    with pytest.raises(RuntimeError, match="recovery deferred"):
        exporter.export_final(tmp_path / "output_cn")
    assert list((tmp_path / "output_cn").glob(f"{exporter.TRANSACTION_PREFIX}*"))

    monkeypatch.setattr(exporter, "_inject", lambda _name: None)
    monkeypatch.setattr(exporter, "_finish_transaction", real_finish)
    exporter.export_final(tmp_path / "output_cn")
    assert singleton.read_bytes() != old[0]
    assert b"synthetic translation 1" in singleton.read_bytes()
    assert b"old one" not in singleton.read_bytes()
    assert manifest.read_bytes() != old[1]
    assert not list((tmp_path / "output_cn").glob(f"{exporter.TRANSACTION_PREFIX}*"))


def test_cleanup_identity_change_never_unlinks_external_target(tmp_path, monkeypatch):
    _fixture(tmp_path, (1,))
    _run, exporter = _bind(tmp_path)
    output = tmp_path / "output_cn"
    external = tmp_path / "external-cleanup.md"
    external.write_bytes(b"external cleanup sentinel")
    changed = False

    def inject(name):
        nonlocal changed
        if name == "cleanup" and not changed:
            transaction = next(output.glob(f"{exporter.TRANSACTION_PREFIX}*"))
            victim = next(path for path in transaction.iterdir() if path.name.startswith("old-"))
            victim.unlink()
            victim.symlink_to(external)
            changed = True

    _sentinels(output)
    monkeypatch.setattr(exporter, "_inject", inject)
    with pytest.raises(RuntimeError, match="cleanup identity changed|not a regular file"):
        exporter.export_final(output)
    assert changed
    assert external.read_bytes() == b"external cleanup sentinel"


def test_publish_conflict_preserves_foreign_entry_and_bounded_recovery_state(tmp_path, monkeypatch):
    _fixture(tmp_path, (1,))
    _run, exporter = _bind(tmp_path)
    output = tmp_path / "output_cn"
    _sentinels(output)
    manifest = output / "final_export_manifest.json"
    foreign = b"foreign publish sentinel"
    original_publish = exporter._rename_entry_noreplace_between
    fired = False

    def conflict(source_fd, source, destination_fd, destination):
        nonlocal fired
        if destination == manifest.name and not fired:
            manifest.write_bytes(foreign)
            fired = True
        return original_publish(source_fd, source, destination_fd, destination)

    monkeypatch.setattr(exporter, "_rename_entry_noreplace_between", conflict)
    with pytest.raises(RuntimeError, match="foreign public entry"):
        exporter.export_final(output)
    assert manifest.read_bytes() == foreign
    assert list(output.glob(f"{exporter.TRANSACTION_PREFIX}*"))


def test_missing_atomic_platform_primitive_fails_without_unsafe_fallback(tmp_path, monkeypatch):
    _fixture(tmp_path, (1,))
    _run, exporter = _bind(tmp_path)
    singleton, manifest = _sentinels(tmp_path / "output_cn")
    old = singleton.read_bytes(), manifest.read_bytes()
    monkeypatch.setattr(exporter, "_renameat_with_flags", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("unsupported")))
    with pytest.raises(RuntimeError, match="unsupported"):
        exporter.export_final(tmp_path / "output_cn")
    assert (singleton.read_bytes(), manifest.read_bytes()) == old


def test_regular_destination_substitution_after_preflight_is_rejected(tmp_path, monkeypatch):
    _fixture(tmp_path, (1,))
    _run, exporter = _bind(tmp_path)
    output = tmp_path / "output_cn"
    singleton, manifest = _sentinels(output)
    substitute = output / "substitute.json"
    substitute.write_bytes(b"substitute sentinel")
    real_assert = exporter._assert_output_entry_identity
    fired = False

    def substitute_once(directory_fd, name, expected, *, context):
        nonlocal fired
        if context == "manifest destination" and not fired:
            manifest.rename(output / "original-aside.json")
            substitute.rename(manifest)
            fired = True
        return real_assert(directory_fd, name, expected, context=context)

    monkeypatch.setattr(exporter, "_assert_output_entry_identity", substitute_once)
    with pytest.raises(RuntimeError, match="identity changed"):
        exporter.export_final(output)
    assert manifest.read_bytes() == b"substitute sentinel"
    assert singleton.read_bytes().startswith(b"# 1 prior")


def test_strict_source_discovery_suffixes_junk_duplicates_and_nonregular(tmp_path):
    run_mod, _exporter = _bind(tmp_path)
    source = tmp_path / "input_jp"
    source.mkdir()
    (source / "001-one.MD").write_text("x")
    (source / "2-two.TxT").write_text("x")
    (source / "README.md").write_text("junk")
    (source / "3.json").write_text("junk")
    assert run_mod.discover_active_chapter_numbers(source) == {1, 2}
    (source / "1-duplicate.txt").write_text("x")
    with pytest.raises(RuntimeError, match="duplicate normalized"):
        run_mod.discover_active_chapter_numbers(source)
    (source / "1-duplicate.txt").unlink()
    (source / "003-dir.md").mkdir()
    with pytest.raises(RuntimeError, match="regular file"):
        run_mod.discover_active_chapter_numbers(source)


def test_numbered_source_symlink_and_missing_empty_corpus_reject(tmp_path):
    run_mod, _exporter = _bind(tmp_path)
    source = tmp_path / "input_jp"
    with pytest.raises(RuntimeError):
        run_mod.discover_active_chapter_numbers(source)
    source.mkdir()
    with pytest.raises(RuntimeError):
        run_mod.discover_active_chapter_numbers(source)
    external = tmp_path / "external.md"
    external.write_bytes(b"external")
    (source / "001-link.md").symlink_to(external)
    with pytest.raises(RuntimeError, match="regular file"):
        run_mod.discover_active_chapter_numbers(source)
    assert external.read_bytes() == b"external"


def test_sparse_jobs_exclude_stale_ids_and_reject_malformed_duplicates(tmp_path):
    run_mod, _exporter = _bind(tmp_path)
    first = _fixture(tmp_path, (1, 3))
    assert run_mod.build_chapter_jobs([first], {1, 3}) == [(first, 1, 1), (first, 3, 3)]
    doc = json.loads(first.read_text())
    doc["chapters"].append({"chapter_id": "ch-999", "segments": []})
    first.write_text(json.dumps(doc))
    assert run_mod.build_chapter_jobs([first], {1, 3}) == [(first, 1, 1), (first, 3, 3)]
    doc["chapters"][0]["chapter_id"] = "chapter-1"
    first.write_text(json.dumps(doc))
    with pytest.raises(RuntimeError, match="malformed canonical"):
        run_mod.build_chapter_jobs([first], {1})
    doc["chapters"][0]["chapter_id"] = "ch-1"
    doc["chapters"][1]["chapter_id"] = "ch-001"
    first.write_text(json.dumps(doc))
    with pytest.raises(RuntimeError, match="duplicate normalized"):
        run_mod.build_chapter_jobs([first], {1})


@pytest.mark.parametrize("mode", ["child-failure", "bad-summary"])
def test_runner_failure_has_no_success_diff(tmp_path, monkeypatch, mode):
    segments = _fixture(tmp_path, (1,))
    run_mod, _exporter = _bind(tmp_path)
    monkeypatch.setattr(run_mod, "discover_canonical_files", lambda: [segments])
    if mode == "child-failure":
        result = SimpleNamespace(returncode=9, stdout="", stderr="secret detail")
    else:
        result = SimpleNamespace(returncode=0, stdout="{}", stderr="")
    monkeypatch.setattr(run_mod.subprocess, "run", lambda *_a, **_k: result)
    diff = tmp_path / "diff.json"
    assert run_mod.main(["--diff-log", str(diff)]) == 1
    assert not diff.exists()
    assert not list(tmp_path.glob(".diff.json*"))


def test_cross_file_canonical_ambiguity_preserves_prior_outputs(tmp_path, monkeypatch):
    first = _fixture(tmp_path, (1,))
    second = tmp_path / "workspace/runs/run_second_draft_stage_b_50ch/segments.json"
    second.parent.mkdir(parents=True)
    second.write_bytes(first.read_bytes())
    _run, exporter = _bind(tmp_path)
    monkeypatch.setattr(exporter, "discover_canonical_files", lambda: [first, second])
    singleton, manifest = _sentinels(tmp_path / "output_cn")
    old = singleton.read_bytes(), manifest.read_bytes()
    with pytest.raises(RuntimeError, match="ambiguous active canonical"):
        exporter.export_final(tmp_path / "output_cn")
    assert (singleton.read_bytes(), manifest.read_bytes()) == old


@pytest.mark.parametrize(
    "body",
    [b"preamble\n# 1 x\n\na\n", b"# 1 x\n\na\n# 01 duplicate\n\nb\n", b"# malformed\n\na\n"],
)
def test_malformed_existing_singleton_rejects_before_mutation(tmp_path, body):
    _fixture(tmp_path, (1,))
    _run, exporter = _bind(tmp_path)
    singleton, manifest = _sentinels(tmp_path / "output_cn")
    singleton.write_bytes(body)
    stale = singleton.with_name("chapter_999_cn.md")
    stale.write_bytes(b"stale")
    with pytest.raises(RuntimeError):
        exporter.export_final(tmp_path / "output_cn")
    assert singleton.read_bytes() == body
    assert manifest.read_bytes() == b"old manifest sentinel\n"
    assert stale.read_bytes() == b"stale"


def test_rogue_fresh_heading_rejects_before_cleanup(tmp_path):
    segments = _fixture(tmp_path, (1,))
    doc = json.loads(segments.read_text())
    doc["chapters"][0]["segments"][0]["refined_text"] = "ok\n\n# rogue\n"
    segments.write_text(json.dumps(doc))
    _run, exporter = _bind(tmp_path)
    output = tmp_path / "output_cn"
    stale = output / "bilingual/chapter_999_bilingual.md"
    stale.parent.mkdir(parents=True)
    stale.write_bytes(b"stale")
    with pytest.raises(RuntimeError, match="malformed top-level"):
        exporter.export_final(output)
    assert stale.read_bytes() == b"stale"


def test_existing_singleton_is_rebuilt_from_current_canonical_segments(tmp_path):
    _fixture(tmp_path, (1, 3))
    _run, exporter = _bind(tmp_path)
    output = tmp_path / "output_cn"
    singleton = output / "translated/full_volume_cn.md"
    singleton.parent.mkdir(parents=True)
    retained = b"# 1 old\r\n\r\nexact one\r\n# 3 old\n\nexact three\n"
    singleton.write_bytes(retained + b"# 999 stale\n\nstale\n")
    exporter.export_final(output)
    rebuilt = singleton.read_bytes()
    assert rebuilt != retained
    assert rebuilt == (
        b"# 1 chapter 1\n\nsynthetic translation 1\n"
        b"# 3 chapter 3\n\nsynthetic translation 3\n"
    )
    assert b"exact one" not in rebuilt and b"# 999" not in rebuilt


def test_changed_canonical_text_replaces_valid_old_singleton(tmp_path):
    segments = _fixture(tmp_path, (1,))
    _run, exporter = _bind(tmp_path)
    output = tmp_path / "output_cn"
    singleton = output / "translated/full_volume_cn.md"
    singleton.parent.mkdir(parents=True)
    singleton.write_bytes(b"# 1 old valid\n\nold canonical bytes\n")
    doc = json.loads(segments.read_text())
    doc["chapters"][0]["segments"][0]["refined_text"] = "new canonical bytes"
    segments.write_text(json.dumps(doc))
    exporter.export_final(output)
    assert singleton.read_bytes() == b"# 1 chapter 1\n\nnew canonical bytes\n"


def test_preflight_finishes_before_plan_or_cleanup(tmp_path, monkeypatch):
    _fixture(tmp_path, (1,))
    _run, exporter = _bind(tmp_path)
    _sentinels(tmp_path / "output_cn")
    events = []
    real_filter = exporter._filter_existing_singleton
    monkeypatch.setattr(exporter, "_filter_existing_singleton", lambda *a, **k: (events.append("filter"), real_filter(*a, **k))[1])
    monkeypatch.setattr(exporter, "_inject", lambda name: events.append(name))
    exporter.export_final(tmp_path / "output_cn")
    assert events[0] == "filter"
    assert events.index("validation") < events.index("plan") < events.index("quarantine")
    assert events.index("publish") < events.index("committed") < events.index("cleanup")


def test_same_bytes_foreign_public_substitution_fails_closed(tmp_path, monkeypatch):
    _fixture(tmp_path, (1,))
    _run, exporter = _bind(tmp_path)
    output = tmp_path / "output_cn"
    _sentinels(output)
    real_publish = exporter._rename_entry_noreplace_between
    fired = False

    def substitute(source_fd, source, destination_fd, destination):
        nonlocal fired
        if destination == "final_export_manifest.json" and not fired:
            staged = exporter._read_fd_bytes(source_fd, source)
            (output / destination).write_bytes(staged)
            fired = True
        return real_publish(source_fd, source, destination_fd, destination)

    monkeypatch.setattr(exporter, "_rename_entry_noreplace_between", substitute)
    with pytest.raises(RuntimeError, match="foreign public entry"):
        exporter.export_final(output)
    assert fired


def test_real_subprocess_inherited_ofd_and_direct_fixer_contention(tmp_path):
    _fixture(tmp_path, (1,))
    from consistency_transaction_lock import INHERITED_LOCK_FD_ENV, exclusive_consistency_lock

    scripts = REPO_ROOT / "scripts"
    with exclusive_consistency_lock(REPO_ROOT) as lock:
        env = os.environ.copy()
        env[INHERITED_LOCK_FD_ENV] = str(lock.fd)
        inherited = subprocess.run(
            [sys.executable, "-c", "from pathlib import Path; from consistency_transaction_lock import exclusive_consistency_lock;\nwith exclusive_consistency_lock(Path(__import__('sys').argv[1])): print('held')", str(REPO_ROOT)],
            cwd=scripts,
            env=env,
            pass_fds=(lock.fd,),
            capture_output=True,
            text=True,
        )
        assert inherited.returncode == 0 and inherited.stdout.strip() == "held"
        blocked = subprocess.run(
            [sys.executable, str(scripts / "fix_terminology_consistency.py"), "--segments-file", str(next(tmp_path.glob("workspace/runs/*/segments.json"))), "--chapters", "1", "1", "--dry-run"],
            cwd=REPO_ROOT,
            env={key: value for key, value in os.environ.items() if key != INHERITED_LOCK_FD_ENV},
            capture_output=True,
            text=True,
        )
        assert blocked.returncode != 0
        assert "holds the lock" in blocked.stderr


@pytest.mark.parametrize("stage", ["plan", "quarantine", "publish", "committed"])
def test_deferred_crash_states_recover_under_fresh_lock(tmp_path, monkeypatch, stage):
    _fixture(tmp_path, (1,))
    _run, exporter = _bind(tmp_path)
    output = tmp_path / "output_cn"
    singleton, manifest = _sentinels(output)
    real_finish = exporter._finish_transaction
    fired = False

    def crash(name):
        nonlocal fired
        if name == stage and not fired:
            fired = True
            raise RuntimeError("simulated crash")

    monkeypatch.setattr(exporter, "_inject", crash)
    monkeypatch.setattr(exporter, "_finish_transaction", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("deferred")))
    with pytest.raises(RuntimeError):
        exporter.export_final(output)
    assert fired and list(output.glob(f"{exporter.TRANSACTION_PREFIX}*"))
    monkeypatch.setattr(exporter, "_inject", lambda _name: None)
    monkeypatch.setattr(exporter, "_finish_transaction", real_finish)
    exporter.export_final(output)
    assert singleton.is_file() and manifest.is_file()
    assert not list(output.glob(f"{exporter.TRANSACTION_PREFIX}*"))
    assert not [path for path in output.rglob(".*") if path.name != ".gitkeep"]


@pytest.mark.parametrize("kind", ["regular", "symlink"])
def test_recovery_restore_noreplace_preserves_substitute(tmp_path, monkeypatch, kind):
    _fixture(tmp_path, (1,))
    _run, exporter = _bind(tmp_path)
    output = tmp_path / "output_cn"
    singleton, manifest = _sentinels(output)
    old_singleton = singleton.read_bytes()
    old_manifest = manifest.read_bytes()
    real_finish = exporter._finish_transaction

    monkeypatch.setattr(
        exporter,
        "_inject",
        lambda name: (_ for _ in ()).throw(RuntimeError("crash"))
        if name == "quarantine"
        else None,
    )
    monkeypatch.setattr(
        exporter,
        "_finish_transaction",
        lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("deferred")),
    )
    with pytest.raises(RuntimeError, match="deferred"):
        exporter.export_final(output)
    assert list(output.glob(f"{exporter.TRANSACTION_PREFIX}*"))

    external = tmp_path / "restore-external"
    external.write_bytes(b"external restore sentinel")
    substituted = None

    def substitute(name):
        nonlocal substituted
        if name != "restore-original" or substituted is not None:
            return
        for candidate in (manifest, singleton):
            if not candidate.exists() and not candidate.is_symlink():
                substituted = candidate
                if kind == "regular":
                    candidate.write_bytes(b"foreign restore sentinel")
                else:
                    candidate.symlink_to(external)
                return

    monkeypatch.setattr(exporter, "_inject", substitute)
    monkeypatch.setattr(exporter, "_finish_transaction", real_finish)
    with pytest.raises(RuntimeError, match="destination appeared during recovery"):
        exporter.export_final(output)
    assert substituted is not None
    if kind == "regular":
        assert substituted.read_bytes() == b"foreign restore sentinel"
    else:
        assert substituted.is_symlink()
        assert external.read_bytes() == b"external restore sentinel"
    # The other original may already have been restored, but no foreign entry
    # is clobbered and the transaction remains bounded/recoverable.
    if singleton.exists() and singleton != substituted:
        assert singleton.read_bytes() == old_singleton
    if manifest.exists() and manifest != substituted:
        assert manifest.read_bytes() == old_manifest
    assert list(output.glob(f"{exporter.TRANSACTION_PREFIX}*"))


@pytest.mark.parametrize(
    "mutate",
    [
        lambda doc: doc["planned"][0].update(area="escape"),
        lambda doc: doc["planned"][0].update(name="../escape"),
        lambda doc: doc["planned"][0].update(sha256="BAD"),
        lambda doc: doc["planned"].append(dict(doc["planned"][0])),
        lambda doc: doc["planned"][0].update(ino="1"),
    ],
)
def test_corrupt_journal_fails_closed(tmp_path, monkeypatch, mutate):
    _fixture(tmp_path, (1,))
    _run, exporter = _bind(tmp_path)
    output = tmp_path / "output_cn"
    _sentinels(output)
    real_finish = exporter._finish_transaction
    monkeypatch.setattr(exporter, "_inject", lambda name: (_ for _ in ()).throw(RuntimeError("crash")) if name == "plan" else None)
    monkeypatch.setattr(exporter, "_finish_transaction", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("deferred")))
    with pytest.raises(RuntimeError):
        exporter.export_final(output)
    txn = next(output.glob(f"{exporter.TRANSACTION_PREFIX}*"))
    journal = txn / "journal.json"
    doc = json.loads(journal.read_text())
    mutate(doc)
    journal.write_text(json.dumps(doc))
    monkeypatch.setattr(exporter, "_inject", lambda _name: None)
    monkeypatch.setattr(exporter, "_finish_transaction", real_finish)
    with pytest.raises(RuntimeError, match="journal|transaction|duplicated|invalid"):
        exporter.export_final(output)


@pytest.mark.parametrize("window", ["prep-created", "prep-plan", "prep-journal", "prep-ready"])
def test_initialization_window_failure_is_clean_and_not_scanned(tmp_path, monkeypatch, window):
    _fixture(tmp_path, (1,))
    _run, exporter = _bind(tmp_path)
    output = tmp_path / "output_cn"
    singleton, manifest = _sentinels(output)
    old = singleton.read_bytes(), manifest.read_bytes()
    fired = False

    def fail(name):
        nonlocal fired
        if name == window and not fired:
            fired = True
            raise RuntimeError("init-window")

    monkeypatch.setattr(exporter, "_inject", fail)
    with pytest.raises(RuntimeError, match="init-window"):
        exporter.export_final(output)
    assert fired and (singleton.read_bytes(), manifest.read_bytes()) == old
    assert not list(output.glob(f"{exporter.TRANSACTION_PREFIX}*"))
    assert not list(output.glob(f"{exporter.PREPARATION_PREFIX}*"))
    monkeypatch.setattr(exporter, "_inject", lambda _name: None)
    exporter.export_final(output)
    assert manifest.read_bytes() != old[1]


def test_recovery_precedes_new_canonical_validation(tmp_path, monkeypatch):
    segments = _fixture(tmp_path, (1,))
    _run, exporter = _bind(tmp_path)
    output = tmp_path / "output_cn"
    singleton, manifest = _sentinels(output)
    old = singleton.read_bytes(), manifest.read_bytes()
    real_finish = exporter._finish_transaction
    monkeypatch.setattr(exporter, "_inject", lambda name: (_ for _ in ()).throw(RuntimeError("crash")) if name == "publish" else None)
    monkeypatch.setattr(exporter, "_finish_transaction", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("deferred")))
    with pytest.raises(RuntimeError):
        exporter.export_final(output)
    segments.write_text("not json", encoding="utf-8")
    monkeypatch.setattr(exporter, "_inject", lambda _name: None)
    monkeypatch.setattr(exporter, "_finish_transaction", real_finish)
    with pytest.raises(RuntimeError, match="invalid canonical"):
        exporter.export_final(output)
    assert (singleton.read_bytes(), manifest.read_bytes()) == old
    assert not list(output.glob(f"{exporter.TRANSACTION_PREFIX}*"))


def test_manifest_is_published_after_all_translation_artifacts(tmp_path, monkeypatch):
    _fixture(tmp_path, (1,))
    _run, exporter = _bind(tmp_path)
    output = tmp_path / "output_cn"
    _sentinels(output)
    observations = []

    def observe(name):
        if name == "publish":
            observations.append(
                ((output / "translated/full_volume_cn.md").exists(), (output / "final_export_manifest.json").exists())
            )

    monkeypatch.setattr(exporter, "_inject", observe)
    exporter.export_final(output)
    assert observations[0] == (True, False)
    assert observations[-1] == (True, True)


def test_canonical_segments_symlink_and_parent_symlink_reject_external(tmp_path):
    segments = _fixture(tmp_path, (1,))
    external = tmp_path / "external-segments.json"
    external.write_bytes(segments.read_bytes())
    segments.unlink()
    segments.symlink_to(external)
    _run, exporter = _bind(tmp_path)
    with pytest.raises(RuntimeError, match="regular file"):
        exporter.export_final(tmp_path / "output_cn")
    assert external.read_bytes().startswith(b'{"chapters"')

    segments.unlink()
    real_parent = segments.parent
    displaced = tmp_path / "displaced-run"
    real_parent.rename(displaced)
    real_parent.symlink_to(displaced, target_is_directory=True)
    with pytest.raises(RuntimeError, match="ancestry"):
        exporter.export_final(tmp_path / "output_cn")


def test_direct_fixer_target_binding_and_prewrite_substitution(tmp_path, monkeypatch):
    segments = _fixture(tmp_path, (1,))
    fixer = _load_fixer()
    monkeypatch.setattr(fixer, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(fixer, "build_rules", lambda _root: {})
    monkeypatch.setattr(fixer, "apply_rules", lambda text, *_args: (text + " changed", {}))
    external = tmp_path / "external.json"
    external.write_bytes(segments.read_bytes())
    original = external.read_bytes()

    def substitute(name):
        if name == "segments-pre-write":
            segments.unlink()
            segments.symlink_to(external)

    monkeypatch.setattr(fixer, "_inject", substitute)
    monkeypatch.setattr(sys, "argv", ["fix", "--segments-file", str(segments), "--chapters", "1", "1"])
    with pytest.raises(RuntimeError, match="identity changed"):
        fixer._main_locked()
    assert external.read_bytes() == original


def test_direct_fixer_rejects_initial_segments_symlink(tmp_path, monkeypatch):
    segments = _fixture(tmp_path, (1,))
    external = tmp_path / "external-fixer.json"
    external.write_bytes(segments.read_bytes())
    segments.unlink()
    segments.symlink_to(external)
    fixer = _load_fixer()
    monkeypatch.setattr(fixer, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(fixer, "build_rules", lambda _root: {})
    monkeypatch.setattr(sys, "argv", ["fix", "--segments-file", str(segments), "--chapters", "1", "1"])
    with pytest.raises(RuntimeError, match="regular file"):
        fixer._main_locked()
    assert external.read_bytes().startswith(b'{"chapters"')


def test_all_runs_discovery_rejects_symlinked_nested_entry(tmp_path):
    _fixture(tmp_path, (1,))
    run_mod, _exporter = _bind(tmp_path)
    external = tmp_path / "external-run"
    external.mkdir()
    link = tmp_path / "workspace/runs/linked"
    link.symlink_to(external, target_is_directory=True)
    with pytest.raises(RuntimeError, match="symlink"):
        run_mod.discover_all_run_files()


def test_direct_fixer_and_runner_diff_log_symlink_parents_fail_closed(tmp_path, monkeypatch):
    segments = _fixture(tmp_path, (1,))
    fixer = _load_fixer()
    monkeypatch.setattr(fixer, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(fixer, "build_rules", lambda _root: {})
    external_dir = tmp_path / "external-diffs"
    external_dir.mkdir()
    link = tmp_path / "linked-diffs"
    link.symlink_to(external_dir, target_is_directory=True)
    monkeypatch.setattr(sys, "argv", ["fix", "--segments-file", str(segments), "--chapters", "1", "1", "--dry-run", "--diff-log", str(link / "diff.json")])
    with pytest.raises(RuntimeError, match="ancestry"):
        fixer._main_locked()
    assert list(external_dir.iterdir()) == []

    run_mod, _exporter = _bind(tmp_path)
    monkeypatch.setattr(run_mod, "discover_canonical_files", lambda: [segments])
    monkeypatch.setattr(
        run_mod.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"changed_segments": 0, "total_segments": 1, "rule_hits": {}, "skipped_ambiguous_hits": {}}),
            stderr="",
        ),
    )
    with pytest.raises(RuntimeError, match="ancestry"):
        run_mod.main(["--dry-run", "--diff-log", str(link / "combined.json")])
    assert list(external_dir.iterdir()) == []


def test_direct_fixer_diff_log_symlink_file_preserves_external(tmp_path, monkeypatch):
    segments = _fixture(tmp_path, (1,))
    fixer = _load_fixer()
    monkeypatch.setattr(fixer, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(fixer, "build_rules", lambda _root: {})
    external = tmp_path / "external-diff.json"
    external.write_bytes(b"external diff sentinel")
    linked = tmp_path / "diff.json"
    linked.symlink_to(external)
    monkeypatch.setattr(sys, "argv", ["fix", "--segments-file", str(segments), "--chapters", "1", "1", "--dry-run", "--diff-log", str(linked)])
    with pytest.raises(RuntimeError, match="regular file"):
        fixer._main_locked()
    assert external.read_bytes() == b"external diff sentinel"


def _secure_files_module():
    import secure_consistency_files

    return secure_consistency_files


@pytest.mark.parametrize("kind", ["regular", "symlink"])
def test_secure_existing_exchange_restores_foreign_appearance(tmp_path, monkeypatch, kind):
    secure = _secure_files_module()
    target = tmp_path / "target.json"
    target.write_bytes(b"old")
    bound = secure.BoundRegularFile.open(target)
    external = tmp_path / "external.json"
    external.write_bytes(b"foreign sentinel")
    original_aside = tmp_path / "original-aside.json"
    fired = False

    def race(name):
        nonlocal fired
        if name == "before-exchange" and not fired:
            target.rename(original_aside)
            if kind == "regular":
                target.write_bytes(b"foreign sentinel")
            else:
                target.symlink_to(external)
            fired = True

    monkeypatch.setattr(secure, "_inject", race)
    try:
        with pytest.raises(RuntimeError, match="identity changed during publication"):
            bound.replace_bytes(b"new")
    finally:
        bound.close()
    assert fired
    if kind == "regular":
        assert target.read_bytes() == b"foreign sentinel"
    else:
        assert target.is_symlink() and external.read_bytes() == b"foreign sentinel"
    assert original_aside.read_bytes() == b"old"
    assert not list(tmp_path.glob(".target.json.consistency.*"))


@pytest.mark.parametrize("kind", ["regular", "symlink"])
def test_secure_absent_noreplace_preserves_appearing_foreign(tmp_path, monkeypatch, kind):
    secure = _secure_files_module()
    target = tmp_path / "new.json"
    external = tmp_path / "external.json"
    external.write_bytes(b"foreign sentinel")

    def race(name):
        if name == "before-noreplace":
            if kind == "regular":
                target.write_bytes(b"foreign sentinel")
            else:
                target.symlink_to(external)

    monkeypatch.setattr(secure, "_inject", race)
    with pytest.raises(RuntimeError, match="appeared during publication"):
        secure.atomic_write_new_or_replace(target, b"new")
    if kind == "regular":
        assert target.read_bytes() == b"foreign sentinel"
    else:
        assert target.is_symlink() and external.read_bytes() == b"foreign sentinel"
    assert not list(tmp_path.glob(".new.json.consistency.*"))


def test_secure_exchange_rollback_window_fails_without_clobber(tmp_path, monkeypatch):
    secure = _secure_files_module()
    target = tmp_path / "target.json"
    target.write_bytes(b"old")
    bound = secure.BoundRegularFile.open(target)
    foreign = tmp_path / "foreign.json"
    original_aside = tmp_path / "old-aside.json"

    def race(name):
        if name == "before-exchange":
            target.rename(original_aside)
            target.write_bytes(b"foreign sentinel")
        elif name == "before-rollback-exchange":
            private = next(tmp_path.glob(".target.json.consistency.*"))
            private.rename(foreign)
            private.symlink_to(original_aside)

    monkeypatch.setattr(secure, "_inject", race)
    try:
        with pytest.raises(RuntimeError, match="rollback boundary changed"):
            bound.replace_bytes(b"new")
    finally:
        bound.close()
    assert target.read_bytes() == b"new"
    assert foreign.read_bytes() == b"foreign sentinel"
    assert original_aside.read_bytes() == b"old"
    owned_residue = [p for p in tmp_path.glob(".target.json.consistency.*") if not p.is_symlink()]
    assert owned_residue == []


def test_secure_helper_missing_atomic_primitive_fails_closed(tmp_path, monkeypatch):
    secure = _secure_files_module()
    target = tmp_path / "target.json"
    target.write_bytes(b"old")
    monkeypatch.setattr(secure, "_rename_with_flag", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("unsupported")))
    with pytest.raises(RuntimeError, match="unsupported"):
        secure.atomic_write_new_or_replace(target, b"new")
    assert target.read_bytes() == b"old"
    assert not list(tmp_path.glob(".target.json.consistency.*"))
