#!/usr/bin/env python3
"""Freeze a source-only split and expose a narrowly scoped development reader.

Construction reads source snapshots and alignment metadata only. The reader
releases one verified development target field, never its JSON container. This
is a data-release boundary, not an OS sandbox against the filesystem owner.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))
from build_optimization_alignment import FrozenReader, TARGET_FIELDS, iter_segments, private_path
from translation.evaluation_split import authorize, build_split, digest, key, source_features, validate_split
from translation.source_alignment import SourceDocument, text_hash


def inventory(readers):
    entries = {}; owners = {}
    for reader in readers:
        for row in reader.versions["entries"]:
            if row["path"] in entries:
                raise ValueError("supplemental inventories must be disjoint")
            entries[row["path"]] = row; owners[row["path"]] = reader
    return entries, owners


def pinned_json(root: Path, path: Path, expected: str) -> dict:
    path = private_path(root, path)
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or path.stat().st_size > 4 * 1024 * 1024:
        raise ValueError("bounded, pinned manifest required")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise ValueError("split manifest identity changed")
    return json.loads(raw)


def alignment_rows(root: Path, path: Path, expected: str):
    path = private_path(root, path)
    if not re.fullmatch(r"[0-9a-f]{64}", expected) or path.stat().st_size > 256 * 1024 * 1024:
        raise ValueError("bounded, pinned alignment required")
    with path.open("rb") as stream:
        if hashlib.file_digest(stream, "sha256").hexdigest() != expected:
            raise ValueError("alignment metadata identity changed")
        stream.seek(0)
        for line in stream:
            if len(line) > 16 * 1024 * 1024:
                raise ValueError("alignment record exceeds read bound")
            yield json.loads(line)


def lineage(split: dict, record: dict) -> tuple[str, str, str]:
    matches = [row for row in split["chapters"]
               if row["chapter_id"] == record.get("chapter_id")
               and row["source_revision"] == record.get("source_revision")]
    locations = record.get("source_locations", [])
    spans = record.get("source_spans", [])
    if (len(matches) != 1 or not locations or not spans
            or record.get("status") not in {"located", "empty_target"}
            or record.get("overlapping_source_parts")
            or any(loc.get("status") != "unique_exact_source" for loc in locations)):
        raise PermissionError("unknown or uncertain source lineage")
    row = matches[0]
    if any(not (isinstance(a, int) and isinstance(b, int)
                and 0 <= a < b <= row["features"]["codepoints"]) for a, b in spans):
        raise PermissionError("invalid source coordinates")
    return key(row)


def build(root: Path, readers: list[FrozenReader], alignment: Path, alignment_sha256: str,
          alignment_count: int, output: Path, *, seed: str, group_size: int = 10) -> dict:
    root = root.resolve(); output = private_path(root, output)
    if output.exists():
        raise ValueError("split already exists; preserve the frozen split")
    entries, owners = inventory(readers)
    chapters = []
    for row in entries.values():
        if row["category"] != "source_original":
            continue
        match = re.match(r"^(\d+)", Path(row["path"]).name)
        if not match or not row["path"].startswith(("input_jp/", "input_cn/")):
            raise ValueError("unrecognized registered source identity")
        chapter_id = f"ch-{int(match[1]):03d}"
        doc = SourceDocument(owners[row["path"]].read(row).decode("utf-8"),
                             revision=row["sha256"], chapter_id=chapter_id)
        chapters.append({"chapter_id": chapter_id, "source_revision": row["sha256"],
                         "path": row["path"], "language_direction": "JP_TO_CN" if row["path"].startswith("input_jp/") else "CN_TO_JP",
                         "features": source_features(doc)})
    expected_sources = sum(r.versions["source_denominator"] for r in readers)
    if len(chapters) != expected_sources:
        raise ValueError("original source denominator changed")
    split = build_split(chapters, seed=seed, group_size=group_size)
    split["inputs"] = [{"path": str(r.path.relative_to(root)), "sha256": r.hash,
                        "registered_denominator": r.versions["registered_denominator"]} for r in readers]
    split["registered_file_denominator"] = len(entries)
    split["alignment"] = {"path": str(private_path(root, alignment).relative_to(root)),
                          "sha256": alignment_sha256, "target_field_denominator": alignment_count}
    routes = Counter()
    for record in alignment_rows(root, alignment, alignment_sha256):
        try:
            anchor = lineage(split, record)
        except PermissionError:
            routes["denied_unknown_or_uncertain_lineage"] += 1
            continue
        try:
            authorize(split, "target", [anchor])
            routes["development_target_fields"] += 1
        except PermissionError:
            routes["denied_holdout_target_fields"] += 1
    if sum(routes.values()) != alignment_count:
        raise ValueError("target-field denominator changed")
    split["target_routing_counts"] = dict(routes)
    raw = (json.dumps(split, ensure_ascii=False, indent=2) + "\n").encode()
    if len(raw) > 4 * 1024 * 1024:
        raise ValueError("split evidence exceeds manifest budget")
    output.mkdir(parents=True, mode=0o700)
    manifest = output / "split.json"; manifest.write_bytes(raw); manifest.chmod(0o400)
    summary = {"schema": "optimization-split-summary/1", "split_sha256": hashlib.sha256(raw).hexdigest(),
               "manifest_bytes": len(raw), "source_denominator": len(chapters),
               "registered_file_denominator": len(entries), "group_count": len(split["groups"]),
               "partition_counts": split["partition_counts"], "target_routing_counts": dict(routes),
               "target_content_reads_during_construction": 0, "source_only_selection": True,
               "semantic_coverage_confirmed": False, "paid_api_calls": 0, "corpus_model_operations": 0}
    (output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    return summary


class DevelopmentReader:
    """Pinned access for later development experiments; no holdout-unseal flag.

    A mixed legacy JSON snapshot is parsed internally only after dev lineage is
    established. Only the selected target field is released. Raw containers,
    feedback, adjudication, TM and derived knowledge have no release method.
    """
    def __init__(self, root: Path, manifest: Path, expected_sha256: str):
        self.root = root.resolve()
        self.split = pinned_json(self.root, manifest, expected_sha256)
        validate_split(self.split)
        self._split_identity = digest(self.split)
        self.readers = [FrozenReader(self.root, self.root / row["path"], row["sha256"])
                        for row in self.split["inputs"]]
        self.entries, self.owners = inventory(self.readers)
        if len(self.entries) != self.split["registered_file_denominator"]:
            raise ValueError("inventory denominator changed")
        registered = [r for r in self.entries.values() if r["category"] == "source_original"]
        if len(registered) != self.split["source_denominator"]:
            raise ValueError("source inventory denominator changed")
        for row in self.split["chapters"]:
            original = self.entries.get(row["path"], {})
            if original.get("category") != "source_original" or original.get("sha256") != row["source_revision"]:
                raise ValueError("source identity is not in pinned inventory")

    def _check_frozen(self):
        if digest(self.split) != self._split_identity:
            raise PermissionError("frozen split mutated in memory")

    def source_context(self, anchor: tuple[str, str, str]) -> str:
        self._check_frozen()
        authorize(self.split, "source_context", [anchor])
        source = next(r for r in self.split["chapters"] if key(r) == tuple(anchor))
        return self.owners[source["path"]].read(self.entries[source["path"]]).decode("utf-8")

    def target(self, record_id: str) -> dict:
        self._check_frozen()
        spec = self.split["alignment"]
        record = None
        for row in alignment_rows(self.root, self.root / spec["path"], spec["sha256"]):
            if row.get("record_id") == record_id:
                if record is not None:
                    raise PermissionError("duplicate alignment record identity")
                record = row
        if record is None:
            raise PermissionError("unregistered target record")
        anchor = lineage(self.split, record)
        authorize(self.split, "target", [anchor])  # Before any target snapshot read.
        path = record["artifact_path"]; artifact = self.entries.get(path, {})
        expected_id = hashlib.sha256(json.dumps([path, record["artifact_revision"],
                                                record["record_pointer"], record["field"]],
                                               ensure_ascii=False).encode()).hexdigest()
        if (artifact.get("category") not in {"old_translation", "manifest_or_user_candidate"}
                or artifact.get("sha256") != record["artifact_revision"] or expected_id != record_id
                or record["field"] not in (*TARGET_FIELDS, "<missing_target>")):
            raise PermissionError("unregistered target artifact identity")
        doc = json.loads(self.owners[path].read(artifact))
        segments = [s for s, pointer, _ in iter_segments(doc) if pointer == record["record_pointer"]]
        if len(segments) != 1:
            raise PermissionError("target pointer changed")
        segment = segments[0]; field = record["field"]
        if field == "<missing_target>":
            if any(isinstance(segment.get(f), str) for f in TARGET_FIELDS):
                raise PermissionError("missing-target identity changed")
            target = ""
        else:
            target = segment.get(field)
        source = segment.get("source_text", segment.get("source", ""))
        if (not isinstance(target, str) or not isinstance(source, str)
                or record.get("source_part_sha256") != [text_hash(source)]
                or len(record.get("target_spans", [])) != 1
                or text_hash(target) != record["target_spans"][0]["target_revision"]):
            raise PermissionError("source/target field identity changed")
        return {"record_id": record_id, "source_anchor": list(anchor), "target_text": target,
                "target_revision": text_hash(target), "field": field,
                "legacy_approval": "unverified; not a reference truth", "partition": "development"}

    def feedback(self, *_args, **_kwargs):
        raise PermissionError("feedback/adjudication/derived knowledge withheld pending verified lineage")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--versions", type=Path, required=True)
    parser.add_argument("--versions-sha256", required=True)
    parser.add_argument("--supplemental", nargs=2, action="append", default=[])
    parser.add_argument("--alignment", type=Path, required=True)
    parser.add_argument("--alignment-sha256", required=True)
    parser.add_argument("--alignment-count", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--seed", required=True)
    parser.add_argument("--group-size", type=int, default=10)
    args = parser.parse_args()
    readers = [FrozenReader(args.root, args.versions, args.versions_sha256)]
    readers += [FrozenReader(args.root, Path(path), sha) for path, sha in args.supplemental]
    print(json.dumps(build(args.root, readers, args.alignment, args.alignment_sha256,
                           args.alignment_count, args.output, seed=args.seed, group_size=args.group_size)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
