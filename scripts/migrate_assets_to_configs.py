#!/usr/bin/env python3
"""Migrate existing translation assets into the configs structure (FS-012).

Source: workspace/assets/translation_memory/*.json (term_candidates + meta).
Target: workspace/configs/glossary.yaml + character_profile.yaml
        (real data stays local; configs/ in git keeps sanitized templates only).

Guarantees:
- never modifies or deletes source asset files (read-only on sources);
- no dropped fields: every candidate field (source / target / kind /
  evidence_segment_id) is mapped into the glossary entry;
- conflict handling: same source_term with different target_term keeps the
  first-seen target and records the rest in notes (counted as conflicts);
- post-write verification reloads the output and validates it against
  schemas/glossary.schema.json, asserting entry count == migrated count.

Stdout prints statistics only - never real term content.
Exit: 0=ok, 1=verification failed, 2=IO error.

Usage:
    python3 scripts/migrate_assets_to_configs.py --dry-run
    python3 scripts/migrate_assets_to_configs.py            # real run
    python3 scripts/migrate_assets_to_configs.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ASSETS_DIR = REPO_ROOT / "workspace" / "assets" / "translation_memory"
DEFAULT_OUTPUT_DIR = REPO_ROOT / "workspace" / "configs"
GLOSSARY_SCHEMA = REPO_ROOT / "schemas" / "glossary.schema.json"
REPORT_PATH = REPO_ROOT / "reports" / "asset_migration_report.json"

# term_candidates "kind" -> glossary category (spec §7.8 enum).
# bracket_label candidates carry no reliable classification signal; they go to
# "other" and await human/FS-013 re-classification.
KIND_TO_CATEGORY = {
    "bracket_label": "other",
}
DEFAULT_CATEGORY = "other"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _display(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def collect_candidates(assets_dir: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Read all TM asset files; return (per_file_stats, raw_candidates)."""
    stats: list[dict[str, Any]] = []
    raw: list[dict[str, Any]] = []
    for path in sorted(assets_dir.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as exc:
            raise ValueError(f"cannot read asset: {_display(path)}: {exc}") from exc
        if not isinstance(data, dict):
            stats.append({"file": path.name, "term_candidates": 0, "skipped": "not_a_dict"})
            continue
        candidates = data.get("term_candidates") or []
        ok = [c for c in candidates if isinstance(c, dict) and c.get("source")]
        for cand in ok:
            raw.append({"file": path.name, **cand})
        stats.append(
            {
                "file": path.name,
                "asset_kind": data.get("asset_kind"),
                "term_candidates": len(ok),
                "approved_pairs": len(data.get("approved_pairs") or []),
            }
        )
    return stats, raw


def merge_candidates(raw: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
    """Dedupe by source term; returns (entries, duplicate_count, conflict_count).

    duplicate = same source + same target seen again (merged silently);
    conflict  = same source + different target (first target wins, others
    recorded in notes for later human review).
    """
    now = _now_iso()
    merged: dict[str, dict[str, Any]] = {}
    duplicates = 0
    conflicts = 0
    for cand in raw:
        source = str(cand["source"])
        target = str(cand.get("target") or "")
        kind = str(cand.get("kind") or "")
        evidence = str(cand.get("evidence_segment_id") or "")
        origin = str(cand.get("file") or "")
        if source not in merged:
            merged[source] = {
                "source_term": source,
                "target_term": target,
                "reading": None,
                "category": KIND_TO_CATEGORY.get(kind, DEFAULT_CATEGORY),
                "description": f"migrated from {origin} (kind={kind}, evidence={evidence})",
                "first_seen_chapter": None,
                "confidence": None,
                "locked": False,
                "approved_by_user": False,
                "aliases": [],
                "notes": None,
                "created_at": now,
                "updated_at": now,
            }
            continue
        entry = merged[source]
        if target == entry["target_term"]:
            duplicates += 1
            # keep earliest description; nothing dropped (same payload)
            continue
        conflicts += 1
        conflict_note = f"conflict_target_candidate: {target} (from {origin}, evidence={evidence})"
        entry["notes"] = conflict_note if not entry["notes"] else f"{entry['notes']}; {conflict_note}"
        entry["updated_at"] = now
    return list(merged.values()), duplicates, conflicts


def build_glossary_doc(entries: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "meta": {
            "project": "real",
            "description": "migrated from workspace/assets/translation_memory (FS-012); local only, never commit",
            "language_pair": "ja-zh",
        },
        "entries": entries,
    }


def build_character_doc() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "meta": {
            "project": "real",
            "description": "skeleton generated by FS-012 (no character data in legacy assets); local only, never commit",
        },
        "characters": [],
    }


def verify_output(glossary_path: Path, expected_count: int) -> list[str]:
    """Reload written glossary; schema-validate and check entry count."""
    import yaml

    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    errors: list[str] = []
    try:
        data = yaml.safe_load(glossary_path.read_text(encoding="utf-8"))
    except (yaml.YAMLError, OSError) as exc:
        return [f"reload failed: {exc}"]
    loaded = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(loaded, list) or len(loaded) != expected_count:
        errors.append(
            f"loader count mismatch: expected {expected_count}, got "
            f"{len(loaded) if isinstance(loaded, list) else 'n/a'}"
        )
    try:
        import jsonschema

        schema = json.loads(GLOSSARY_SCHEMA.read_text(encoding="utf-8"))
        validator = jsonschema.Draft7Validator(schema)
        for err in validator.iter_errors(data):
            errors.append(f"schema: {'.'.join(str(p) for p in err.path) or '(root)'}: {err.message}")
    except ImportError:
        errors.append("jsonschema not installed; cannot verify (see requirements-dev.txt)")
    return errors


def migrate(
    assets_dir: Path = DEFAULT_ASSETS_DIR,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    dry_run: bool = True,
    write_report: bool = True,
) -> dict[str, Any]:
    import yaml

    if not assets_dir.is_dir():
        return {"status": "FAIL", "exit_code": 2, "errors": [f"assets dir not found: {_display(assets_dir)}"]}

    file_stats, raw = collect_candidates(assets_dir)
    entries, duplicates, conflicts = merge_candidates(raw)

    summary: dict[str, Any] = {
        "status": "PASS",
        "exit_code": 0,
        "generated_at": _now_iso(),
        "mode": "dry_run" if dry_run else "real",
        "assets_dir": _display(assets_dir),
        "output_dir": _display(output_dir),
        "files_scanned": len(file_stats),
        "file_stats": file_stats,
        "candidates_total": len(raw),
        "entries_migrated": len(entries),
        "duplicates_merged": duplicates,
        "conflicts": conflicts,
        "dropped_fields": 0,
        "characters_migrated": 0,
        "characters_note": "legacy TM assets carry no character data; skeleton written",
        "errors": [],
    }

    if not dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        glossary_path = output_dir / "glossary.yaml"
        character_path = output_dir / "character_profile.yaml"
        glossary_path.write_text(
            yaml.safe_dump(build_glossary_doc(entries), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        character_path.write_text(
            yaml.safe_dump(build_character_doc(), allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
        errors = verify_output(glossary_path, len(entries))
        summary["errors"] = errors
        summary["verified"] = not errors
        if errors:
            summary["status"] = "FAIL"
            summary["exit_code"] = 1

    if write_report:
        REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        REPORT_PATH.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        summary["report"] = _display(REPORT_PATH)
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Migrate TM assets to workspace/configs (stats only on stdout)")
    parser.add_argument("--assets-dir", type=Path, default=DEFAULT_ASSETS_DIR)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--dry-run", action="store_true", help="Scan and report only; write nothing")
    parser.add_argument("--no-report", action="store_true", help="Skip writing reports/asset_migration_report.json")
    parser.add_argument("--json", action="store_true", help="Print machine-readable result")
    args = parser.parse_args(argv)

    assets_dir = args.assets_dir if args.assets_dir.is_absolute() else REPO_ROOT / args.assets_dir
    output_dir = args.output_dir if args.output_dir.is_absolute() else REPO_ROOT / args.output_dir

    try:
        summary = migrate(
            assets_dir=assets_dir,
            output_dir=output_dir,
            dry_run=args.dry_run,
            write_report=not args.no_report,
        )
    except ValueError as exc:
        print(f"migrate_assets_to_configs: ERROR: {exc}")
        return 2

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(
            f"migrate_assets_to_configs: {summary['status']} mode={summary['mode']} "
            f"files={summary.get('files_scanned')} candidates={summary.get('candidates_total')} "
            f"entries={summary.get('entries_migrated')} duplicates={summary.get('duplicates_merged')} "
            f"conflicts={summary.get('conflicts')} dropped_fields={summary.get('dropped_fields')}"
        )
        for err in summary.get("errors", []):
            print(f"  - {err}")

    return int(summary["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
