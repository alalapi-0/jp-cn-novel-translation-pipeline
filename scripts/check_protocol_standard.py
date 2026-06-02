#!/usr/bin/env python3
"""Check repo protocol alignment between governance YAML and project.yaml.

Deterministic only — no LLM, no .env reads, no network.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Iterable, Sequence


class Severity(str, Enum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass
class CheckResult:
    check_id: str
    severity: Severity
    message: str

    def to_dict(self) -> dict:
        return {"id": self.check_id, "severity": self.severity.value, "message": self.message}


REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = REPO_ROOT / "docs" / "reports" / "protocol_compliance_report.md"

PROTOCOL_PATH = REPO_ROOT / "governance" / "repo_protocol_standard.yaml"
PROJECT_PATH = REPO_ROOT / "project.yaml"

REQUIRED_ROOT = ("README.md", "AGENTS.md", "project.yaml")
REQUIRED_GOVERNANCE = (
    "governance/agent_policy.yaml",
    "governance/round_state.yaml",
    "governance/file_role_map.yaml",
    "governance/novel_pipeline_contract.yaml",
)
REQUIRED_DOC_DIRS = ("docs/reports", "docs/archive")


def _yaml_scalar(path: Path, key_path: Sequence[str]) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    if len(key_path) == 2 and key_path[0] == "protocol" and key_path[1] == "version":
        m = re.search(r'^protocol:\s*\n(?:[ \t].*\n)*?[ \t]+version:\s*["\']?([^"\'\n]+)', text, re.M)
        return m.group(1).strip() if m else None
    if key_path == ("protocol_standard", "version"):
        m = re.search(
            r'protocol_standard:\s*\n(?:[ \t].*\n)*?[ \t]+version:\s*["\']?([^"\'\n]+)',
            text,
            re.M,
        )
        return m.group(1).strip() if m else None
    return None


def check_required_files() -> list[CheckResult]:
    results: list[CheckResult] = []
    for name in REQUIRED_ROOT:
        path = REPO_ROOT / name
        if path.is_file():
            results.append(CheckResult("required_root_files", Severity.PASS, f"found {name}"))
        else:
            results.append(
                CheckResult("required_root_files", Severity.FAIL, f"missing root file {name}")
            )
    for rel in REQUIRED_GOVERNANCE:
        path = REPO_ROOT / rel
        if path.is_file():
            results.append(
                CheckResult("required_governance_files", Severity.PASS, f"found {rel}")
            )
        else:
            results.append(
                CheckResult(
                    "required_governance_files",
                    Severity.FAIL,
                    f"missing governance file {rel}",
                )
            )
    for rel in REQUIRED_DOC_DIRS:
        path = REPO_ROOT / rel
        if path.is_dir():
            results.append(
                CheckResult("required_doc_dirs", Severity.PASS, f"found directory {rel}")
            )
        else:
            results.append(
                CheckResult(
                    "required_doc_dirs",
                    Severity.WARN,
                    f"missing directory {rel}",
                )
            )
    return results


def check_protocol_version_alignment() -> CheckResult:
    if not PROTOCOL_PATH.is_file():
        return CheckResult(
            "protocol_version_match",
            Severity.FAIL,
            "governance/repo_protocol_standard.yaml missing",
        )
    if not PROJECT_PATH.is_file():
        return CheckResult("protocol_version_match", Severity.FAIL, "project.yaml missing")
    proto_ver = _yaml_scalar(PROTOCOL_PATH, ("protocol", "version"))
    proj_ver = _yaml_scalar(PROJECT_PATH, ("protocol_standard", "version"))
    if not proto_ver or not proj_ver:
        return CheckResult(
            "protocol_version_match",
            Severity.FAIL,
            f"could not parse versions (protocol={proto_ver!r}, project={proj_ver!r})",
        )
    if proto_ver == proj_ver:
        return CheckResult(
            "protocol_version_match",
            Severity.PASS,
            f"versions aligned at {proto_ver}",
        )
    return CheckResult(
        "protocol_version_match",
        Severity.FAIL,
        f"version mismatch: protocol {proto_ver} vs project {proj_ver}",
    )


def check_project_protocol_path() -> CheckResult:
    text = PROJECT_PATH.read_text(encoding="utf-8", errors="replace") if PROJECT_PATH.is_file() else ""
    if "governance/repo_protocol_standard.yaml" in text:
        return CheckResult(
            "project_protocol_path",
            Severity.PASS,
            "project.yaml references governance/repo_protocol_standard.yaml",
        )
    return CheckResult(
        "project_protocol_path",
        Severity.WARN,
        "project.yaml may not reference standard protocol path",
    )


def check_agents_reading_order() -> CheckResult:
    agents = REPO_ROOT / "AGENTS.md"
    if not agents.is_file():
        return CheckResult("agents_reading_order", Severity.FAIL, "AGENTS.md missing")
    text = agents.read_text(encoding="utf-8", errors="replace")
    expected = (
        "governance/repo_protocol_standard.yaml",
        "project.yaml",
        "governance/round_state.yaml",
    )
    missing = [e for e in expected if e not in text]
    if not missing:
        return CheckResult(
            "agents_reading_order",
            Severity.PASS,
            "AGENTS.md lists core governance entry files",
        )
    return CheckResult(
        "agents_reading_order",
        Severity.WARN,
        f"AGENTS.md missing references: {', '.join(missing)}",
    )


def run_all_checks() -> list[CheckResult]:
    results: list[CheckResult] = []
    results.extend(check_required_files())
    results.append(check_protocol_version_alignment())
    results.append(check_project_protocol_path())
    results.append(check_agents_reading_order())
    return results


def aggregate_exit_code(results: Iterable[CheckResult]) -> int:
    severities = {r.severity for r in results}
    if Severity.FAIL in severities:
        return 2
    if Severity.WARN in severities:
        return 1
    return 0


def write_report(results: Sequence[CheckResult], exit_code: int) -> None:
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# Protocol Compliance Report",
        "",
        f"- Generated: {now}",
        f"- Exit code: {exit_code}",
        "",
        "## Checks",
        "",
        "| ID | Status | Message |",
        "|----|--------|---------|",
    ]
    for r in results:
        lines.append(f"| {r.check_id} | {r.severity.value} | {r.message} |")
    REPORT_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repo protocol compliance checker")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    results = run_all_checks()
    exit_code = aggregate_exit_code(results)
    write_report(results, exit_code)

    payload = {
        "exit_code": exit_code,
        "report_path": str(REPORT_PATH.relative_to(REPO_ROOT)),
        "checks": [r.to_dict() for r in results],
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        label = {0: "PASS", 1: "WARNING", 2: "BLOCKED"}[exit_code]
        print(f"protocol_check: {label} (exit {exit_code})")
        print(f"report: {REPORT_PATH.relative_to(REPO_ROOT)}")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
