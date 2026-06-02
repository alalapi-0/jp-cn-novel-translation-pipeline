#!/usr/bin/env python3
"""Inspect local vector index metadata (JSON mock index MVP).

Read-only: no embedding generation, no cloud API, no .env reads.
Exit codes: 0=PASS, 1=WARNING (empty index, missing metadata, orphans), 2=BLOCKED (parse error).

Future adapters: Chroma, FAISS, SQLite vector extension — keep metadata fields stable.
See docs/embedding_vector_db_design.md and data/schemas/vector_index_metadata.schema.json.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_INDEX = REPO_ROOT / "workspace" / "vector_store" / "index.json"
DEFAULT_MANIFEST = REPO_ROOT / "workspace" / "manifests" / "project_manifest.json"
SCHEMA_PATH = REPO_ROOT / "data" / "schemas" / "vector_index_metadata.schema.json"
EXAMPLE_INDEX = REPO_ROOT / "data" / "examples" / "vector_index_mock.example.json"

REQUIRED_VECTOR_METADATA = (
    "project_id",
    "language_direction",
    "chapter_id",
    "model",
    "version",
)

FILTER_KEYS = ("project_id", "chapter_id", "language_direction")


class Severity(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class Finding:
    code: str
    severity: Severity
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"code": self.code, "severity": self.severity.value, "message": self.message}


@dataclass
class InspectionReport:
    index_path: str
    manifest_path: str | None
    backend: str | None = None
    schema_version: str | None = None
    embedding_model: str | None = None
    embedding_dimension: int | None = None
    vector_count: int = 0
    metadata_keys: list[str] = field(default_factory=list)
    missing_metadata_counts: dict[str, int] = field(default_factory=dict)
    orphan_vectors: list[str] = field(default_factory=list)
    duplicate_ids: list[str] = field(default_factory=list)
    filter_stats: dict[str, Counter] = field(default_factory=dict)
    findings: list[Finding] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "index_path": self.index_path,
            "manifest_path": self.manifest_path,
            "backend": self.backend,
            "schema_version": self.schema_version,
            "embedding_model": self.embedding_model,
            "embedding_dimension": self.embedding_dimension,
            "vector_count": self.vector_count,
            "metadata_keys": self.metadata_keys,
            "missing_metadata_counts": self.missing_metadata_counts,
            "orphan_vectors": self.orphan_vectors,
            "duplicate_ids": self.duplicate_ids,
            "filter_stats": {k: dict(v) for k, v in self.filter_stats.items()},
            "findings": [f.to_dict() for f in self.findings],
        }


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_json_file(path: Path) -> tuple[dict[str, Any] | None, Finding | None]:
    if not path.is_file():
        return None, None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return None, Finding("index_parse_error", Severity.FAIL, f"cannot parse {_rel(path)}: {exc}")
    if not isinstance(data, dict):
        return None, Finding("index_shape_error", Severity.FAIL, f"expected JSON object in {_rel(path)}")
    return data, None


def _manifest_segment_keys(manifest: dict[str, Any]) -> set[tuple[str, str]]:
    keys: set[tuple[str, str]] = set()
    segments = manifest.get("segments") or []
    for item in segments:
        if not isinstance(item, dict):
            continue
        chapter_id = item.get("chapter_id")
        segment_id = item.get("segment_id")
        if chapter_id and segment_id:
            keys.add((str(chapter_id), str(segment_id)))
    return keys


def inspect_index(
    index_data: dict[str, Any] | None,
    *,
    index_path: Path,
    manifest_data: dict[str, Any] | None = None,
    manifest_path: Path | None = None,
) -> InspectionReport:
    report = InspectionReport(
        index_path=_rel(index_path),
        manifest_path=_rel(manifest_path) if manifest_path else None,
    )

    if index_data is None:
        report.findings.append(
            Finding(
                "index_missing",
                Severity.WARN,
                f"no index at {report.index_path}; soft fallback — other rounds may continue",
            )
        )
        return report

    meta = index_data.get("index_metadata") or {}
    vectors = index_data.get("vectors")
    if not isinstance(meta, dict) or not isinstance(vectors, list):
        report.findings.append(
            Finding(
                "index_structure_invalid",
                Severity.FAIL,
                "index must contain index_metadata object and vectors array",
            )
        )
        return report

    report.backend = str(meta.get("backend") or "unknown")
    report.schema_version = meta.get("schema_version")
    report.embedding_model = meta.get("embedding_model")
    dim = meta.get("embedding_dimension")
    report.embedding_dimension = int(dim) if isinstance(dim, int) else None
    report.vector_count = len(vectors)

    if report.vector_count == 0:
        report.findings.append(
            Finding("index_empty", Severity.WARN, "index file exists but vectors array is empty")
        )

    all_keys: set[str] = set()
    missing_counter: Counter[str] = Counter()
    id_counter: Counter[str] = Counter()
    filter_stats: dict[str, Counter] = {k: Counter() for k in FILTER_KEYS}

    for idx, item in enumerate(vectors):
        if not isinstance(item, dict):
            report.findings.append(
                Finding(
                    "vector_entry_invalid",
                    Severity.FAIL,
                    f"vectors[{idx}] is not an object",
                )
            )
            continue
        embedding_id = str(item.get("embedding_id") or f"<missing-id-{idx}>")
        id_counter[embedding_id] += 1
        md = item.get("metadata")
        if not isinstance(md, dict):
            missing_counter["metadata"] += 1
            report.findings.append(
                Finding(
                    "metadata_missing_object",
                    Severity.WARN,
                    f"{embedding_id}: metadata object missing",
                )
            )
            continue
        all_keys.update(md.keys())
        for key in REQUIRED_VECTOR_METADATA:
            value = md.get(key)
            if value is None or (isinstance(value, str) and not value.strip()):
                missing_counter[key] += 1
                report.findings.append(
                    Finding(
                        "metadata_field_missing",
                        Severity.WARN,
                        f"{embedding_id}: missing required metadata '{key}'",
                    )
                )
        for fk in FILTER_KEYS:
            fv = md.get(fk)
            if fv is not None:
                filter_stats[fk][str(fv)] += 1

    report.metadata_keys = sorted(all_keys)
    report.missing_metadata_counts = dict(missing_counter)
    report.duplicate_ids = [eid for eid, count in id_counter.items() if count > 1]
    report.filter_stats = filter_stats

    if report.duplicate_ids:
        report.findings.append(
            Finding(
                "duplicate_embedding_id",
                Severity.WARN,
                f"duplicate embedding_id values: {', '.join(report.duplicate_ids)}",
            )
        )

    manifest_keys = _manifest_segment_keys(manifest_data) if manifest_data else set()
    if manifest_data and not manifest_keys:
        report.findings.append(
            Finding(
                "manifest_empty_segments",
                Severity.WARN,
                "manifest present but segments list is empty — all vectors treated as orphans",
            )
        )

    for item in vectors:
        if not isinstance(item, dict):
            continue
        embedding_id = str(item.get("embedding_id") or "")
        md = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        chapter_id = md.get("chapter_id")
        segment_id = md.get("segment_id")
        if manifest_data is None:
            continue
        if not chapter_id or not segment_id:
            report.orphan_vectors.append(embedding_id or "<unknown>")
            continue
        if (str(chapter_id), str(segment_id)) not in manifest_keys:
            report.orphan_vectors.append(embedding_id)

    if report.orphan_vectors:
        report.findings.append(
            Finding(
                "orphan_vectors",
                Severity.WARN,
                f"{len(report.orphan_vectors)} vector(s) not in source manifest: "
                f"{', '.join(report.orphan_vectors[:5])}"
                + (" ..." if len(report.orphan_vectors) > 5 else ""),
            )
        )

    index_model = meta.get("embedding_model")
    if index_model:
        for item in vectors:
            if not isinstance(item, dict):
                continue
            md = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
            record_model = md.get("model")
            if record_model and str(record_model) != str(index_model):
                report.findings.append(
                    Finding(
                        "model_drift",
                        Severity.WARN,
                        f"{item.get('embedding_id')}: metadata.model != index embedding_model",
                    )
                )
                break

    if not report.findings:
        report.findings.append(
            Finding("index_ok", Severity.PASS, f"{report.vector_count} vector(s) inspected")
        )

    return report


def aggregate_exit_code(findings: Iterable[Finding]) -> int:
    severities = {f.severity for f in findings}
    if Severity.FAIL in severities:
        return 2
    if Severity.WARN in severities:
        return 1
    return 0


def sample_vectors(index_data: dict[str, Any] | None, n: int) -> list[dict[str, Any]]:
    if not index_data or n <= 0:
        return []
    vectors = index_data.get("vectors") or []
    samples: list[dict[str, Any]] = []
    for item in vectors[:n]:
        if not isinstance(item, dict):
            continue
        md = item.get("metadata") if isinstance(item.get("metadata"), dict) else {}
        samples.append(
            {
                "embedding_id": item.get("embedding_id"),
                "chapter_id": md.get("chapter_id"),
                "segment_id": md.get("segment_id"),
                "text_type": md.get("text_type"),
                "model": md.get("model"),
                "version": md.get("version"),
            }
        )
    return samples


def run_inspection(
    index_path: Path,
    manifest_path: Path | None,
) -> tuple[InspectionReport, dict[str, Any] | None, Finding | None]:
    index_data, parse_error = load_json_file(index_path)
    if parse_error:
        report = InspectionReport(index_path=_rel(index_path), manifest_path=_rel(manifest_path) if manifest_path else None)
        report.findings.append(parse_error)
        return report, None, parse_error

    manifest_data = None
    if manifest_path and manifest_path.is_file():
        manifest_data, manifest_error = load_json_file(manifest_path)
        if manifest_error:
            report = inspect_index(index_data, index_path=index_path, manifest_path=manifest_path)
            report.findings.append(manifest_error)
            return report, index_data, manifest_error
    elif manifest_path:
        report = inspect_index(index_data, index_path=index_path, manifest_path=manifest_path)
        report.findings.append(
            Finding(
                "manifest_missing",
                Severity.WARN,
                f"manifest not found at {_rel(manifest_path)}; orphan check skipped",
            )
        )
        return report, index_data, None

    report = inspect_index(
        index_data,
        index_path=index_path,
        manifest_data=manifest_data,
        manifest_path=manifest_path,
    )
    return report, index_data, None


def write_text_report(report: InspectionReport, exit_code: int, sample: Sequence[dict[str, Any]]) -> str:
    lines = [
        "# Vector DB Inspection",
        "",
        f"- Index: {report.index_path}",
        f"- Manifest: {report.manifest_path or '(none)'}",
        f"- Exit code: {exit_code}",
        "",
        "## Summary",
        "",
        f"- backend: {report.backend or 'n/a'}",
        f"- schema_version: {report.schema_version or 'n/a'}",
        f"- embedding_model: {report.embedding_model or 'n/a'}",
        f"- embedding_dimension: {report.embedding_dimension or 'n/a'}",
        f"- vector_count: {report.vector_count}",
        f"- metadata_keys: {', '.join(report.metadata_keys) or '(none)'}",
        f"- orphan_vectors: {len(report.orphan_vectors)}",
        f"- duplicate_ids: {len(report.duplicate_ids)}",
        "",
        "## Findings",
        "",
    ]
    for f in report.findings:
        lines.append(f"- [{f.severity.value}] {f.code}: {f.message}")
    if sample:
        lines.extend(["", "## Sample (redacted)", ""])
        for row in sample:
            lines.append(f"- {json.dumps(row, ensure_ascii=False)}")
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Inspect local vector index metadata (read-only)")
    parser.add_argument(
        "--index",
        type=Path,
        default=DEFAULT_INDEX,
        help=f"Path to JSON index (default: {_rel(DEFAULT_INDEX)})",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST,
        help=f"Optional segment manifest for orphan detection (default: {_rel(DEFAULT_MANIFEST)})",
    )
    parser.add_argument("--example", action="store_true", help=f"Inspect bundled example at {_rel(EXAMPLE_INDEX)}")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON to stdout")
    parser.add_argument("--sample", type=int, default=0, help="Include N redacted vector samples in text output")
    parser.add_argument(
        "--report",
        type=Path,
        default=None,
        help="Write markdown report path (default: stdout only unless set)",
    )
    args = parser.parse_args(argv)

    index_path = EXAMPLE_INDEX if args.example else args.index
    manifest_path = args.manifest
    if args.example:
        manifest_path = REPO_ROOT / "data" / "examples" / "vector_source_manifest.example.json"

    report, index_data, _ = run_inspection(index_path.resolve(), manifest_path.resolve() if manifest_path else None)
    exit_code = aggregate_exit_code(report.findings)
    samples = sample_vectors(index_data, args.sample)

    payload = report.to_dict()
    payload["exit_code"] = exit_code
    payload["schema_path"] = _rel(SCHEMA_PATH)
    payload["sample"] = list(samples)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        text = write_text_report(report, exit_code, samples)
        if args.report:
            args.report.parent.mkdir(parents=True, exist_ok=True)
            args.report.write_text(text, encoding="utf-8")
            print(f"report: {args.report}")
        else:
            print(text, end="")
        label = {0: "PASS", 1: "WARNING", 2: "BLOCKED"}[exit_code]
        print(f"vector_db_inspect: {label} (exit {exit_code})", file=sys.stderr)

    return exit_code


if __name__ == "__main__":
    sys.exit(main())
