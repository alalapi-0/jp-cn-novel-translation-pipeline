"""Registered version and recovery checks use synthetic files only."""
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("inventory_test", ROOT / "scripts/freeze_optimization_inventory.py")
inventory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(inventory)


def registered(tmp_path):
    private = tmp_path / "workspace/tooling/optimization"; private.mkdir(parents=True)
    source = tmp_path / "input_jp/001.md"; source.parent.mkdir(); source.write_text("合成原文\n")
    record = {"path": "input_jp/001.md", "category": "source_original",
              "read_eligibility": "registered_local_original_read_only", **inventory.identity(source.stat())}
    reg = private / "registration.json"
    reg.write_text(json.dumps({"schema": "optimization-file-registration/1", "root": str(tmp_path), "entries": [record]}))
    return source, reg, private / "snapshot"


def freeze(reg, output, **kwargs):
    # Unit tests explicitly select their disposable repository, never ROOT.
    return inventory.freeze_registered(reg.parents[3], reg, output, **kwargs)


def test_recoverable_version_preserves_original_and_reuses_exact_freeze(tmp_path):
    source, reg, output = registered(tmp_path); before = source.read_bytes()
    result = freeze(reg, output); inventory.verify(result, output)
    assert source.read_bytes() == before == (output / result["entries"][0]["snapshot"]).read_bytes()
    assert freeze(reg, output) == result
    assert result["source_denominator"] == 1
    assert not list((output / "blobs").glob("freeze-*"))


def test_relative_cli_paths_reuse_exact_version(tmp_path, monkeypatch):
    _, reg, output = registered(tmp_path); monkeypatch.chdir(tmp_path)
    first = inventory.freeze_registered(tmp_path, reg.relative_to(tmp_path), output.relative_to(tmp_path))
    assert inventory.freeze_registered(tmp_path, reg.relative_to(tmp_path), output.relative_to(tmp_path)) == first


def test_unknown_source_is_excluded_without_opening(tmp_path):
    _, reg, output = registered(tmp_path); data = json.loads(reg.read_text())
    data["entries"].append({"path": "missing-secret.json", "bytes": 1, "category": "unknown", "read_eligibility": "excluded_unknown_provenance"})
    reg.write_text(json.dumps(data)); result = freeze(reg, output)
    assert result["entries"][1]["freeze_status"] == "excluded_without_content_read"
    assert result["registered_denominator"] == 2 and result["eligible_denominator"] == 1


def test_changed_input_and_duplicate_registration_are_refused(tmp_path):
    source, reg, output = registered(tmp_path)
    source.write_text("等长改文\n")
    with pytest.raises(ValueError, match="version changed"):
        freeze(reg, output)
    data = json.loads(reg.read_text()); data["entries"] *= 2; reg.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="duplicate"):
        freeze(reg, output)


def test_secret_symlink_budget_and_overwrite_boundaries(tmp_path):
    source, reg, output = registered(tmp_path)
    with pytest.raises(ValueError, match="budget"):
        freeze(reg, output, max_bytes=0)
    with pytest.raises(ValueError, match="secret"):
        inventory.ordinary_path(tmp_path, ".env")
    link = source.parent / "link.md"; link.symlink_to(source)
    with pytest.raises(ValueError, match="symlink"):
        inventory.ordinary_path(tmp_path, "input_jp/link.md")
    freeze(reg, output)
    data=json.loads(reg.read_text()); data["revision"]=2; reg.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="different registration"):
        freeze(reg, output)


def test_registry_is_validated_before_any_content_read(tmp_path, monkeypatch):
    _, reg, output = registered(tmp_path)
    secret = tmp_path / ".env"; secret.write_text("SYNTHETIC do not open")
    alias = reg.parent / "alias"; alias.mkdir()
    link = alias / "registration.json"; link.symlink_to(secret)
    original = Path.read_bytes
    def guarded(path):
        if path in (secret, link):
            raise AssertionError("unregistered content opened")
        return original(path)
    monkeypatch.setattr(Path, "read_bytes", guarded)
    for candidate in (secret, link, tmp_path / "registration.json"):
        with pytest.raises(ValueError, match="registry|symlink"):
            inventory.freeze_registered(tmp_path, candidate, output)


@pytest.mark.parametrize("change", ["drop_entry", "denominator", "record_path"])
def test_same_registration_hash_cannot_hide_manifest_changes(tmp_path, change):
    _, reg, output = registered(tmp_path); freeze(reg, output)
    manifest = output / "versions.json"; result = json.loads(manifest.read_text())
    if change == "drop_entry": result["entries"] = []
    elif change == "denominator": result["source_denominator"] = 0
    else: result["entries"][0]["path"] = "input_jp/other.md"
    manifest.chmod(0o600); manifest.write_text(json.dumps(result))
    with pytest.raises(ValueError, match="manifest"):
        freeze(reg, output)


def test_symlink_manifest_is_not_read(tmp_path):
    _, reg, output = registered(tmp_path); freeze(reg, output)
    manifest = output / "versions.json"; original = output / "manifest-original.json"
    manifest.rename(original); manifest.symlink_to(original)
    with pytest.raises(ValueError, match="symlink"):
        freeze(reg, output)


def test_snapshot_directory_symlink_cannot_redirect_writes(tmp_path):
    _, reg, output = registered(tmp_path); output.mkdir()
    outside = tmp_path / "outside"; outside.mkdir()
    (output / "blobs").symlink_to(outside, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        freeze(reg, output)
    assert not list(outside.iterdir())
