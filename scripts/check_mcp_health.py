#!/usr/bin/env python3
"""Local MCP health checks for light_novel (no direct MCP tool calls)."""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_JSON = REPO_ROOT / ".cursor" / "mcp.json"
RUNBOOK = REPO_ROOT / "docs" / "runbooks" / "mcp_browser_tools_runbook.md"
ISOLATION_DOC = REPO_ROOT / "docs" / "mcp_isolation_strategy_light_novel.md"
EXAMPLE_CONFIG = REPO_ROOT / "docs" / "examples" / "mcp.light_novel.example.json"
DEFAULT_PROFILE = Path.home() / ".cache" / "chrome-devtools-mcp" / "chrome-profile"
PROJECT_PROFILE = Path.home() / ".cache" / "chrome-devtools-mcp" / "light_novel-chrome-profile"
REPORT_MD = REPO_ROOT / "docs" / "mcp_health_report.md"
REPORT_JSON = REPO_ROOT / "workspace" / "tooling" / "mcp_health_report.json"
WRAPPER = REPO_ROOT / "scripts" / "chrome_devtools_mcp_light_novel.sh"
PLAYWRIGHT_CONFIG = REPO_ROOT / "playwright.config.ts"
AGENT_GATE = REPO_ROOT / "scripts" / "agent_gate.py"
PACKAGE_JSON = REPO_ROOT / "package.json"


