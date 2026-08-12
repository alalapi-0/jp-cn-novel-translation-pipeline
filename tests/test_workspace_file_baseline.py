from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT = REPO_ROOT / "scripts" / "workspace_file_baseline.py"


def _load_script():
    spec = importlib.util.spec_from_file_location("workspace_file_baseline", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def baseline_module():
    return _load_script()


def _tree_and_baseline(tmp_path: Path) -> tuple[Path, Path]:
    root = tmp_path / "workspace"
    root.mkdir()
    return root, tmp_path / "workspace_file_baseline.json"


def test_create_is_byte_deterministic_and_uses_specified_aggregate(tmp_path: Path, baseline_module) -> None:
    root, baseline = _tree_and_baseline(tmp_path)
    (root / "z.bin").write_bytes(b"z\x00")
    (root / "nested").mkdir()
    (root / "nested" / "a.txt").write_bytes("你好".encode())

    first = baseline_module.create_baseline(root, baseline)
    first_bytes = baseline.read_bytes()
    second = baseline_module.create_baseline(root, baseline)
    assert baseline.read_bytes() == first_bytes
    assert first == second

    document = json.loads(first_bytes)
    assert [item["relative_path"] for item in document["files"]] == ["nested/a.txt", "z.bin"]
    aggregate = hashlib.sha256()
    for item in document["files"]:
        aggregate.update(item["relative_path"].encode("utf-8"))
        aggregate.update(b"\x00")
        aggregate.update(bytes.fromhex(item["sha256"]))
    assert document["aggregate_sha256"] == aggregate.hexdigest()


def test_verify_reports_sorted_added_removed_and_changed(tmp_path: Path, baseline_module) -> None:
    root, baseline = _tree_and_baseline(tmp_path)
    (root / "removed.txt").write_bytes(b"gone")
    (root / "changed.txt").write_bytes(b"old")
    baseline_module.create_baseline(root, baseline)

    (root / "removed.txt").unlink()
    (root / "changed.txt").write_bytes(b"new-value")
    (root / "z-added.txt").write_bytes(b"z")
    (root / "a-added.txt").write_bytes(b"a")

    exit_code, summary = baseline_module.verify_baseline(root, baseline)
    assert exit_code == 1
    assert summary["status"] == "drift"
    assert summary["added"] == ["a-added.txt", "z-added.txt"]
    assert summary["removed"] == ["removed.txt"]
    assert [item["relative_path"] for item in summary["changed"]] == ["changed.txt"]
    assert summary["changed"][0]["expected"] == {
        "size": 3,
        "sha256": hashlib.sha256(b"old").hexdigest(),
    }
    assert summary["changed"][0]["actual"] == {
        "size": 9,
        "sha256": hashlib.sha256(b"new-value").hexdigest(),
    }


@pytest.mark.parametrize("unsafe_path", ["../escape", "/absolute", "dir//file", "./file"])
def test_verify_rejects_unsafe_manifest_paths(tmp_path: Path, baseline_module, unsafe_path: str) -> None:
    root, baseline = _tree_and_baseline(tmp_path)
    (root / "file").write_bytes(b"x")
    baseline_module.create_baseline(root, baseline)
    document = json.loads(baseline.read_bytes())
    document["files"][0]["relative_path"] = unsafe_path
    baseline.write_text(json.dumps(document), encoding="utf-8")
    with pytest.raises(baseline_module.BaselineError, match="normalized safe"):
        baseline_module.verify_baseline(root, baseline)


def test_verify_rejects_corrupt_duplicate_and_inconsistent_manifests(tmp_path: Path, baseline_module) -> None:
    root, baseline = _tree_and_baseline(tmp_path)
    (root / "file").write_bytes(b"x")
    baseline_module.create_baseline(root, baseline)
    good = json.loads(baseline.read_bytes())

    baseline.write_bytes(b"{not-json")
    with pytest.raises(baseline_module.BaselineError, match="valid UTF-8 JSON"):
        baseline_module.verify_baseline(root, baseline)

    duplicate = dict(good)
    duplicate["files"] = [good["files"][0], good["files"][0]]
    duplicate["file_count"] = 2
    baseline.write_text(json.dumps(duplicate), encoding="utf-8")
    with pytest.raises(baseline_module.BaselineError, match="duplicates"):
        baseline_module.verify_baseline(root, baseline)

    inconsistent = dict(good)
    inconsistent["aggregate_sha256"] = "0" * 64
    baseline.write_text(json.dumps(inconsistent), encoding="utf-8")
    with pytest.raises(baseline_module.BaselineError, match="self-consistent"):
        baseline_module.verify_baseline(root, baseline)

    baseline.write_text('{"schema":"a","schema":"b"}', encoding="utf-8")
    with pytest.raises(baseline_module.BaselineError, match="duplicate object keys"):
        baseline_module.verify_baseline(root, baseline)


def test_external_file_and_directory_symlinks_are_not_followed(tmp_path: Path, baseline_module) -> None:
    root, baseline = _tree_and_baseline(tmp_path)
    (root / "local.txt").write_bytes(b"local")
    external = tmp_path / "external"
    external.mkdir()
    (external / "secret.txt").write_bytes(b"external-secret")
    (root / "file-link").symlink_to(external / "secret.txt")
    (root / "dir-link").symlink_to(external, target_is_directory=True)

    summary = baseline_module.create_baseline(root, baseline)
    document = json.loads(baseline.read_bytes())
    assert summary["symlinks_skipped"] == 2
    assert [item["relative_path"] for item in document["files"]] == ["local.txt"]
    assert "external-secret" not in baseline.read_text(encoding="utf-8")

    (external / "secret.txt").write_bytes(b"changed-outside")
    exit_code, verified = baseline_module.verify_baseline(root, baseline)
    assert exit_code == 0
    assert verified["symlinks_skipped"] == 2


def test_atomic_replace_failure_preserves_old_baseline(tmp_path: Path, baseline_module, monkeypatch) -> None:
    root, baseline = _tree_and_baseline(tmp_path)
    (root / "file").write_bytes(b"x")
    baseline.write_bytes(b"old-baseline")

    def fail_replace(_source, _destination):
        raise OSError("simulated replace failure")

    monkeypatch.setattr(baseline_module.os, "replace", fail_replace)
    with pytest.raises(baseline_module.BaselineError, match="atomic replacement failed"):
        baseline_module.create_baseline(root, baseline)
    assert baseline.read_bytes() == b"old-baseline"
    assert list(tmp_path.glob(".workspace_file_baseline.json.*.tmp")) == []


def test_unstable_collection_does_not_replace_old_baseline(tmp_path: Path, baseline_module, monkeypatch) -> None:
    root, baseline = _tree_and_baseline(tmp_path)
    (root / "file").write_bytes(b"x")
    baseline.write_bytes(b"old-baseline")
    original_capture = baseline_module._capture_once
    calls = 0

    def mutate_before_second_capture(capture_root: Path, *, hash_files: bool):
        nonlocal calls
        calls += 1
        if calls == 2:
            (root / "added-during-collection").write_bytes(b"new")
        return original_capture(capture_root, hash_files=hash_files)

    monkeypatch.setattr(baseline_module, "_capture_once", mutate_before_second_capture)
    with pytest.raises(baseline_module.BaselineError, match="changed during collection"):
        baseline_module.create_baseline(root, baseline)
    assert baseline.read_bytes() == b"old-baseline"


def test_cli_exit_codes_and_json_summary(tmp_path: Path, baseline_module, capsys) -> None:
    root, baseline = _tree_and_baseline(tmp_path)
    (root / "file").write_bytes(b"x")
    assert baseline_module.main(["create", "--root", str(root), "--baseline", str(baseline)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "created"
    assert baseline_module.main(["verify", "--root", str(root), "--baseline", str(baseline)]) == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
    (root / "file").write_bytes(b"drift")
    assert baseline_module.main(["verify", "--root", str(root), "--baseline", str(baseline)]) == 1
    assert json.loads(capsys.readouterr().out)["status"] == "drift"
    baseline.write_bytes(b"invalid")
    assert baseline_module.main(["verify", "--root", str(root), "--baseline", str(baseline)]) == 2
    assert json.loads(capsys.readouterr().out)["status"] == "error"


@pytest.mark.parametrize("command", ["create", "verify"])
def test_cli_json_flag_is_idempotent_in_any_position(tmp_path: Path, baseline_module, capsys, command: str) -> None:
    root, baseline = _tree_and_baseline(tmp_path)
    (root / "file").write_bytes(b"x")
    baseline_module.create_baseline(root, baseline)

    common = ["--root", str(root), "--baseline", str(baseline)]
    variants = [
        [command, *common],
        ["--json", command, *common],
        [command, *common, "--json"],
    ]
    results = []
    for argv in variants:
        exit_code = baseline_module.main(argv)
        results.append((exit_code, capsys.readouterr().out))

    assert results[0] == results[1] == results[2]
