#!/usr/bin/env python3
"""Scan repository inventory and tooling environment readiness.

Deterministic only — no LLM, no .env reads, no network, no file content hashing.
Generates governance/repo_inventory.generated.json and docs/reports/tooling_environment_audit.md.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence

REPO_ROOT = Path(__file__).resolve().parent.parent
INVENTORY_PATH = REPO_ROOT / "governance" / "repo_inventory.generated.json"
EXAMPLE_PATH = REPO_ROOT / "governance" / "repo_inventory.example.json"
AUDIT_REPORT_PATH = REPO_ROOT / "docs" / "reports" / "tooling_environment_audit.md"

SCAN_DIRS = ("scripts", "tests", "prompts", "frontend", "governance")
STRUCTURE_DIRS = (
    "directions/jp_to_cn",
    "directions/cn_to_jp",
    "shared",
)
TOOLING_PROMPT_MIN = 6
TOOLING_PROMPT_PATTERN = re.compile(r"round_(4[1-9]|50)_", re.I)


@dataclass
class ToolProbe:
    name: str
    present: bool
    version: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {"present": self.present}
        if self.version:
            out["version"] = self.version
        if self.note:
            out["note"] = self.note
        return out


def _run(cmd: Sequence[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(cmd),
        cwd=cwd or REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


def _first_line(text: str) -> str:
    return text.strip().splitlines()[0].strip() if text.strip() else ""


def probe_command(name: str, cmd: Sequence[str], version_flag: str = "--version") -> ToolProbe:
    exe = shutil.which(cmd[0])
    if not exe:
        return ToolProbe(name, present=False, note=f"{cmd[0]} not on PATH")
    proc = _run([exe, *cmd[1:]] if len(cmd) > 1 else [exe, version_flag])
    version = _first_line(proc.stdout or proc.stderr)
    return ToolProbe(name, present=True, version=version or None)


def probe_pytest() -> ToolProbe:
    proc = _run([sys.executable, "-m", "pytest", "--version"])
    if proc.returncode == 0:
        return ToolProbe("pytest", present=True, version=_first_line(proc.stdout))
    return ToolProbe("pytest", present=False, note="python -m pytest unavailable")


def probe_playwright() -> ToolProbe:
    for cmd in (["npx", "playwright", "--version"], ["playwright", "--version"]):
        exe = shutil.which(cmd[0])
        if not exe:
            continue
        proc = _run([exe, *cmd[1:]])
        if proc.returncode == 0:
            return ToolProbe("playwright", present=True, version=_first_line(proc.stdout))
    return ToolProbe("playwright", present=False, note="Playwright CLI not detected")


def probe_mcp_config() -> ToolProbe:
    path = REPO_ROOT / ".cursor" / "mcp.json"
    if path.is_file():
        return ToolProbe("mcp_config", present=True, version=str(path.relative_to(REPO_ROOT)))
    return ToolProbe("mcp_config", present=False, note=".cursor/mcp.json missing")


def probe_env_tracked() -> ToolProbe:
    proc = _run(["git", "ls-files", "--error-unmatch", ".env"])
    if proc.returncode == 0:
        return ToolProbe("env_tracked", present=True, note="HIGH: .env is tracked by git")
    return ToolProbe("env_tracked", present=False, note=".env not tracked")


def scan_directory(rel: str) -> dict[str, Any]:
    root = REPO_ROOT / rel
    if not root.is_dir():
        return {"exists": False, "count": 0, "files": [], "total_bytes": 0}
    files: list[dict[str, Any]] = []
    total = 0
    for path in sorted(root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.startswith("."):
            continue
        size = path.stat().st_size
        total += size
        files.append(
            {
                "name": path.name,
                "relative": str(path.relative_to(REPO_ROOT)),
                "bytes": size,
            }
        )
    return {
        "exists": True,
        "count": len(files),
        "files": files,
        "total_bytes": total,
    }


def count_tooling_prompts(prompt_inventory: dict[str, Any]) -> int:
    count = 0
    for item in prompt_inventory.get("files", []):
        name = item.get("name", "")
        if TOOLING_PROMPT_PATTERN.search(name):
            count += 1
    return count


def build_gaps_by_round(env: dict[str, ToolProbe], inventory: dict[str, Any]) -> dict[str, list[str]]:
    gaps: dict[str, list[str]] = {}
    if not env["playwright"].present:
        gaps["round_44"] = ["Install Playwright CLI (Node or Python route)"]
    if not env["pytest"].present:
        gaps["round_41"] = ["Install pytest for unit tests"]
    frontend = inventory.get("frontend", {})
    if not frontend.get("exists") or frontend.get("count", 0) < 3:
        gaps["round_44"] = gaps.get("round_44", []) + ["frontend/ directory incomplete"]
    if not env["node"].present:
        gaps["round_44"] = gaps.get("round_44", []) + ["Node.js recommended for Playwright smoke tests"]
    if not env["mcp_config"].present:
        gaps["round_45"] = ["Configure .cursor/mcp.json for browser MCP"]
    return gaps


def build_payload() -> dict[str, Any]:
    inventory = {name: scan_directory(name) for name in SCAN_DIRS}
    tooling_prompt_count = count_tooling_prompts(inventory["prompts"])
    env = {
        "python": probe_command("python", [sys.executable, "--version"]),
        "node": probe_command("node", ["node", "--version"]),
        "npm": probe_command("npm", ["npm", "--version"]),
        "git": probe_command("git", ["git", "--version"]),
        "gh": probe_command("gh", ["gh", "--version"]),
        "pytest": probe_pytest(),
        "playwright": probe_playwright(),
        "mcp_config": probe_mcp_config(),
        "env_tracked": probe_env_tracked(),
    }
    structure = {
        rel.replace("/", "_"): (REPO_ROOT / rel).exists() for rel in STRUCTURE_DIRS
    }
    gaps = build_gaps_by_round(env, inventory)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return {
        "schema_version": "1.0",
        "generated_at": now,
        "inventory": inventory,
        "counts_summary": {
            "scripts": inventory["scripts"]["count"],
            "tests": inventory["tests"]["count"],
            "prompts": inventory["prompts"]["count"],
            "tooling_prompts": tooling_prompt_count,
            "frontend_files": inventory["frontend"]["count"],
            "governance_files": inventory["governance"]["count"],
        },
        "environment": {k: v.to_dict() for k, v in env.items()},
        "structure": structure,
        "tooling_prompts_meets_minimum": tooling_prompt_count >= TOOLING_PROMPT_MIN,
        "gaps_by_round": gaps,
        "recommended_next_installs": sorted(
            {item for items in gaps.values() for item in items}
        ),
    }


def write_audit_markdown(payload: dict[str, Any]) -> None:
    AUDIT_REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    env = payload["environment"]
    gaps = payload["gaps_by_round"]
    lines = [
        "# Tooling Environment Audit",
        "",
        f"- Generated: {payload['generated_at']}",
        f"- Inventory: {INVENTORY_PATH.relative_to(REPO_ROOT)}",
        "",
        "## Tool matrix",
        "",
        "| Tool | Present | Version / note |",
        "|------|---------|--------------|",
    ]
    for name, info in env.items():
        present = "yes" if info["present"] else "no"
        detail = info.get("version") or info.get("note") or ""
        lines.append(f"| {name} | {present} | {detail} |")
    lines.extend(
        [
            "",
            "## Counts summary",
            "",
            f"- scripts: {payload['counts_summary']['scripts']}",
            f"- tests: {payload['counts_summary']['tests']}",
            f"- prompts: {payload['counts_summary']['prompts']} "
            f"(tooling: {payload['counts_summary']['tooling_prompts']}, "
            f"min {TOOLING_PROMPT_MIN}: "
            f"{'ok' if payload['tooling_prompts_meets_minimum'] else 'below'})",
            f"- frontend files: {payload['counts_summary']['frontend_files']}",
            "",
            "## Structure",
            "",
        ]
    )
    for key, ok in payload["structure"].items():
        lines.append(f"- {key}: {'present' if ok else 'missing'}")
    lines.extend(["", "## Gaps by round", ""])
    if gaps:
        for rnd, items in sorted(gaps.items()):
            lines.append(f"### {rnd}")
            for item in items:
                lines.append(f"- {item}")
    else:
        lines.append("- No tooling gaps detected for Round 44–45 prerequisites.")
    if env.get("env_tracked", {}).get("present"):
        lines.extend(["", "## HIGH", "", "- `.env` is tracked by git — align with agent_gate BLOCKED policy."])
    lines.extend(
        [
            "",
            "## Validation commands",
            "",
            "```bash",
            "python3 scripts/agent_gate.py",
            "python3 scripts/check_protocol_standard.py",
            "python3 scripts/scan_repo_inventory.py",
            "npm run check:tooling",
            "```",
            "",
        ]
    )
    AUDIT_REPORT_PATH.write_text("\n".join(lines), encoding="utf-8")


def write_example_summary(payload: dict[str, Any]) -> None:
    summary = {
        "schema_version": payload["schema_version"],
        "generated_at": payload["generated_at"],
        "counts_summary": payload["counts_summary"],
        "environment_present": {k: v["present"] for k, v in payload["environment"].items()},
        "structure": payload["structure"],
        "tooling_prompts_meets_minimum": payload["tooling_prompts_meets_minimum"],
        "gaps_by_round_keys": sorted(payload["gaps_by_round"].keys()),
    }
    EXAMPLE_PATH.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Repository inventory and tooling audit")
    parser.add_argument("--json", action="store_true", help="Print inventory JSON to stdout")
    parser.add_argument("--no-report", action="store_true", help="Skip markdown audit report")
    args = parser.parse_args(argv)

    payload = build_payload()
    INVENTORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    INVENTORY_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    write_example_summary(payload)
    if not args.no_report:
        write_audit_markdown(payload)

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        cs = payload["counts_summary"]
        print(f"inventory_scan: PASS")
        print(f"inventory: {_display_path(INVENTORY_PATH)}")
        print(f"example: {_display_path(EXAMPLE_PATH)}")
        if not args.no_report:
            print(f"audit: {_display_path(AUDIT_REPORT_PATH)}")
        print(
            f"counts: scripts={cs['scripts']} tests={cs['tests']} "
            f"prompts={cs['prompts']} frontend={cs['frontend_files']}"
        )
        if payload["gaps_by_round"]:
            print(f"gaps: {', '.join(sorted(payload['gaps_by_round']))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
