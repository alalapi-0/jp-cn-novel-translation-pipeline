#!/usr/bin/env python3
"""Freeze explicitly registered local inputs without changing any original.

This is private evidence for the existing optimization state, not a scheduler or
canonical resolver. Unknown inputs are recorded but never opened. No model/API.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from translation.run_progress import atomic_write_json

IDENTITY = ("device", "inode", "bytes", "mtime_ns")


def identity(stat: os.stat_result) -> dict:
    return {"device": stat.st_dev, "inode": stat.st_ino, "bytes": stat.st_size,
            "mtime_ns": stat.st_mtime_ns}


def ordinary_path(root: Path, relative: str) -> Path:
    rel = Path(relative)
    if rel.is_absolute() or ".." in rel.parts or any(p == ".env" or p.startswith(".env.") for p in rel.parts):
        raise ValueError("secret or non-relative input path refused")
    path = root / rel
    if any((root / parent).is_symlink() for parent in (rel, *rel.parents)):
        raise ValueError("symlink input refused")
    if not path.resolve().is_relative_to(root.resolve()) or not path.is_file():
        raise ValueError("input must be an ordinary registered file")
    return path


def freeze(registry_path: Path, output: Path, *, max_bytes: int = 128 * 1024 * 1024) -> dict:
    return freeze_registered(ROOT, registry_path, output, max_bytes=max_bytes)


def validate_manifest(result: dict, registry: dict, digest: str) -> None:
    entries = registry["entries"]
    eligible = [x for x in entries if x["read_eligibility"].startswith("registered_local_")]
    if (result.get("schema") != "optimization-input-versions/1" or result.get("task") != "P1.R02.T01"
            or result.get("registration_sha256") != digest
            or result.get("registered_denominator") != len(entries)
            or result.get("eligible_denominator") != len(eligible)
            or result.get("source_denominator") != sum(x["category"] == "source_original" for x in eligible)
            or not isinstance(result.get("entries"), list) or len(result["entries"]) != len(entries)
            or result.get("exclusions") != registry.get("exclusions", [])):
        raise ValueError("frozen manifest schema or denominator mismatch")
    for original, version in zip(entries, result["entries"]):
        if not isinstance(version, dict) or any(version.get(key) != value for key, value in original.items()):
            raise ValueError("frozen manifest registration record mismatch")
        if original["read_eligibility"].startswith("registered_local_"):
            sha = version.get("sha256", "")
            if (not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha)
                    or version.get("snapshot") != f"blobs/{sha}"
                    or version.get("freeze_status") != "read_only_recoverable_version"):
                raise ValueError("frozen manifest version identity mismatch")
        elif (version.get("freeze_status") != "excluded_without_content_read"
              or "sha256" in version or "snapshot" in version):
            raise ValueError("excluded source unexpectedly versioned")


def freeze_registered(root: Path, registry_path: Path, output: Path, *, max_bytes: int = 128 * 1024 * 1024) -> dict:
    root = root.resolve()
    output = output.absolute()
    private = root / "workspace/tooling/optimization"
    registry_path = registry_path.absolute()
    # Check the declared role and all path components before any content read.
    if registry_path.name != "registration.json" or not registry_path.is_relative_to(private):
        raise ValueError("registry must be a private optimization registration.json")
    registry_path = ordinary_path(root, str(registry_path.relative_to(root)))
    if registry_path.stat().st_nlink != 1:
        raise ValueError("registry must not be a hardlink alias")
    raw = registry_path.read_bytes()
    registry = json.loads(raw)
    if registry.get("schema") != "optimization-file-registration/1":
        raise ValueError("unsupported registration schema")
    if Path(registry["root"]).resolve() != root:
        raise ValueError("registry root must be the explicitly owned repository")
    allowed_output = root / "workspace/tooling/optimization"
    if not output.resolve().is_relative_to(allowed_output.resolve()):
        raise ValueError("snapshot output must stay in private optimization evidence")
    if any(parent.is_symlink() for parent in (output, *output.parents)):
        raise ValueError("symlink output refused")
    digest = hashlib.sha256(raw).hexdigest()
    manifest = output / "versions.json"
    if manifest.is_symlink():
        raise ValueError("symlink manifest refused")
    entries = registry["entries"]
    paths = [item["path"] for item in entries]
    if len(paths) != len(set(paths)):
        raise ValueError("duplicate registration path")
    if manifest.exists():
        ordinary_path(root, str(manifest.relative_to(root)))
        result = json.loads(manifest.read_text())
        if result.get("registration_sha256") != digest:
            raise ValueError("frozen denominator already exists for a different registration")
        validate_manifest(result, registry, digest)
        verify(result, output)
        return result
    eligible = [item for item in entries if item["read_eligibility"].startswith("registered_local_")]
    requested = sum(item["bytes"] for item in eligible)
    if requested > max_bytes:
        raise ValueError("registered snapshot exceeds bounded disk budget")
    if shutil.disk_usage(allowed_output).free < requested + 16 * 1024 * 1024:
        raise ValueError("insufficient persistent storage for registered snapshot")
    output.mkdir(parents=True, exist_ok=True)
    blobs = output / "blobs"
    if blobs.is_symlink():
        raise ValueError("symlink snapshot directory refused")
    blobs.mkdir(exist_ok=True)
    versions = []; copied_bytes = 0
    for item in entries:
        record = dict(item)
        if not item["read_eligibility"].startswith("registered_local_"):
            record["freeze_status"] = "excluded_without_content_read"
            versions.append(record)
            continue
        source = ordinary_path(root, item["path"])
        expected = {key: item[key] for key in IDENTITY}
        with os.fdopen(os.open(source, os.O_RDONLY | os.O_NOFOLLOW), "rb") as stream:
            if identity(os.fstat(stream.fileno())) != expected:
                raise ValueError(f"registered version changed: {item['path']}")
            hasher = hashlib.sha256()
            with tempfile.NamedTemporaryFile(prefix="freeze-", dir=blobs, delete=False) as target:
                temporary = Path(target.name)
                try:
                    while chunk := stream.read(512 * 1024):
                        hasher.update(chunk); target.write(chunk)
                    target.flush(); os.fsync(target.fileno())
                    if identity(os.fstat(stream.fileno())) != expected or identity(source.stat()) != expected:
                        raise ValueError(f"input changed during freeze: {item['path']}")
                    sha = hasher.hexdigest(); blob = blobs / sha
                    if blob.exists():
                        if blob.is_symlink():
                            raise ValueError("existing snapshot blob is corrupt")
                        with blob.open("rb") as previous:
                            if hashlib.file_digest(previous, "sha256").hexdigest() != sha:
                                raise ValueError("existing snapshot blob is corrupt")
                    else:
                        os.link(temporary, blob); blob.chmod(0o400)
                        copied_bytes += expected["bytes"]
                    record.update(sha256=sha, snapshot=f"blobs/{sha}",
                                  freeze_status="read_only_recoverable_version", approval="unverified_legacy_labels")
                finally:
                    temporary.unlink(missing_ok=True)
        versions.append(record)
    result = {"schema": "optimization-input-versions/1", "task": "P1.R02.T01",
              "registration_sha256": digest, "registered_denominator": len(entries),
              "eligible_denominator": len(eligible), "source_denominator": sum(x["category"] == "source_original" for x in eligible),
              "snapshot_bytes_created": copied_bytes, "entries": versions,
              "exclusions": registry.get("exclusions", []), "canonical_selection": "none; inventory is not acceptance"}
    validate_manifest(result, registry, digest)
    atomic_write_json(manifest, result)
    manifest.chmod(0o400)
    return result


def verify(result: dict, output: Path) -> None:
    """Check each distinct immutable blob; no original or production write."""
    checked = set()
    for record in result["entries"]:
        if record.get("snapshot") and record["snapshot"] not in checked:
            blob = ordinary_path(output, record["snapshot"])
            with blob.open("rb") as stream:
                actual = hashlib.file_digest(stream, "sha256").hexdigest()
            if actual != record["sha256"]:
                raise ValueError("snapshot verification failed")
            checked.add(record["snapshot"])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--registry", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    result = freeze(args.registry, args.output)
    verify(result, args.output)
    print(json.dumps({key: result[key] for key in ("registered_denominator", "eligible_denominator", "source_denominator", "snapshot_bytes_created")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