def _run(cmd: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
        out = (proc.stdout or "") + (proc.stderr or "")
        return proc.returncode, out.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        return 1, str(exc)


def _profile_locked(profile: Path) -> tuple[bool, str]:
    if not profile.is_dir():
        return False, "profile directory does not exist"
    code, out = _run(["lsof", f"+D:{profile}"])
    if code != 0 or not out:
        code, out = _run(["ps", "aux"])
        if code == 0 and str(profile) in out:
            return True, "process list references profile path"
        return False, "no open file handles detected"
    lines = [ln for ln in out.splitlines() if ln.strip() and "COMMAND" not in ln]
    if not lines:
        return False, "lsof returned no handles"
    summary = f"{len(lines)} open handle(s); first: {lines[0][:120]}"
    return True, summary


def _chrome_devtools_uses_isolated_profile() -> tuple[bool, str]:
    if not MCP_JSON.is_file():
        return False, "missing .cursor/mcp.json"
    try:
        data = json.loads(MCP_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, f"invalid mcp.json: {exc}"
    servers = data.get("mcpServers", {})
    cfg = servers.get("chrome-devtools", {})
    if not isinstance(cfg, dict):
        return False, "chrome-devtools server not configured"
    command = str(cfg.get("command", ""))
    args = cfg.get("args", [])
    blob = " ".join([command, *[str(a) for a in args]]) if isinstance(args, list) else command
    if "chrome_devtools_mcp_light_novel" in blob:
        return True, "uses project wrapper script"
    if "light_novel-chrome-profile" in blob or "--userDataDir" in blob:
        return True, "uses explicit userDataDir"
    if "chrome-profile" in blob and "light_novel" not in blob:
        return False, "still references shared default profile path"
    return False, "no project-isolated userDataDir detected"


def _playwright_available() -> tuple[bool, str]:
    if not PLAYWRIGHT_CONFIG.is_file():
        return False, "missing playwright.config.ts"
    if not PACKAGE_JSON.is_file():
        return False, "missing package.json"
    try:
        pkg = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return False, f"invalid package.json: {exc}"
    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
    if "@playwright/test" in deps or "playwright" in deps:
        return True, "playwright dependencies present"
    return False, "playwright not listed in package.json"


def _decision(checks: dict[str, object]) -> str:
    runbook_ok = bool(checks.get("runbook_exists"))
    playwright_ok = bool(checks.get("playwright_available"))
    isolated = bool(checks.get("chrome_devtools_isolated_config"))
    default_locked = bool(checks.get("default_profile_locked"))

    if not runbook_ok:
        return "BLOCKED_BY_MCP_CONFIG_UNCERTAINTY"
    if playwright_ok and (isolated or not default_locked):
        if default_locked and isolated:
            return "RUNBOOK_READY_WITH_PLAYWRIGHT_FALLBACK"
        return "RUNBOOK_READY"
    if playwright_ok:
        return "RUNBOOK_READY_WITH_PLAYWRIGHT_FALLBACK"
    return "BLOCKED_BY_MCP_CONFIG_UNCERTAINTY"


def _collect_checks() -> dict[str, object]:
    default_locked, default_detail = _profile_locked(DEFAULT_PROFILE)
    project_locked, project_detail = _profile_locked(PROJECT_PROFILE)
    isolated, isolated_detail = _chrome_devtools_uses_isolated_profile()
    playwright_ok, playwright_detail = _playwright_available()
    mcp_config_ok, mcp_out = _run(["python3", str(REPO_ROOT / "scripts" / "check_mcp_config.py")])

    docs = {
        "mcp_current_status_light_novel.md": (
            REPO_ROOT / "docs" / "mcp_current_status_light_novel.md"
        ).is_file(),
        "chrome_devtools_profile_conflict_audit.md": (
            REPO_ROOT / "docs" / "chrome_devtools_profile_conflict_audit.md"
        ).is_file(),
        "mcp_isolation_strategy_light_novel.md": ISOLATION_DOC.is_file(),
        "tooling_current_status.md": (REPO_ROOT / "docs" / "tooling_current_status.md").is_file(),
        "agent_tooling_strategy.md": (REPO_ROOT / "docs" / "agent_tooling_strategy.md").is_file(),
        "mcp_playwright_setup_plan.md": (
            REPO_ROOT / "docs" / "mcp_playwright_setup_plan.md"
        ).is_file(),
    }

    checks: dict[str, object] = {
        "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "repo": str(REPO_ROOT),
        "branch": _run(["git", "-C", str(REPO_ROOT), "branch", "--show-current"])[1],
        "runbook_exists": RUNBOOK.is_file(),
        "runbook_path": str(RUNBOOK.relative_to(REPO_ROOT)),
        "isolation_doc_exists": ISOLATION_DOC.is_file(),
        "example_config_exists": EXAMPLE_CONFIG.is_file(),
        "agent_gate_exists": AGENT_GATE.is_file(),
        "default_profile_exists": DEFAULT_PROFILE.is_dir(),
        "project_profile_exists": PROJECT_PROFILE.is_dir(),
        "wrapper_executable": WRAPPER.is_file() and bool(WRAPPER.stat().st_mode & 0o111),
        "default_profile_locked": default_locked,
        "default_profile_detail": default_detail,
        "project_profile_locked": project_locked,
        "project_profile_detail": project_detail,
        "chrome_devtools_isolated_config": isolated,
        "chrome_devtools_isolated_detail": isolated_detail,
        "playwright_available": playwright_ok,
        "playwright_detail": playwright_detail,
        "recommend_playwright_fallback": default_locked or not isolated,
        "cursor_mcp_json_exists": MCP_JSON.is_file(),
        "mcp_config_check_pass": mcp_config_ok == 0,
        "mcp_config_check_output": mcp_out.splitlines()[-1] if mcp_out else "",
        "mcp_docs_present": docs,
    }
    checks["decision"] = _decision(checks)
    return checks


def _render_markdown(checks: dict[str, object]) -> str:
    fallback = "yes" if checks["recommend_playwright_fallback"] else "no"
    isolated = "yes" if checks["chrome_devtools_isolated_config"] else "no"
    lines = [
        "# MCP Health Report (light_novel)",
        "",
        f"Generated: {checks['timestamp']}",
        "",
        "## Summary",
        "",
        f"- Repository: `{checks['repo']}`",
        f"- Git branch: `{checks['branch']}`",
        f"- Decision: **{checks['decision']}**",
        f"- Runbook: {'present' if checks['runbook_exists'] else 'missing'} (`{checks['runbook_path']}`)",
        f"- Playwright: {'available' if checks['playwright_available'] else 'missing'} ({checks['playwright_detail']})",
        f"- `.cursor/mcp.json`: {'present' if checks['cursor_mcp_json_exists'] else 'missing'}",
        f"- chrome-devtools isolated config: **{isolated}** ({checks['chrome_devtools_isolated_detail']})",
        f"- Recommend Playwright fallback: **{fallback}**",
        "",
        "## Chrome profile status",
        "",
        "| profile | exists | locked | detail |",
        "|---|---|---|---|",
        f"| default `{DEFAULT_PROFILE}` | "
        f"{'yes' if checks['default_profile_exists'] else 'no'} | "
        f"{'yes' if checks['default_profile_locked'] else 'no'} | "
        f"{checks['default_profile_detail']} |",
        f"| project `{PROJECT_PROFILE}` | "
        f"{'yes' if checks['project_profile_exists'] else 'no'} | "
        f"{'yes' if checks['project_profile_locked'] else 'no'} | "
        f"{checks['project_profile_detail']} |",
        "",
        "## Infrastructure checks",
        "",
        f"- `agent_gate.py`: {'present' if checks['agent_gate_exists'] else 'missing'}",
        f"- Example MCP config: {'present' if checks['example_config_exists'] else 'missing'}",
        f"- Project wrapper executable: {'yes' if checks['wrapper_executable'] else 'no'}",
        "",
        "## MCP config check",
        "",
        f"- `check_mcp_config.py`: {'PASS' if checks['mcp_config_check_pass'] else 'FAIL'}",
        f"- Last line: `{checks['mcp_config_check_output']}`",
        "",
        "## MCP documentation",
        "",
    ]
    docs = checks["mcp_docs_present"]
    assert isinstance(docs, dict)
    for name, present in docs.items():
        lines.append(f"- `{name}`: {'present' if present else 'missing'}")
    lines.extend(
        [
            "",
            "## Agent guidance",
            "",
            "1. Read `docs/runbooks/mcp_browser_tools_runbook.md` before browser/MCP tasks.",
            "2. Prefer **playwright** for UI verification when chrome-devtools reports profile lock.",
            "3. Profile isolation (`userDataDir`) takes priority over port changes.",
            "4. After editing `.cursor/mcp.json`, reload Cursor window before probing MCP tools.",
            "5. Do not kill other projects' Chrome/MCP processes to reclaim the shared profile.",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    checks = _collect_checks()
    report = _render_markdown(checks)
    REPORT_MD.write_text(report, encoding="utf-8")
    REPORT_JSON.parent.mkdir(parents=True, exist_ok=True)
    REPORT_JSON.write_text(json.dumps(checks, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    print(report)
    print(f"\nMarkdown report: {REPORT_MD.relative_to(REPO_ROOT)}")
    print(f"JSON report: {REPORT_JSON.relative_to(REPO_ROOT)}")
    print(f"Decision: {checks['decision']}")

    decision = checks["decision"]
    if decision == "BLOCKED_BY_MCP_CONFIG_UNCERTAINTY":
        return 1
    if decision == "RUNBOOK_READY_WITH_PLAYWRIGHT_FALLBACK":
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
