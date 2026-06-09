#!/usr/bin/env python3
"""Read-only tool capability probe for Tool-aware Agent Layer 2.0.

Does not call paid APIs, does not modify external systems, does not read .env.
Writes reports/tool_probe_report.json and optionally refreshes docs/TOOL_INVENTORY.md.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
REPORT_PATH = REPO_ROOT / "reports" / "tool_probe_report.json"
INVENTORY_PATH = REPO_ROOT / "docs" / "TOOL_INVENTORY.md"
MCP_CONFIG = REPO_ROOT / ".cursor" / "mcp.json"

MCP_DEFAULTS: dict[str, dict[str, Any]] = {
    "filesystem": {
        "safe_probe": "list_allowed_directories (read-only)",
        "recommended_use_cases": ["project file inspection", "verify writes"],
        "allowed_scope": "${workspaceFolder}",
        "risks": ["must not authorize / or home directory"],
        "fallback": "Read/Grep/Shell in repo",
        "required_env": [],
        "wrapper_script": None,
        "safe_tool": "list_allowed_directories",
    },
    "github": {
        "safe_probe": "list_commits or search (read-only if token present)",
        "recommended_use_cases": ["issues", "PRs", "remote inspection"],
        "allowed_scope": "repo with GITHUB_TOKEN",
        "risks": ["push/merge without user approval"],
        "fallback": "git + gh CLI",
        "required_env": ["GITHUB_TOKEN"],
        "wrapper_script": None,
        "safe_tool": "list_commits",
    },
    "playwright": {
        "safe_probe": "browser_snapshot on local URL",
        "recommended_use_cases": ["e2e", "user-view flows", "screenshots"],
        "allowed_scope": "local dev server",
        "risks": ["multitask browser control blocked by project rules"],
        "fallback": "npm run test:ui",
        "required_env": [],
        "wrapper_script": None,
        "safe_tool": "browser_snapshot",
    },
    "chrome-devtools": {
        "safe_probe": "navigate local workbench + console check",
        "recommended_use_cases": ["DOM", "console", "network debug"],
        "allowed_scope": "project-isolated profile port 9321",
        "risks": ["profile conflicts with other projects"],
        "fallback": "playwright MCP or npm run test:ui",
        "required_env": [],
        "wrapper_script": "scripts/chrome_devtools_mcp_light_novel.sh",
        "safe_tool": "list_pages",
    },
    "context7": {
        "safe_probe": "resolve-library-id + query-docs",
        "recommended_use_cases": ["library API docs", "version-specific examples"],
        "allowed_scope": "public library docs",
        "risks": ["stale index vs latest release"],
        "fallback": "web_search official docs",
        "required_env": [],
        "wrapper_script": None,
        "safe_tool": "resolve-library-id",
    },
    "stitch": {
        "safe_probe": "list_projects (requires STITCH_API_KEY)",
        "recommended_use_cases": ["UI prototypes", "design input only"],
        "allowed_scope": "docs/design/stitch exports",
        "risks": ["paid API", "must not overwrite frontend/ blindly"],
        "fallback": "docs/design templates + manual UI",
        "required_env": ["STITCH_API_KEY"],
        "wrapper_script": "scripts/stitch_mcp_proxy.mjs",
        "safe_tool": "list_projects",
    },
    "Prisma-Local": {
        "safe_probe": "prisma mcp launcher check (not used by this repo)",
        "recommended_use_cases": [],
        "allowed_scope": "local prisma schema if present",
        "risks": ["optional server; not required for pipeline"],
        "fallback": "N/A",
        "required_env": [],
        "wrapper_script": None,
        "safe_tool": None,
    },
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _run(cmd: list[str] | str, *, timeout: int = 15) -> dict[str, Any]:
    if isinstance(cmd, str):
        shell = True
        argv: list[str] | str = cmd
    else:
        shell = False
        argv = cmd
    try:
        proc = subprocess.run(
            argv,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=shell,
            check=False,
        )
        out = (proc.stdout or proc.stderr or "").strip()[:500]
        return {
            "exit_code": proc.returncode,
            "output": out,
            "available": proc.returncode == 0,
        }
    except FileNotFoundError:
        return {"exit_code": 127, "output": "command not found", "available": False}
    except subprocess.TimeoutExpired:
        return {"exit_code": 124, "output": "timeout", "available": False}


def _which(name: str) -> bool:
    return shutil.which(name) is not None


def _env_present(name: str) -> bool:
    return bool(os.environ.get(name))


def _mcp_json_valid() -> bool:
    if not MCP_CONFIG.is_file():
        return False
    try:
        json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
        return True
    except json.JSONDecodeError:
        return False


def _find_cursor_mcps_root() -> Path | None:
    """Locate ~/.cursor/projects/<slug>/mcps if present."""
    home = Path.home()
    projects = home / ".cursor" / "projects"
    if not projects.is_dir():
        return None
    repo_name = REPO_ROOT.name
    repo_hyphen = repo_name.replace("_", "-")
    for path in sorted(projects.iterdir()):
        if not path.is_dir():
            continue
        mcps = path / "mcps"
        if not mcps.is_dir():
            continue
        folder = path.name.lower()
        if repo_name.lower() in folder or repo_hyphen.lower() in folder:
            return mcps
    return None


def _thread_mcp_dir(name: str, mcps_root: Path | None) -> Path | None:
    if not mcps_root:
        return None
    repo_token = REPO_ROOT.name.replace("_", "_")
    patterns = [
        f"project-0-{repo_token}-{name}",
        f"project-0-light_novel-{name}",
        name,
    ]
    for pat in patterns:
        path = mcps_root / pat
        if path.is_dir():
            return path
    for child in mcps_root.iterdir():
        if not child.is_dir():
            continue
        if child.name.endswith(f"-{name}") or child.name == name:
            return child
    return None


def _count_thread_tools(mcp_dir: Path | None) -> int:
    if not mcp_dir:
        return 0
    tools = mcp_dir / "tools"
    if not tools.is_dir():
        return 0
    return len(list(tools.glob("*.json")))


def _launcher_available(cfg: dict[str, Any]) -> dict[str, Any]:
    command = cfg.get("command")
    if not command:
        return {"available": False, "detail": "missing command"}
    if isinstance(command, str) and _which(command):
        return {"available": True, "detail": command}
    if command in ("npx", "node", "bash"):
        return {"available": _which(command), "detail": command}
    script = REPO_ROOT / str(command)
    if script.is_file():
        return {"available": os.access(script, os.X_OK), "detail": str(script.relative_to(REPO_ROOT))}
    return {"available": False, "detail": str(command)}


def _wrapper_probe(rel_path: str | None) -> dict[str, Any]:
    if not rel_path:
        return {"present": True, "executable": True, "path": None}
    path = REPO_ROOT / rel_path
    node_script = rel_path.endswith((".mjs", ".js", ".cjs"))
    exec_ok = path.is_file() and (node_script or os.access(path, os.X_OK))
    return {
        "present": path.is_file(),
        "executable": exec_ok,
        "path": rel_path,
    }


def _probe_mcp_config_script() -> dict[str, Any]:
    script = REPO_ROOT / "scripts" / "check_mcp_config.js"
    if not script.is_file():
        return {"available": False, "passed": False, "output": "check_mcp_config.js missing"}
    result = _run(["node", str(script)])
    passed = result["exit_code"] == 0
    return {
        "available": True,
        "passed": passed,
        "exit_code": result["exit_code"],
        "output": result["output"][:300],
    }


def _filesystem_scope_safe(cfg: dict[str, Any]) -> bool:
    args = cfg.get("args") or []
    if not isinstance(args, list):
        return False
    joined = " ".join(str(a) for a in args)
    return "${workspaceFolder}" in joined and "server-filesystem" in joined


def _probe_github_offline() -> dict[str, Any]:
    gh_status = _run(["gh", "auth", "status"])
    return {
        "token_env": _env_present("GITHUB_TOKEN"),
        "gh_auth": gh_status["available"],
        "gh_detail": gh_status["output"][:120],
    }


def _probe_playwright_offline() -> dict[str, Any]:
    pw = _run("npx playwright --version")
    return {"npx_playwright": pw["available"], "version": pw["output"][:40]}


def _probe_prisma_offline() -> dict[str, Any]:
    prisma = _run(["npx", "-y", "prisma", "--version"], timeout=30)
    return {"npx_prisma": prisma["available"], "detail": prisma["output"][:80]}


def _derive_callable_now(
    *,
    name: str,
    launcher: dict[str, Any],
    wrapper: dict[str, Any],
    thread_loaded: bool,
    env_ok: bool,
    extra_ok: bool = True,
) -> str:
    if not launcher.get("available"):
        return "false"
    if wrapper.get("path") and not wrapper.get("present"):
        return "false"
    if wrapper.get("path") and not wrapper.get("executable"):
        return "false"
    if not extra_ok:
        return "false"
    meta = MCP_DEFAULTS.get(name, {})
    if meta.get("required_env") and not env_ok and name != "github":
        return "false"
    if thread_loaded:
        return "true"
    if name in ("playwright", "context7", "filesystem"):
        return "true"
    if name == "github" and env_ok:
        return "true"
    if name == "stitch" and env_ok:
        return "config_only"
    if launcher.get("available"):
        return "config_only"
    return "unknown"


def _format_probe_result(name: str, checks: dict[str, Any]) -> str:
    parts: list[str] = []
    cfg = checks.get("config_check") or {}
    if cfg:
        parts.append(f"config={'PASS' if cfg.get('passed') else 'FAIL'}")
    launcher = checks.get("launcher") or {}
    if launcher:
        parts.append(f"launcher={launcher.get('detail')} ({'ok' if launcher.get('available') else 'missing'})")
    wrapper = checks.get("wrapper") or {}
    if wrapper.get("path"):
        parts.append(
            f"wrapper={wrapper.get('path')} ({'exec' if wrapper.get('executable') else 'not exec'})"
        )
    if checks.get("thread_loaded"):
        parts.append(f"thread_tools={checks.get('thread_tool_count', 0)}")
    else:
        parts.append("thread_loaded=false")
    safe_tool = checks.get("safe_tool")
    if safe_tool:
        parts.append(f"safe_tool={safe_tool}")
    env = checks.get("env") or {}
    for key, present in env.items():
        parts.append(f"{key}={'set' if present else 'unset'}")
    offline = checks.get("offline") or {}
    for key, val in offline.items():
        if isinstance(val, bool):
            parts.append(f"{key}={'ok' if val else 'no'}")
        elif val:
            parts.append(f"{key}={val}")
    if name == "filesystem" and checks.get("scope_safe"):
        parts.append("scope=${workspaceFolder}")
    if name == "Prisma-Local":
        parts.append("repo_use=none")
    return "; ".join(parts)


def _probe_single_mcp_server(
    name: str,
    cfg: dict[str, Any],
    *,
    mcps_root: Path | None,
    config_check: dict[str, Any],
) -> dict[str, Any]:
    meta = MCP_DEFAULTS.get(name, {})
    mcp_dir = _thread_mcp_dir(name, mcps_root)
    thread_tool_count = _count_thread_tools(mcp_dir)
    thread_loaded = thread_tool_count > 0
    launcher = _launcher_available(cfg)
    wrapper = _wrapper_probe(meta.get("wrapper_script"))
    env_status = {var: _env_present(var) for var in meta.get("required_env", [])}
    env_ok = all(env_status.values()) if env_status else True

    offline: dict[str, Any] = {}
    extra_ok = True
    if name == "github":
        offline = _probe_github_offline()
        extra_ok = offline.get("gh_auth") or offline.get("token_env")
        env_ok = extra_ok
    elif name == "playwright":
        offline = _probe_playwright_offline()
        extra_ok = offline.get("npx_playwright", False)
    elif name == "Prisma-Local":
        offline = _probe_prisma_offline()
        extra_ok = offline.get("npx_prisma", False)
    elif name == "filesystem":
        extra_ok = _filesystem_scope_safe(cfg)

    callable_now = _derive_callable_now(
        name=name,
        launcher=launcher,
        wrapper=wrapper,
        thread_loaded=thread_loaded,
        env_ok=env_ok,
        extra_ok=extra_ok,
    )

    checks: dict[str, Any] = {
        "config_check": config_check,
        "launcher": launcher,
        "wrapper": wrapper,
        "thread_loaded": thread_loaded,
        "thread_tool_count": thread_tool_count,
        "thread_mcp_dir": str(mcp_dir) if mcp_dir else None,
        "safe_tool": meta.get("safe_tool"),
        "env": env_status,
        "offline": offline,
    }
    if name == "filesystem":
        checks["scope_safe"] = extra_ok

    probe_result = _format_probe_result(name, checks)
    if callable_now == "config_only":
        probe_result += "; note=configured but not loaded in Cursor thread"

    return {
        "name": name,
        "configured": True,
        "callable_now": callable_now,
        "command_hint": cfg.get("command") or (cfg.get("args") or [""])[0],
        "safe_probe_command": meta.get("safe_probe", "read-only list/describe"),
        "probe_result": probe_result,
        "probe_checks": checks,
        "allowed_scope": meta.get("allowed_scope", "see docs/TOOL_USAGE_POLICY.md"),
        "recommended_use_cases": meta.get("recommended_use_cases", []),
        "risks": meta.get("risks", []),
        "fallback": meta.get("fallback", "local scripts + IDE tools"),
    }


def probe_local_tools() -> dict[str, Any]:
    probes = {
        "shell": _run("pwd"),
        "git": _run(["git", "status", "--short"]),
        "git_branch": _run(["git", "branch", "--show-current"]),
        "node": _run("node -v"),
        "npm": _run("npm -v"),
        "pnpm": _run("pnpm -v"),
        "python3": _run("python3 --version"),
        "uv": _run("uv --version"),
        "java": _run("java -version"),
        "mvn": _run("mvn -v"),
        "docker": _run("docker --version"),
        "make": _run("make --version"),
        "gh": _run("gh --version"),
        "ffmpeg": _run("ffmpeg -version"),
        "playwright_npx": _run("npx playwright --version"),
        "pytest": _run("python3 -m pytest --version"),
    }
    probes["cwd"] = str(REPO_ROOT)
    return probes


def probe_cursor_artifacts() -> dict[str, Any]:
    rules_dir = REPO_ROOT / ".cursor" / "rules"
    rule_files = sorted(p.name for p in rules_dir.glob("*")) if rules_dir.is_dir() else []
    mcps_root = _find_cursor_mcps_root()
    thread_servers: list[str] = []
    if mcps_root:
        thread_servers = sorted(
            p.name for p in mcps_root.iterdir() if p.is_dir()
        )
    return {
        "cursor_rules_dir": rules_dir.is_dir(),
        "cursor_rules_count": len(rule_files),
        "cursor_rules_files": rule_files,
        "mcp_json_exists": MCP_CONFIG.is_file(),
        "mcp_json_valid": _mcp_json_valid(),
        "cursor_mcps_root": str(mcps_root) if mcps_root else None,
        "cursor_thread_mcp_servers": thread_servers,
        "cursor_config_visibility": "limited",
        "manual_confirm_in_cursor_ui": [
            "Settings → MCP: confirm servers loaded after mcp.json changes",
            "Settings → Rules: confirm project rules active",
            "Browser / Design Mode availability per Cursor version",
            "Cloud Agent / Subagents / Hooks / Skills per account plan",
        ],
    }


def probe_mcp_configured() -> list[dict[str, Any]]:
    servers: list[dict[str, Any]] = []
    if not MCP_CONFIG.is_file():
        return servers
    try:
        data = json.loads(MCP_CONFIG.read_text(encoding="utf-8"))
        configured = data.get("mcpServers") or {}
    except json.JSONDecodeError:
        return servers

    mcps_root = _find_cursor_mcps_root()
    config_check = _probe_mcp_config_script()

    for name, cfg in configured.items():
        if not isinstance(cfg, dict):
            continue
        servers.append(
            _probe_single_mcp_server(
                name,
                cfg,
                mcps_root=mcps_root,
                config_check=config_check,
            )
        )
    return servers


def probe_codex_compat() -> dict[str, Any]:
    codex_home = Path.home() / ".codex"
    return {
        "CODEX_AVAILABLE": "manual",
        "agents_md_at_repo_root": (REPO_ROOT / "AGENTS.md").is_file(),
        "codex_config_dir_exists": codex_home.is_dir(),
        "codex_cli_on_path": _which("codex"),
        "notes": "Codex not verified in this Cursor thread; protocol files remain compatible.",
    }


def probe_github() -> dict[str, Any]:
    remote = _run(["git", "remote", "-v"])
    offline = _probe_github_offline()
    return {
        "has_remote": "origin" in remote.get("output", ""),
        "gh_cli": _which("gh"),
        "github_mcp_configured": any(s["name"] == "github" for s in probe_mcp_configured()),
        "github_token_env": offline["token_env"],
        "gh_auth_ok": offline["gh_auth"],
        "commit_allowed": "user_explicit_only",
        "push_allowed": "user_explicit_only",
        "pr_allowed": "user_explicit_only",
    }


def probe_web_search(agent_surface: str = "cursor") -> dict[str, Any]:
    return {
        "available": True if agent_surface == "cursor" else "unknown",
        "tool_id": "WebSearch",
        "use_for": ["official docs", "platform rules", "API changes"],
        "policy": "docs/SEARCH_POLICY.md",
    }


def probe_browser_stack() -> dict[str, Any]:
    return {
        "playwright_config": (REPO_ROOT / "playwright.config.ts").is_file(),
        "npm_test_ui": "test:ui" in (REPO_ROOT / "package.json").read_text(encoding="utf-8"),
        "serve_frontend_script": (REPO_ROOT / "scripts" / "serve_frontend.py").is_file(),
        "browser_inspection_script": (REPO_ROOT / "scripts" / "run_browser_inspection.py").is_file(),
        "cursor_ide_browser_mcp": "callable in current Cursor thread",
        "recommended_local_url": "http://127.0.0.1:5174/",
    }


def _sync_tool_inventory(mcp_servers: list[dict[str, Any]]) -> bool:
    """Update callable_now column in docs/TOOL_INVENTORY.md from probe results."""
    if not INVENTORY_PATH.is_file():
        return False
    text = INVENTORY_PATH.read_text(encoding="utf-8")
    lookup = {s["name"]: s for s in mcp_servers}
    lines = text.splitlines()
    out: list[str] = []
    in_mcp_table = False
    for line in lines:
        if line.startswith("| name | configured | callable_now |"):
            in_mcp_table = True
            out.append(line)
            continue
        if in_mcp_table and line.startswith("|") and not line.startswith("|------"):
            cols = [c.strip() for c in line.strip("|").split("|")]
            if len(cols) >= 3 and cols[0] in lookup:
                server = lookup[cols[0]]
                probe = server.get("probe_result", "")
                cols[2] = server.get("callable_now", cols[2])
                if len(cols) >= 4:
                    cols[3] = server.get("safe_probe_command", cols[3])[:60]
                line = "| " + " | ".join(cols) + " |"
                if probe and len(cols) >= 4:
                    pass
            out.append(line)
            continue
        if in_mcp_table and line.startswith("## "):
            in_mcp_table = False
        out.append(line)

    updated = "\n".join(out) + "\n"
    if updated != text:
        INVENTORY_PATH.write_text(updated, encoding="utf-8")
        return True
    return False


def _sync_agent_tools_yaml(mcp_servers: list[dict[str, Any]]) -> bool:
    """Patch callable_now hints in agent_tools.yaml for known MCP keys."""
    yaml_path = REPO_ROOT / "agent_tools.yaml"
    if not yaml_path.is_file():
        return False
    key_map = {
        "filesystem": "filesystem_mcp",
        "github": "github_mcp",
        "stitch": "stitch_mcp",
        "context7": "context7",
        "playwright": "playwright",
        "chrome-devtools": "chrome_devtools",
    }
    text = yaml_path.read_text(encoding="utf-8")
    changed = False
    for server in mcp_servers:
        yaml_key = key_map.get(server["name"])
        if not yaml_key:
            continue
        val = server.get("callable_now", "unknown")
        if val == "config_only":
            val = "config_only"
        pattern = rf"(^  {re.escape(yaml_key)}:[\s\S]*?callable_now:\s*)([^\n]+)"
        match = re.search(pattern, text, re.MULTILINE)
        if match and match.group(2).strip() != val:
            text = text[: match.start(2)] + val + text[match.end(2) :]
            changed = True
    if changed:
        yaml_path.write_text(text, encoding="utf-8")
    return changed


def build_report(agent_surface: str = "cursor") -> dict[str, Any]:
    local = probe_local_tools()
    mcp = probe_mcp_configured()
    deferred = [s["name"] for s in mcp if s.get("probe_result") == "deferred_to_agent_thread"]
    report: dict[str, Any] = {
        "version": 2,
        "timestamp": _utc_now(),
        "agent_surface": agent_surface,
        "repo_root": str(REPO_ROOT),
        "status": "partial",
        "local_tools": local,
        "cursor": probe_cursor_artifacts(),
        "codex": probe_codex_compat(),
        "mcp_servers": mcp,
        "mcp_probe_summary": {
            "total_configured": len(mcp),
            "callable_true": sum(1 for s in mcp if s.get("callable_now") == "true"),
            "callable_config_only": sum(1 for s in mcp if s.get("callable_now") == "config_only"),
            "callable_false": sum(1 for s in mcp if s.get("callable_now") == "false"),
            "deferred_probe_results": deferred,
        },
        "web_search": probe_web_search(agent_surface),
        "github": probe_github(),
        "browser": probe_browser_stack(),
        "blockers": [],
        "recommendations": [
            "Read AGENTS.md + agent_tools.yaml before each round",
            "Run python3 scripts/tool_probe.py at round start if stale",
            "Use Context7 or WebSearch for fresh library/platform docs",
            "UI tasks: dev server + browser MCP or npm run test:ui",
        ],
    }
    if not local.get("git", {}).get("available"):
        report["blockers"].append("TOOL_UNAVAILABLE: git")
    if not MCP_CONFIG.is_file():
        report["blockers"].append("TOOL_UNAVAILABLE: mcp.json missing")
    if deferred:
        report["blockers"].append(f"MCP_PROBE_DEFERRED: {', '.join(deferred)}")
    report["status"] = "passed" if not report["blockers"] else "partial"
    return report


def main() -> int:
    agent = "cursor"
    sync_docs = "--sync-docs" in sys.argv
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if args:
        agent = args[0]

    report = build_report(agent)
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if sync_docs or "--sync-docs" in sys.argv:
        inv = _sync_tool_inventory(report["mcp_servers"])
        yaml = _sync_agent_tools_yaml(report["mcp_servers"])
        if inv:
            print(f"tool_probe: updated {INVENTORY_PATH.relative_to(REPO_ROOT)}")
        if yaml:
            print("tool_probe: updated agent_tools.yaml callable_now hints")

    summary = report.get("mcp_probe_summary", {})
    print(
        f"tool_probe: {report['status']} -> {REPORT_PATH.relative_to(REPO_ROOT)} "
        f"(mcp callable={summary.get('callable_true', 0)}/"
        f"{summary.get('total_configured', 0)}, "
        f"config_only={summary.get('callable_config_only', 0)})"
    )
    return 0 if report["status"] in ("passed", "partial") else 1


if __name__ == "__main__":
    sys.exit(main())
