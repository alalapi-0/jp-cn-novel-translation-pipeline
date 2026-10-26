"""Private snapshot integration is tested with an isolated synthetic repository."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("alignment_cli_test", ROOT / "scripts/build_optimization_alignment.py")
alignment = importlib.util.module_from_spec(spec)
spec.loader.exec_module(alignment)


def fixture(tmp_path):
    private = tmp_path / "workspace/tooling/optimization"; frozen = private / "frozen"
    (frozen / "blobs").mkdir(parents=True)
    rows = []
    def blob(path, category, raw):
        digest = hashlib.sha256(raw).hexdigest(); (frozen / "blobs" / digest).write_bytes(raw)
        rows.append({"path": path, "category": category, "bytes": len(raw), "sha256": digest,
                     "snapshot": f"blobs/{digest}", "freeze_status": "read_only_recoverable_version"})
    blob("input_jp/001-synthetic.md", "source_original", "# 合成\n\n彼は来た。\n\n彼女は去った。".encode())
    doc = {"language_direction": "JP_TO_CN", "chapters": [{"chapter_id": "ch-001", "segments": [
        {"segment_id": "duplicate", "source_text": "彼は来た。", "draft_text": "他来了。", "refined_text": "他来了呀。"},
        {"segment_id": "duplicate", "source_text": "彼女は去った。", "draft_text": ""}]}]}
    blob("workspace/runs/synthetic/segments.json", "old_translation", json.dumps(doc).encode())
    blob("workspace/manifests/unknown.json", "manifest_or_user_candidate", json.dumps({
        "language_direction": "JP_TO_CN", "segments": [{"id": "no-chapter", "source": "不明", "draft": "候选"}]}).encode())
    manifest = frozen / "versions.json"
    manifest.write_text(json.dumps({"schema": "optimization-input-versions/1", "registered_denominator": 3,
                                    "source_denominator": 1, "entries": rows}))
    return manifest, hashlib.sha256(manifest.read_bytes()).hexdigest(), private / "alignment"


def test_pinned_snapshot_alignment_preserves_fields_duplicates_and_unknowns(tmp_path):
    manifest, digest, output = fixture(tmp_path)
    result = alignment.build(tmp_path, manifest, digest, output)
    rows = [json.loads(line) for line in (output / "legacy-alignment.jsonl").read_text().splitlines()]
    assert result["source_index"]["files"] == 1
    assert result["alignment_counts"]["legacy_segment_records"] == 3
    assert result["alignment_counts"]["target_field_records"] == 4
    assert len({row["record_id"] for row in rows}) == 4
    assert {row["field"] for row in rows} >= {"draft_text", "refined_text"}
    assert any(row["status"] == "empty_target" for row in rows)
    unknown = next(row for row in rows if row["status"] == "unresolved_original_source_identity")
    assert unknown["target_spans"][0]["span"] == [0, 2]
    assert result["artifact_diagnostics"][0]["duplicate_legacy_ids"] == {"duplicate": 2}
    assert all(row["automatic_acceptance"] is False for row in rows)
    with pytest.raises(ValueError, match="already exists"):
        alignment.build(tmp_path, manifest, digest, output)


def test_wrong_pin_and_symlink_snapshot_fail_closed(tmp_path):
    manifest, digest, output = fixture(tmp_path)
    with pytest.raises(ValueError, match="identity changed"):
        alignment.FrozenReader(tmp_path, manifest, "0" * 64)
    reader = alignment.FrozenReader(tmp_path, manifest, digest); row = reader.versions["entries"][0]
    blob = manifest.parent / row["snapshot"]; raw = blob.read_bytes(); blob.unlink()
    victim = tmp_path / "victim"; victim.write_bytes(raw); blob.symlink_to(victim)
    with pytest.raises(ValueError, match="ordinary private"):
        reader.read(row)


def test_versions_path_is_checked_before_content_read(tmp_path, monkeypatch):
    secret = tmp_path / ".env"
    def forbidden(*args, **kwargs):
        raise AssertionError("secret opened before validation")
    monkeypatch.setattr(Path, "read_bytes", forbidden)
    with pytest.raises(ValueError, match="ordinary private"):
        alignment.FrozenReader(tmp_path, secret, "0" * 64)


def test_supplemental_inventory_cannot_duplicate_or_shrink_original_scope(tmp_path):
    manifest, digest, output = fixture(tmp_path)
    with pytest.raises(ValueError, match="disjoint"):
        alignment.build(tmp_path, manifest, digest, output, supplemental=((manifest, digest),))


def test_forged_descriptor_and_identical_artifact_aliases_are_preserved(tmp_path):
    manifest, digest, output = fixture(tmp_path)
    reader = alignment.FrozenReader(tmp_path, manifest, digest)
    forged = dict(reader.versions["entries"][0], path="unregistered.md")
    with pytest.raises(ValueError, match="not in the pinned"):
        reader.read(forged)
    value = json.loads(manifest.read_text())
    value["entries"].append(dict(value["entries"][1], path="workspace/runs/alias/segments.json"))
    value["registered_denominator"] = 4
    manifest.write_text(json.dumps(value)); digest = hashlib.sha256(manifest.read_bytes()).hexdigest()
    alignment.build(tmp_path, manifest, digest, output)
    rows = [json.loads(line) for line in (output / "legacy-alignment.jsonl").read_text().splitlines()]
    assert len(rows) == len({row["record_id"] for row in rows}) == 7
