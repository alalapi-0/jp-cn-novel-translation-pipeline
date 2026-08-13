#!/usr/bin/env python3
"""Validate agent round report JSON against schemas/agent_round_report.schema.json.

Read-only; does not modify reports. No .env access.
Exit: 0=valid, 1=schema validation failed, 2=IO/JSON parse error.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_REPORT = REPO_ROOT / "reports" / "current-cohort-report.json"
LEGACY_REPORT = REPO_ROOT / "reports" / "latest-agent-report.json"
DEFAULT_SCHEMA = REPO_ROOT / "schemas" / "agent_round_report.schema.json"

# Minimal fallback when jsonschema is not installed (dev should use requirements-dev.txt).
REQUIRED_TOP_LEVEL = (
    "round_id",
    "timestamp",
    "agent",
    "agent_surface",
    "mode",
    "goal",
    "tool_probe_status",
    "gate_status",
    "severity_summary",
)
POLICY_VERSION = "git_safe_cohort_delivery_v1"
POLICY_EFFECTIVE_AT = dt.datetime(2026, 8, 13, tzinfo=dt.timezone.utc)


def load_json(path: Path) -> dict[str, Any]:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"invalid JSON: {path}: {exc}") from exc


def validate_required_fields(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    for key in REQUIRED_TOP_LEVEL:
        if key not in report:
            errors.append(f"missing required field: {key}")
    summary = report.get("severity_summary")
    if isinstance(summary, dict):
        for sev in ("p0", "p1", "p2", "p3"):
            if sev not in summary:
                errors.append(f"severity_summary missing {sev}")
    elif "severity_summary" in report:
        errors.append("severity_summary must be an object")
    return errors


def validate_with_jsonschema(report: dict[str, Any], schema: dict[str, Any]) -> list[str]:
    try:
        import jsonschema
        from jsonschema.exceptions import ValidationError
    except ImportError:
        return validate_required_fields(report) + validate_git_delivery_semantics(report)

    validator = jsonschema.Draft7Validator(schema)
    errors: list[str] = []
    for err in sorted(validator.iter_errors(report), key=lambda e: list(e.path)):
        path = ".".join(str(p) for p in err.path) or "(root)"
        errors.append(f"{path}: {err.message}")
    errors.extend(validate_git_delivery_semantics(report))
    return errors


def _is_exact_legacy_report_path(path: Path) -> bool:
    """Bind legacy-schema compatibility to the one protected historical file."""
    return Path(os.path.abspath(path)) == LEGACY_REPORT


def validate_legacy_report(report: dict[str, Any]) -> list[str]:
    timestamp = _timestamp(report.get("timestamp"))
    if (
        report.get("policy_version") == POLICY_VERSION
        or timestamp is None
        or timestamp >= POLICY_EFFECTIVE_AT
    ):
        return ["protected legacy report does not satisfy the pre-policy boundary"]
    return validate_required_fields(report)


def _timestamp(value: Any) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


def validate_git_delivery_semantics(report: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    version = report.get("policy_version")
    if version != POLICY_VERSION:
        errors.append("current reports must declare git_safe_cohort_delivery_v1")
        return errors
    status = report.get("cohort_status")
    delivery = report.get("git_delivery")
    if not isinstance(delivery, dict):
        errors.append("git_delivery must be an object")
        return errors
    if delivery.get("status") != status:
        errors.append("git_delivery.status must match cohort_status")
    if delivery.get("remote_sha_verified") is not False:
        errors.append("tracked report cannot self-attest the post-push remote SHA")
    if report.get("overall_status") == "completed" or status == "complete":
        errors.append("tracked report cannot mark the cohort complete")
    next_round = report.get("next_recommended_round", "")
    if status in {"work_in_progress", "candidate_ready_for_delivery"} and next_round:
        errors.append("next cohort is blocked until fresh remote SHA verification")
    if status == "candidate_ready_for_delivery" and not report.get("changed_files"):
        errors.append("candidate_ready_for_delivery requires an exact changed_files list")
    if status == "not_applicable" and report.get("changed_files"):
        errors.append("not_applicable requires changed_files to be empty")
    return errors


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def validate_report(
    report_path: Path = DEFAULT_REPORT,
    schema_path: Path = DEFAULT_SCHEMA,
) -> tuple[bool, list[str]]:
    if not report_path.is_file():
        return False, [f"report not found: {_display_path(report_path)}"]
    if not schema_path.is_file():
        return False, [f"schema not found: {_display_path(schema_path)}"]
    try:
        report = load_json(report_path)
        schema = load_json(schema_path)
    except ValueError as exc:
        return False, [str(exc)]
    if _is_exact_legacy_report_path(report_path):
        errors = validate_legacy_report(report)
    else:
        errors = validate_with_jsonschema(report, schema)
    return len(errors) == 0, errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate latest agent round report JSON")
    parser.add_argument(
        "--report",
        type=Path,
        default=DEFAULT_REPORT,
        help=f"Report JSON (default: {DEFAULT_REPORT.relative_to(REPO_ROOT)})",
    )
    parser.add_argument(
        "--schema",
        type=Path,
        default=DEFAULT_SCHEMA,
        help=f"JSON Schema (default: {DEFAULT_SCHEMA.relative_to(REPO_ROOT)})",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable result")
    args = parser.parse_args(argv)

    report_path = args.report if args.report.is_absolute() else REPO_ROOT / args.report
    schema_path = args.schema if args.schema.is_absolute() else REPO_ROOT / args.schema

    ok, errors = validate_report(report_path, schema_path)

    if not report_path.is_file() or not schema_path.is_file():
        code = 2
    elif errors and errors[0].startswith(("invalid JSON", "report not found", "schema not found")):
        code = 2
    elif ok:
        code = 0
    else:
        code = 1

    payload = {
        "valid": ok,
        "exit_code": code,
        "report": _display_path(report_path),
        "schema": _display_path(schema_path),
        "errors": errors,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    elif ok:
        print(f"validate_agent_report: PASS -> {_display_path(report_path)}")
    else:
        print(f"validate_agent_report: FAIL (exit {code}) -> {_display_path(report_path)}")
        for err in errors:
            print(f"  - {err}")

    return code


if __name__ == "__main__":
    sys.exit(main())
