#!/usr/bin/env python3
"""Build private source/target span evidence from a pinned frozen inventory.

No original, canonical, scheduler, or approval writes. Legacy text is compared
only for source-location geometry. No model, external API, or semantic verdict.
"""
from __future__ import annotations

import argparse
from collections import Counter, OrderedDict
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from translation.source_alignment import SourceDocument, align_group, text_hash
from translation.run_progress import atomic_write_json

TARGET_FIELDS = ("draft_text", "target_text", "refined_text", "draft", "translation")
MAX_OUTPUT_BYTES = 256 * 1024 * 1024


def private_path(root: Path, path: Path, *, name: str | None = None) -> Path:
    path = path.absolute()
    if (not path.is_relative_to(root / "workspace/tooling/optimization")
            or ".." in path.parts or (name and path.name != name)
            or any(p.is_symlink() for p in (path, *path.parents))):
        raise ValueError("expected an ordinary private optimization path")
    return path


class FrozenReader:
    def __init__(self, root: Path, manifest: Path, expected_sha256: str):
        self.root = root.resolve()
        self.path = private_path(self.root, manifest, name="versions.json")
        if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
            raise ValueError("pinned versions hash required")
        raw = self.path.read_bytes()
        if hashlib.sha256(raw).hexdigest() != expected_sha256:
            raise ValueError("frozen inventory identity changed")
        self.versions = json.loads(raw)
        if (self.versions.get("schema") != "optimization-input-versions/1"
                or len(self.versions.get("entries", [])) != self.versions.get("registered_denominator")):
            raise ValueError("invalid frozen inventory denominator")
        self.entries_by_path = {row["path"]: row for row in self.versions["entries"]}
        if len(self.entries_by_path) != len(self.versions["entries"]):
            raise ValueError("duplicate frozen inventory path")
        self.hash = expected_sha256

    def read(self, row: dict) -> bytes:
        if row != self.entries_by_path.get(row.get("path")):
            raise ValueError("snapshot descriptor is not in the pinned inventory")
        sha = row.get("sha256", "")
        if (row.get("freeze_status") != "read_only_recoverable_version"
                or not re.fullmatch(r"[0-9a-f]{64}", sha)
                or row.get("snapshot") != f"blobs/{sha}"):
            raise ValueError("unregistered or excluded snapshot")
        blob = private_path(self.root, self.path.parent / row["snapshot"])
        if blob.stat().st_size > 16 * 1024 * 1024:
            raise ValueError("snapshot exceeds bounded per-file read")
        raw = blob.read_bytes()
        if len(raw) != row["bytes"] or hashlib.sha256(raw).hexdigest() != sha:
            raise ValueError("snapshot content identity changed")
        return raw


def number(value) -> int | None:
    match = re.fullmatch(r"(?:ch-?)?(\d+)", str(value))
    return int(match[1]) if match else None


def iter_segments(doc: dict):
    def within(container, pointer, chapter):
        segments = container.get("segments")
        for i, segment in enumerate(segments if isinstance(segments, list) else []):
            if isinstance(segment, dict):
                yield segment, f"{pointer}.segments[{i}]", chapter
        paragraphs = container.get("paragraphs")
        for i, paragraph in enumerate(paragraphs if isinstance(paragraphs, list) else []):
            if isinstance(paragraph, dict):
                nested = paragraph.get("segments")
                for j, segment in enumerate(nested if isinstance(nested, list) else []):
                    if isinstance(segment, dict):
                        yield segment, f"{pointer}.paragraphs[{i}].segments[{j}]", chapter
    if isinstance(doc.get("chapters"), list):
        for i, chapter in enumerate(doc["chapters"]):
            if isinstance(chapter, dict):
                yield from within(chapter, f"$.chapters[{i}]", chapter.get("chapter_id"))
    else:
        yield from within(doc, "$", doc.get("chapter_id"))


