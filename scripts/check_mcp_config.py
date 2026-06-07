#!/usr/bin/env python3
"""Lightweight checker for project MCP configuration (.cursor/mcp.json)."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
MCP_PATH = REPO_ROOT / ".cursor" / "mcp.json"

# Paths that must not be the sole filesystem grant.
DANGEROUS_PATH_PATTERNS = (
    re.compile(r"^/$"),
    re.compile(r"^\\?$"),  # empty
    re.compile(r"^[A-Za-z]:[/\\]?$"),
    re.compile(r"^\$\{userHome\}$"),
    re.compile(r"^/Users/[^/]+$"),
    re.compile(r"^/home/[^/]+$"),
    re.compile(r"^C:\\Users\\[^\\]+$", re.IGNORECASE),
)

SECRET_VALUE_PATTERNS = (
    re.compile(r"ghp_[A-Za-z0-9_]+"),
    re.compile(r"github_pat_[A-Za-z0-9_]+"),
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"^glpat-[A-Za-z0-9_-]+$"),
)


def _collect_strings(obj: object) -> list[str]:
    if isinstance(obj, str):
        return [obj]
    if isinstance(obj, dict):
        out: list[str] = []
        for k, v in obj.items():
            out.append(str(k))
            out.extend(_collect_strings(v))
        return out
    if isinstance(obj, list):
        out: list[str] = []
        for item in obj:
            out.extend(_collect_strings(item))
        return out
    return []


def _is_dangerous_path(value: str) -> bool:
    normalized = value.strip()
    return any(p.match(normalized) for p in DANGEROUS_PATH_PATTERNS)


def _looks_like_hardcoded_secret(value: str) -> bool:
    if "${env:" in value or value.startswith("${"):
        return False
    return any(p.search(value) for p in SECRET_VALUE_PATTERNS)


def main() -> int:
    errors: list[str] = []
    warnings: list[str] = []
    summary: list[str] = []

    if not MCP_PATH.is_file():
        errors.append(f"Missing MCP config: {MCP_PATH.relative_to(REPO_ROOT)}")
        _print_report(errors, warnings, summary)
        return 1

    try:
        raw = MCP_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        errors.append(f"Invalid JSON in {MCP_PATH.name}: {exc}")
        _print_report(errors, warnings, summary)
        return 1

    servers = data.get("mcpServers")
    if not isinstance(servers, dict):
        errors.append("mcpServers must be an object")
        _print_report(errors, warnings, summary)
        return 1

    names = sorted(servers.keys())
    summary.append(f"servers ({len(names)}): {', '.join(names) if names else '(none)'}")

    if "playwright" not in servers:
        warnings.append("playwright server not configured (recommended for UI rounds)")

    for name, cfg in servers.items():
        if not isinstance(cfg, dict):
            errors.append(f"server '{name}' must be an object")
            continue
        command = cfg.get("command", "?")
        args = cfg.get("args", [])
        arg_preview = " ".join(str(a) for a in args[:4])
        if len(args) > 4:
            arg_preview += " ..."
        summary.append(f"  - {name}: command={command!r} args=[{arg_preview}]")

        env = cfg.get("env", {})
        if isinstance(env, dict):
            for key, val in env.items():
                if isinstance(val, str) and _looks_like_hardcoded_secret(val):
                    errors.append(
                        f"server '{name}' env.{key} looks like a hardcoded secret; use ${{env:...}}"
                    )

        if name == "filesystem" and isinstance(args, list):
            for arg in args:
                if not isinstance(arg, str):
                    continue
                if _is_dangerous_path(arg):
                    errors.append(
                        f"filesystem MCP arg {arg!r} is dangerously broad; "
                        "use ${workspaceFolder} only"
                    )
                if arg in ("/", "\\", "C:\\", "C:/"):
                    errors.append(f"filesystem MCP must not grant {arg!r}")

        if name == "chrome-devtools" and isinstance(args, list):
            blob = " ".join(str(a) for a in args)
            if (
                "chrome_devtools_mcp_light_novel" not in blob
                and "light_novel-chrome-profile" not in blob
                and "--userDataDir" not in blob
            ):
                warnings.append(
                    "chrome-devtools uses shared default profile risk; "
                    "prefer scripts/chrome_devtools_mcp_light_novel.sh "
                    "(see docs/mcp_isolation_strategy_light_novel.md)"
                )

    # Scan all string values for accidental secrets (without printing values).
    for s in _collect_strings(data):
        if _looks_like_hardcoded_secret(s):
            errors.append("config contains a value that looks like a hardcoded secret")
            break

    github_cfg = servers.get("github", {})
    if isinstance(github_cfg, dict):
        env = github_cfg.get("env", {})
        token_ref = env.get("GITHUB_PERSONAL_ACCESS_TOKEN", "") if isinstance(env, dict) else ""
        if not token_ref:
            warnings.append(
                "github MCP has no GITHUB_PERSONAL_ACCESS_TOKEN env mapping; "
                "set GITHUB_TOKEN locally for remote API access"
            )
        elif isinstance(token_ref, str) and "${env:" not in token_ref:
            warnings.append(
                "github MCP token should use ${env:GITHUB_TOKEN}, not a literal value"
            )

    _print_report(errors, warnings, summary)
    return 1 if errors else 0


def _print_report(errors: list[str], warnings: list[str], summary: list[str]) -> None:
    print("MCP config check")
    print(f"  path: {MCP_PATH.relative_to(REPO_ROOT)}")
    print("  summary:")
    for line in summary:
        print(f"    {line}")
    if warnings:
        print("  warnings:")
        for w in warnings:
            print(f"    - {w}")
    if errors:
        print("  errors:")
        for e in errors:
            print(f"    - {e}")
    status = "FAIL" if errors else "PASS"
    print(f"  result: {status}")


if __name__ == "__main__":
    sys.exit(main())
