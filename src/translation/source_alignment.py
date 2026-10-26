"""Versioned source coordinates and conservative, text-based legacy alignment.

Coordinates are half-open Unicode code-point offsets into the exact decoded
UTF-8 source revision. This locates stored source text; it does not evaluate a
translation, infer semantic omission, or select a canonical revision.
"""
from __future__ import annotations

from array import array
from collections import Counter
import hashlib
import json

SCHEMA = "source-span-alignment/1"


def text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


class SourceDocument:
    def __init__(self, text: str, *, revision: str, chapter_id: str):
        if text_hash(text) != revision:
            raise ValueError("source revision does not match exact UTF-8 text")
        self.text = text
        self.revision = revision
        self.chapter_id = chapter_id
        self.paragraphs: list[dict] = []
        self.headings: list[list[int]] = []
        self.offsets = array("I")
        compact: list[str] = []
        occurrences: Counter = Counter()
        lines: list[list[int]] = []

        def finish_paragraph():
            if not lines:
                return
            value = "\n".join(text[a:b] for a, b in lines)
            digest = text_hash(value)
            occurrences[digest] += 1
            self.paragraphs.append({
                "paragraph_id": f"{chapter_id}:p:{digest}:{occurrences[digest]}",
                "display_position": len(self.paragraphs) + 1,
                "source_revision": revision, "content_sha256": digest,
                "spans": [span[:] for span in lines],
                "identity_note": "content and duplicate occurrence; exact source revision is mandatory"})
            lines.clear()

        cursor = 0
        for line in text.splitlines(keepends=True):
            body = line.rstrip("\r\n")
            start, end = cursor, cursor + len(body)
            cursor += len(line)
            if body.startswith("#"):
                finish_paragraph(); self.headings.append([start, end]); continue
            if not body.strip():
                finish_paragraph(); continue
            a = start + len(body) - len(body.lstrip())
            b = end - (len(body) - len(body.rstrip()))
            lines.append([a, b])
            for position in range(a, b):
                char = text[position]
                if not char.isspace():
                    compact.append(char); self.offsets.append(position)
        finish_paragraph()
        self.compact = "".join(compact)

    def to_index(self) -> dict:
        return {"schema": SCHEMA, "chapter_id": self.chapter_id,
                "source_revision": self.revision, "document_span": [0, len(self.text)],
                "coordinate": "unicode_codepoint_half_open", "encoding": "utf-8",
                "paragraphs": self.paragraphs, "heading_spans": self.headings,
                "heading_policy": "retained as source context; excluded from body locator, as in legacy parser",
                "semantic_coverage": "not_evaluated"}

    def locate(self, source_text: str) -> dict:
        needle = "".join(char for char in source_text if not char.isspace())
        if not needle:
            return {"status": "empty_stored_source", "spans": [], "paragraph_ids": [], "occurrences": 0}
        first = self.compact.find(needle)
        if first < 0:
            return {"status": "unmatched_source_version_or_transform", "spans": [], "paragraph_ids": [], "occurrences": 0}
        second = self.compact.find(needle, first + 1)
        if second >= 0:
            return {"status": "ambiguous_repeated_source", "spans": [], "paragraph_ids": [], "occurrences": "at_least_2"}
        positions = self.offsets[first:first + len(needle)]
        spans: list[list[int]] = []
        for position in positions:
            if not spans or self.text[spans[-1][1]:position].strip():
                spans.append([position, position + 1])
            else:
                spans[-1][1] = position + 1
        paragraph_ids = [p["paragraph_id"] for p in self.paragraphs
                         if any(a < y and x < b for a, b in spans for x, y in p["spans"])]
        extracted = "".join(self.text[a:b] for a, b in spans)
        exact = extracted == source_text.strip()
        return {"status": "unique_exact_source" if exact else "unique_layout_match_unverified",
                "spans": spans, "paragraph_ids": paragraph_ids, "occurrences": 1,
                "normalization": "none" if exact else "whitespace_erased_for_location_only",
                "confidence": {"kind": "deterministic_location_not_semantic_probability",
                               "value": 1.0 if exact else None}}


def align_group(document: SourceDocument, source_parts: list[str], targets: list[dict]) -> dict:
    """An explicit group may contain merged sources or split target fragments."""
    locations = [document.locate(part) for part in source_parts]
    source_spans = [span for location in locations for span in location["spans"]]
    resolved = bool(locations) and all(x["status"].startswith("unique_") for x in locations)
    ordered = sorted(source_spans)
    overlap = any(a[1] > b[0] for a, b in zip(ordered, ordered[1:]))
    target_spans = []
    for target in targets:
        text = str(target.get("text") or "")
        target_spans.append({"segment_id": str(target.get("segment_id") or ""),
                             "field": str(target.get("field") or "target_text"),
                             "target_revision": text_hash(text), "span": [0, len(text)],
                             "nonempty": bool(text.strip())})
    status = "located" if resolved and not overlap else "uncertain_source_alignment"
    if not target_spans or not all(x["nonempty"] for x in target_spans):
        status = "empty_target"
    record = {"schema": SCHEMA, "source_revision": document.revision,
              "chapter_id": document.chapter_id, "source_spans": source_spans,
              "source_part_sha256": [text_hash(x) for x in source_parts],
              "source_locations": locations, "target_spans": target_spans,
              "source_parts_reordered": source_spans != ordered, "overlapping_source_parts": overlap,
              "status": status, "semantic_coverage": "not_evaluated",
              "automatic_acceptance": False, "canonical_selection": False}
    record["alignment_id"] = hashlib.sha256(json.dumps(record, sort_keys=True).encode()).hexdigest()
    return record
