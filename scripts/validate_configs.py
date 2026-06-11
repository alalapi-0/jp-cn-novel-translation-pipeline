#!/usr/bin/env python3
"""Validate configs/*.yaml asset files against schemas/*.schema.json (FS-011).

Validates the five asset config files defined in spec §10:
glossary / character_profile / style_profile / world_bible / model_profiles.

Read-only; no .env access; no network.
Exit: 0=all valid, 1=schema validation failed, 2=IO/parse error.

Usage:
    python3 scripts/validate_configs.py                 # validate configs/ templates
    python3 scripts/validate_configs.py --json
    python3 scripts/validate_configs.py --configs-dir workspace/configs  # real data
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIGS_DIR = REPO_ROOT / "configs"
SCHEMAS_DIR = REPO_ROOT / "schemas"

# config filename -> schema filename
CONFIG_SCHEMA_MAP: dict[str, str] = {
    "glossary.yaml": "glossary.schema.json",
    "character_profile.yaml": "character_profile.schema.json",
    "style_profile.yaml": "style_profile.schema.json",
    "world_bible.yaml": "world_bible.schema.json",
    "model_profiles.yaml": "model_profiles.schema.json",
}


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def load_yaml(path: Path) -> Any:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - dev env always has pyyaml
        raise ValueError("pyyaml not installed (see requirements-dev.txt)") from exc
    try:
        return yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ValueError(f"invalid YAML: {_display_path(path)}: {exc}") from exc


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {_display_path(path)}: {exc}") from exc


def validate_data(data: Any, schema: dict[str, Any]) -> list[str]:
    """Validate parsed data against a Draft7 schema; returns error strings."""
    try:
        import jsonschema
    except ImportError:  # pragma: no cover - dev env always has jsonschema
        return ["jsonschema not installed (see requirements-dev.txt)"]
    validator = jsonschema.Draft7Validator(schema)
    errors: list[str] = []
    for err in sorted(validator.iter_errors(data), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in err.path) or "(root)"
        errors.append(f"{path}: {err.message}")
    return errors


def validate_config_file(config_path: Path, schema_path: Path) -> tuple[bool, list[str]]:
    """Validate one YAML config against its schema. Raises ValueError on parse error."""
    if not config_path.is_file():
        return False, [f"config not found: {_display_path(config_path)}"]
    if not schema_path.is_file():
        return False, [f"schema not found: {_display_path(schema_path)}"]
    data = load_yaml(config_path)
    schema = load_json(schema_path)
    errors = validate_data(data, schema)
    return len(errors) == 0, errors


def validate_all(
    configs_dir: Path = DEFAULT_CONFIGS_DIR,
    allow_missing: bool = False,
) -> dict[str, Any]:
    """Validate all five config files; returns machine-readable summary.

    allow_missing: skip absent config files instead of failing (used for
    workspace/configs/ real-data dirs that only carry migrated subsets).
    """
    results: list[dict[str, Any]] = []
    overall = "PASS"
    exit_code = 0
    for config_name, schema_name in CONFIG_SCHEMA_MAP.items():
        config_path = configs_dir / config_name
        schema_path = SCHEMAS_DIR / schema_name
        entry: dict[str, Any] = {
            "config": _display_path(config_path),
            "schema": _display_path(schema_path),
        }
        if allow_missing and not config_path.is_file():
            entry["valid"] = None
            entry["skipped"] = "missing"
            entry["errors"] = []
            results.append(entry)
            continue
        try:
            ok, errors = validate_config_file(config_path, schema_path)
            entry["valid"] = ok
            entry["errors"] = errors
            if not ok:
                overall = "FAIL"
                missing = any("not found" in e for e in errors)
                exit_code = max(exit_code, 2 if missing else 1)
        except ValueError as exc:
            entry["valid"] = False
            entry["errors"] = [str(exc)]
            overall = "FAIL"
            exit_code = 2
        results.append(entry)
    return {"status": overall, "exit_code": exit_code, "results": results}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate configs/*.yaml against schemas")
    parser.add_argument(
        "--configs-dir",
        type=Path,
        default=DEFAULT_CONFIGS_DIR,
        help="Directory containing the five YAML configs (default: configs/)",
    )
    parser.add_argument(
        "--allow-missing",
        action="store_true",
        help="Skip absent config files (for real-data dirs carrying migrated subsets)",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable result")
    args = parser.parse_args(argv)

    configs_dir = args.configs_dir if args.configs_dir.is_absolute() else REPO_ROOT / args.configs_dir
    summary = validate_all(configs_dir, allow_missing=args.allow_missing)

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"validate_configs: {summary['status']} -> {_display_path(configs_dir)}")
        for item in summary["results"]:
            mark = "SKIP" if item.get("skipped") else ("PASS" if item["valid"] else "FAIL")
            print(f"  [{mark}] {item['config']}")
            for err in item["errors"]:
                print(f"      - {err}")

    return int(summary["exit_code"])


if __name__ == "__main__":
    sys.exit(main())