def build(root: Path, versions_path: Path, expected_sha256: str, output: Path,
          *, supplemental: tuple[tuple[Path, str], ...] = ()) -> dict:
    root = root.resolve()
    reader = FrozenReader(root, versions_path, expected_sha256)
    readers = [reader] + [FrozenReader(root, path, sha) for path, sha in supplemental]
    output = private_path(root, output)
    if output.exists():
        raise ValueError("alignment candidate already exists; preserve it rather than overwrite")
    output.mkdir(parents=True)
    entries = []
    owners = {}
    for current in readers:
        for row in current.versions["entries"]:
            if row["path"] in owners:
                raise ValueError("supplemental inventories must have disjoint registered paths")
            entries.append(row); owners[row["path"]] = current
    def read(row):
        return owners[row["path"]].read(row)
    sources = {}; documents = OrderedDict(); source_counts = Counter(); totals = Counter()
    artifacts = []; stored_bytes = 0

    def emit(handle, value):
        nonlocal stored_bytes
        raw = json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n"
        stored_bytes += len(raw.encode("utf-8"))
        if stored_bytes > MAX_OUTPUT_BYTES:
            raise ValueError("alignment evidence exceeds bounded output size")
        handle.write(raw)

    def load_source(key):
        if key not in documents:
            row = sources[key]
            text = read(row).decode("utf-8")
            documents[key] = SourceDocument(text, revision=row["sha256"], chapter_id=f"ch-{key[1]:03d}")
            if len(documents) > 8:
                documents.popitem(last=False)
        documents.move_to_end(key)
        return documents[key]

    with (output / "source-spans.jsonl").open("x", encoding="utf-8") as source_out:
        for row in entries:
            if row["category"] != "source_original":
                continue
            match = re.match(r"^(\d+)", Path(row["path"]).name)
            direction = "JP_TO_CN" if row["path"].startswith("input_jp/") else "CN_TO_JP"
            if not match:
                artifacts.append({"path": row["path"], "status": "unknown_source_chapter_identity"}); continue
            key = (direction, int(match[1]))
            if key in sources:
                raise ValueError("multiple original source revisions share chapter identity")
            sources[key] = row
            doc = load_source(key)
            index = doc.to_index(); index.update(path=row["path"], language_direction=direction)
            emit(source_out, index)
            source_counts["files"] += 1; source_counts["paragraphs"] += len(doc.paragraphs)
            source_counts["headings"] += len(doc.headings)
            source_counts["empty_body_files"] += not bool(doc.paragraphs)
    with (output / "legacy-alignment.jsonl").open("x", encoding="utf-8") as aligned_out:
        for row in entries:
            if row["category"] not in {"old_translation", "manifest_or_user_candidate"}:
                continue
            doc = json.loads(read(row).decode("utf-8"))
            if not isinstance(doc, dict):
                artifacts.append({"path": row["path"], "status": "unsupported_json_container"}); continue
            direction = doc.get("language_direction")
            ids = Counter(); local = Counter(); present = 0
            for segment, pointer, chapter in iter_segments(doc):
                present += 1; totals["legacy_segment_records"] += 1
                identity = str(segment.get("segment_id") or segment.get("id") or "")
                ids[identity] += 1
                chapter_num = number(segment.get("chapter_id", segment.get("chapter", chapter)))
                if chapter_num is None:
                    match = re.match(r"^ch-(\d+)-seg-", identity)
                    chapter_num = int(match[1]) if match else None
                key = (direction, chapter_num)
                source = segment.get("source_text", segment.get("source", ""))
                if not isinstance(source, str):
                    source = ""
                fields = [field for field in TARGET_FIELDS if field in segment and isinstance(segment[field], str)]
                fields = fields or ["<missing_target>"]
                for field in fields:
                    if key in sources:
                        result = align_group(load_source(key), [source], [{
                            "text": segment.get(field, ""), "field": field, "segment_id": identity}])
                    else:
                        target = segment.get(field, "")
                        result = {"status": "unresolved_original_source_identity", "source_spans": [],
                                  "source_revision": None,
                                  "target_spans": [{"field": field, "segment_id": identity,
                                                    "target_revision": text_hash(target),
                                                    "span": [0, len(target)], "nonempty": bool(target.strip())}],
                                  "semantic_coverage": "not_evaluated",
                                  "automatic_acceptance": False, "canonical_selection": False}
                    result.update(artifact_path=row["path"], artifact_revision=row["sha256"],
                                  record_pointer=pointer, field=field, legacy_segment_id=identity,
                                  legacy_approval="unverified; stored labels are not approval evidence")
                    result["record_id"] = hashlib.sha256(json.dumps(
                        [row["path"], row["sha256"], pointer, field], ensure_ascii=False).encode()).hexdigest()
                    emit(aligned_out, result)
                    for location in result.get("source_locations", []):
                        totals["source_locator:" + location["status"]] += 1
                    totals[result["status"]] += 1; local[result["status"]] += 1
                    totals["target_field_records"] += 1
            artifacts.append({"path": row["path"], "artifact_revision": row["sha256"],
                              "legacy_records": present, "alignment_counts": dict(local),
                              "duplicate_legacy_ids": {key: value for key, value in ids.items() if value > 1},
                              "status": "processed_as_legacy_candidate" if present else "metadata_only_or_unsupported_alignment_shape"})
    result = {"schema": "optimization-alignment-evidence/1", "versions_sha256": reader.hash,
              "version_inputs": [{"path": str(r.path.relative_to(root)), "sha256": r.hash,
                                  "registered_denominator": r.versions["registered_denominator"]} for r in readers],
              "original_file_denominator": reader.versions["registered_denominator"],
              "registered_file_denominator": sum(r.versions["registered_denominator"] for r in readers),
              "frozen_source_denominator": sum(r.versions["source_denominator"] for r in readers),
              "source_index": dict(source_counts), "alignment_counts": dict(totals),
              "artifact_diagnostics": artifacts, "evidence_bytes": stored_bytes,
              "semantic_coverage": "not_evaluated", "canonical_selection": "none",
              "limitations": ["Textual location is not translation fidelity or semantic coverage.",
                              "Whitespace-only matches remain unverified; repeated source is ambiguous.",
                              "Standalone exports without source-version evidence are not forced onto ordinal IDs."]}
    for name in ("source-spans.jsonl", "legacy-alignment.jsonl"):
        with (output / name).open("rb") as stream:
            result[name + "_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    atomic_write_json(output / "summary.json", result)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--versions", type=Path, required=True)
    parser.add_argument("--expected-versions-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--supplemental-versions", type=Path)
    parser.add_argument("--expected-supplemental-sha256")
    args = parser.parse_args()
    if bool(args.supplemental_versions) != bool(args.expected_supplemental_sha256):
        parser.error("supplemental versions and pinned hash must be supplied together")
    extra = ((args.supplemental_versions, args.expected_supplemental_sha256),) if args.supplemental_versions else ()
    result = build(ROOT, args.versions, args.expected_versions_sha256, args.output, supplemental=extra)
    print(json.dumps({key: result[key] for key in ("source_index", "alignment_counts", "evidence_bytes")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
