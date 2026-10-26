"""Leakage counterexamples use generated synthetic snapshots only."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("split_cli_test", ROOT / "scripts/build_optimization_split.py")
split_cli = importlib.util.module_from_spec(spec); spec.loader.exec_module(split_cli)
import build_optimization_alignment as alignment


def setup(tmp_path):
    private = tmp_path / "workspace/tooling/optimization"; frozen = private / "frozen"
    (frozen / "blobs").mkdir(parents=True); entries = []
    def blob(path, category, raw):
        sha = hashlib.sha256(raw).hexdigest(); (frozen / "blobs" / sha).write_bytes(raw)
        entries.append({"path": path, "category": category, "bytes": len(raw), "sha256": sha,
                        "snapshot": f"blobs/{sha}", "freeze_status": "read_only_recoverable_version"})
    chapters = []
    for i in range(1, 25):
        source = f"彼は「先生、もしドラゴンが来なかったら」と言った。{i}"
        blob(f"input_jp/{i:03d}.md", "source_original", ("# 合成\n\n" + source).encode())
        chapters.append({"chapter_id": f"ch-{i:03d}", "segments": [{"id": f"s{i}", "source_text": source,
                        "draft_text": f"合成旧译{i}" if i > 1 else "", "refined_text": f"合成另一旧译{i}",
                        "human_approved_final": True}]})
    blob("workspace/runs/mixed/segments.json", "old_translation", json.dumps({
        "language_direction": "JP_TO_CN", "chapters": chapters}).encode())
    blob("workspace/manifests/unresolved.json", "manifest_or_user_candidate", json.dumps({
        "segments": [{"source": "unknown", "draft": "UNKNOWN_TARGET"}]}).encode())
    manifest = frozen / "versions.json"
    manifest.write_text(json.dumps({"schema": "optimization-input-versions/1", "registered_denominator": len(entries),
                                    "source_denominator": 24, "entries": entries}))
    sha = hashlib.sha256(manifest.read_bytes()).hexdigest()
    aligned = private / "alignment"; summary = alignment.build(tmp_path, manifest, sha, aligned)
    reader = alignment.FrozenReader(tmp_path, manifest, sha)
    return private, reader, aligned / "legacy-alignment.jsonl", summary


def freeze(tmp_path, monkeypatch=None):
    private, reader, aligned, summary = setup(tmp_path)
    original_read = alignment.FrozenReader.read
    def source_only(self, row):
        assert row["category"] == "source_original", "target/feedback opened during source-only split"
        return original_read(self, row)
    if monkeypatch:
        monkeypatch.setattr(alignment.FrozenReader, "read", source_only)
    result = split_cli.build(tmp_path, [reader], aligned, summary["legacy-alignment.jsonl_sha256"],
                             summary["alignment_counts"]["target_field_records"], private / "split",
                             seed="fixed synthetic seed", group_size=4)
    if monkeypatch:
        monkeypatch.setattr(alignment.FrozenReader, "read", original_read)
    manifest = private / "split/split.json"
    return private, manifest, result


def test_construction_opens_sources_only_and_preserves_all_denominators(tmp_path, monkeypatch):
    private, manifest, summary = freeze(tmp_path, monkeypatch)
    split = json.loads(manifest.read_bytes())
    assert summary["source_denominator"] == 24 and summary["registered_file_denominator"] == 26
    assert sum(summary["target_routing_counts"].values()) == 49
    assert summary["target_content_reads_during_construction"] == 0
    assert split["target_routing_counts"]["denied_unknown_or_uncertain_lineage"] == 1
    assert summary["partition_counts"] == {"development": 16, "holdout": 8}
    assert summary["target_routing_counts"]["denied_holdout_target_fields"] == 16
    with pytest.raises(ValueError, match="already exists"):
        reader = alignment.FrozenReader(tmp_path, private / "frozen/versions.json", split["inputs"][0]["sha256"])
        split_cli.build(tmp_path, [reader], private / split["alignment"]["path"], "0" * 64, 49,
                        private / "split", seed="irrelevant")


def test_holdout_and_feedback_denied_before_target_read_but_dev_releases_one_field(tmp_path, monkeypatch):
    private, manifest, result = freeze(tmp_path)
    reader = split_cli.DevelopmentReader(tmp_path, manifest, result["split_sha256"])
    records = [json.loads(line) for line in (private / "alignment/legacy-alignment.jsonl").read_text().splitlines()]
    partitions = {r["chapter_id"]: r["partition"] for r in reader.split["chapters"]}
    held = next(r for r in records if partitions.get(r.get("chapter_id")) == "holdout")
    dev = next(r for r in records if partitions.get(r.get("chapter_id")) == "development" and r["field"] == "refined_text")
    original_read = alignment.FrozenReader.read; calls = []
    def observed(self, row):
        calls.append(row["category"]); return original_read(self, row)
    monkeypatch.setattr(alignment.FrozenReader, "read", observed)
    for request in (lambda: reader.target(held["record_id"]), lambda: reader.target("unknown"),
                    lambda: reader.target(records[-1]["record_id"]), lambda: reader.feedback("any", allow=True)):
        with pytest.raises(PermissionError): request()
        assert calls == []
    context = reader.source_context(split_cli.lineage(reader.split, held))
    assert context.startswith("# 合成") and calls == ["source_original"]
    value = reader.target(dev["record_id"])
    assert value["target_text"].startswith("合成另一旧译")
    assert value["legacy_approval"].startswith("unverified") and value["partition"] == "development"
    assert "chapters" not in value and "segments" not in value and "human_approved_final" not in value
    assert calls == ["source_original", "old_translation"]


def test_manifest_alignment_and_blob_pins_fail_closed(tmp_path, monkeypatch):
    private, manifest, result = freeze(tmp_path)
    with pytest.raises(ValueError, match="identity changed"):
        split_cli.DevelopmentReader(tmp_path, manifest, "0" * 64)
    with pytest.raises(ValueError, match="ordinary private"):
        split_cli.DevelopmentReader(tmp_path, tmp_path / ".env", "0" * 64)
    reader = split_cli.DevelopmentReader(tmp_path, manifest, result["split_sha256"])
    rows = [json.loads(line) for line in (private / "alignment/legacy-alignment.jsonl").read_text().splitlines()]
    dev_ids = {r["chapter_id"] for r in reader.split["chapters"] if r["partition"] == "development"}
    record = next(r for r in rows if r.get("chapter_id") in dev_ids)
    artifact = reader.entries[record["artifact_path"]]
    blob = private / "frozen" / artifact["snapshot"]
    original = blob.read_bytes(); blob.write_bytes(original + b" ")
    with pytest.raises(ValueError, match="content identity"):
        reader.target(record["record_id"])
    blob.write_bytes(original)
    metadata = private / "alignment/legacy-alignment.jsonl"
    metadata.write_bytes(metadata.read_bytes() + b"\n")
    def forbidden(*args): raise AssertionError("target opened despite changed alignment")
    monkeypatch.setattr(alignment.FrozenReader, "read", forbidden)
    with pytest.raises(ValueError, match="metadata identity"):
        reader.target(record["record_id"])


def test_wrong_target_denominator_writes_no_split(tmp_path):
    private, reader, aligned, summary = setup(tmp_path)
    with pytest.raises(ValueError, match="target-field denominator"):
        split_cli.build(tmp_path, [reader], aligned, summary["legacy-alignment.jsonl_sha256"],
                        48, private / "bad-split", seed="test", group_size=4)
    assert not (private / "bad-split").exists()


def test_in_memory_holdout_relabel_cannot_bypass_frozen_identity(tmp_path, monkeypatch):
    private, manifest, result = freeze(tmp_path)
    reader = split_cli.DevelopmentReader(tmp_path, manifest, result["split_sha256"])
    held = next(row for row in reader.split["chapters"] if row["partition"] == "holdout")
    held["partition"] = "development"
    def forbidden(*args): raise AssertionError("snapshot opened after split mutation")
    monkeypatch.setattr(alignment.FrozenReader, "read", forbidden)
    with pytest.raises(PermissionError, match="mutated"):
        reader.target("any record")
    with pytest.raises(PermissionError, match="mutated"):
        reader.source_context((held["language_direction"], held["chapter_id"], held["source_revision"]))
