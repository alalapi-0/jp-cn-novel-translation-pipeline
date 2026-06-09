#!/usr/bin/env python3
"""Sync agent_tools.yaml availability fields from reports/tool_probe_report.json.

Read-only with respect to external systems — only updates local YAML from probe report.
Does not read .env or print secrets.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_PROBE = REPO_ROOT / "reports" / "tool_probe_report.json"
DEFAULT_YAML = REPO_ROOT / "agent_tools.yaml"

LOCAL_PROBE_KEYS: dict[str, tuple[str, str | tuple[str, ...]]] = {
    "shell": ("shell", "shell"),
    "git": ("git", "git"),
    "node_npm": ("node_npm", ("node", "npm")),
    "python": ("python", "python3"),
    "gh_cli": ("gh_cli", "gh"),
    "ffmpeg": ("ffmpeg", "ffmpeg"),
    "docker": ("docker", "docker"),
    "playwright": ("playwright", "playwright_npx"),
}

MCP_NAME_TO_YAML: dict[str, str] = {
    "filesystem": "filesystem_mcp",
    "github": "github_mcp",
    "playwright": "playwright",
    "chrome-devtools": "chrome_devtools",
    "context7": "context7",
    "stitch": "stitch_mcp",
}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _truncate(text: str, limit: int = 120) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    return text[: limit - 3] + "..."


def _load_yaml(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:
        raise SystemExit("PyYAML required: pip install pyyaml") from exc
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} root must be a mapping")
    return data


def _dump_yaml(data: dict[str, Any], path: Path) -> None:
    import yaml

    text = yaml.dump(
        data,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
        width=120,
    )
    path.write_text(text, encoding="utf-8")


def _local_available(local_tools: dict[str, Any], key: str | tuple[str, ...]) -> bool:
    if isinstance(key, str):
        entry = local_tools.get(key) or {}
        return bool(entry.get("available"))
    return all(_local_available(local_tools, k) for k in key)


def _local_probe_result(local_tools: dict[str, Any], key: str | tuple[str, ...]) -> str:
    if isinstance(key, str):
        entry = local_tools.get(key) or {}
        return _truncate(str(entry.get("output") or ""))
    parts = [_local_probe_result(local_tools, k) for k in key if _local_probe_result(local_tools, k)]
    return "; ".join(parts)[:120]


def _normalize_callable_now(value: Any) -> Any:
    if value is True or value is False:
        return value
    text = str(value).strip().lower()
    if text == "true":
        return True
    if text == "false":
        return False
    return str(value)


def _mcp_lookup(mcp_servers: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {s["name"]: s for s in mcp_servers if isinstance(s, dict) and "name" in s}


MCP_YAML_KEYS = frozenset(MCP_NAME_TO_YAML.values())


def build_sync_plan(probe: dict[str, Any], yaml_data: dict[str, Any]) -> dict[str, Any]:
    local_tools = probe.get("local_tools") or {}
    mcp_by_name = _mcp_lookup(probe.get("mcp_servers") or [])
    tools = yaml_data.setdefault("tools", {})
    changes: list[dict[str, Any]] = []

    for yaml_key, (_, probe_key) in LOCAL_PROBE_KEYS.items():
        tool = tools.setdefault(yaml_key, {})
        new_available = _local_available(local_tools, probe_key)
        field_changes: dict[str, Any] = {}
        if tool.get("available") != new_available:
            field_changes["available"] = {"from": tool.get("available"), "to": new_available}
            tool["available"] = new_available
        if yaml_key not in MCP_YAML_KEYS:
            new_probe = _local_probe_result(local_tools, probe_key)
            if new_probe and tool.get("probe_result") != new_probe:
                field_changes["probe_result"] = {"from": tool.get("probe_result"), "to": new_probe}
                tool["probe_result"] = new_probe
        if field_changes:
            changes.append({"tool": yaml_key, "fields": field_changes})

    java_ok = _local_available(local_tools, "java")
    mvn_ok = _local_available(local_tools, "mvn")
    jm = tools.setdefault("java_maven", {})
    jm_available = java_ok and mvn_ok
    if jm.get("available") != jm_available:
        changes.append(
            {
                "tool": "java_maven",
                "fields": {"available": {"from": jm.get("available"), "to": jm_available}},
            }
        )
        jm["available"] = jm_available

    web = probe.get("web_search") or {}
    ws = tools.setdefault("web_search", {})
    ws_available = web.get("available") is True or web.get("available") == "true"
    if ws.get("available") != ws_available:
        changes.append(
            {
                "tool": "web_search",
                "fields": {"available": {"from": ws.get("available"), "to": ws_available}},
            }
        )
        ws["available"] = ws_available

    for mcp_name, yaml_key in MCP_NAME_TO_YAML.items():
        server = mcp_by_name.get(mcp_name)
        tool = tools.setdefault(yaml_key, {})
        field_changes: dict[str, Any] = {}

        if server:
            configured = bool(server.get("configured", True))
            callable_now = _normalize_callable_now(server.get("callable_now", "unknown"))
            probe_result = _truncate(str(server.get("probe_result") or ""))
            local_ok = True
            if yaml_key in LOCAL_PROBE_KEYS:
                _, probe_key = LOCAL_PROBE_KEYS[yaml_key]
                local_ok = _local_available(local_tools, probe_key)
            available = local_ok and (
                callable_now is True or callable_now == "config_only"
            )

            for field, new_val in (
                ("configured", configured),
                ("callable_now", callable_now),
                ("available", available),
                ("probe_result", probe_result),
            ):
                if new_val and tool.get(field) != new_val:
                    field_changes[field] = {"from": tool.get(field), "to": new_val}
                    tool[field] = new_val
        else:
            if tool.get("configured") is not False:
                field_changes["configured"] = {"from": tool.get("configured"), "to": False}
                tool["configured"] = False
            if tool.get("callable_now") != "unknown":
                field_changes["callable_now"] = {"from": tool.get("callable_now"), "to": "unknown"}
                tool["callable_now"] = "unknown"

        if field_changes:
            changes.append({"tool": yaml_key, "mcp": mcp_name, "fields": field_changes})

    yaml_data["updated_at"] = probe.get("timestamp") or _utc_now()
    yaml_data.setdefault("probe_sync", {})
    yaml_data["probe_sync"] = {
        "source": str(DEFAULT_PROBE.relative_to(REPO_ROOT)),
        "probe_timestamp": probe.get("timestamp"),
        "synced_at": _utc_now(),
        "probe_status": probe.get("status"),
        "changes_count": len(changes),
    }

    return {
        "changed": bool(changes),
        "changes": changes,
        "updated_at": yaml_data["updated_at"],
        "probe_timestamp": probe.get("timestamp"),
    }


def sync_agent_tools_from_probe(
    probe_path: Path = DEFAULT_PROBE,
    yaml_path: Path = DEFAULT_YAML,
    *,
    dry_run: bool = False,
) -> dict[str, Any]:
    if not probe_path.is_file():
        raise FileNotFoundError(f"Probe report not found: {probe_path}")
    if not yaml_path.is_file():
        raise FileNotFoundError(f"agent_tools.yaml not found: {yaml_path}")

    probe = json.loads(probe_path.read_text(encoding="utf-8"))
    yaml_data = _load_yaml(yaml_path)
    plan = build_sync_plan(probe, yaml_data)

    if plan["changed"] and not dry_run:
        _dump_yaml(yaml_data, yaml_path)

    plan["dry_run"] = dry_run
    plan["yaml_path"] = str(yaml_path.relative_to(REPO_ROOT))
    plan["probe_path"] = str(probe_path.relative_to(REPO_ROOT))
    return plan


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync agent_tools.yaml from tool probe report")
    parser.add_argument("--probe", type=Path, default=DEFAULT_PROBE, help="tool_probe_report.json path")
    parser.add_argument("--yaml", type=Path, default=DEFAULT_YAML, help="agent_tools.yaml path")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    parser.add_argument("--json", action="store_true", help="Print JSON summary")
    args = parser.parse_args()

    try:
        result = sync_agent_tools_from_probe(args.probe, args.yaml, dry_run=args.dry_run)
    except (FileNotFoundError, ValueError, json.JSONDecodeError) as exc:
        print(f"sync_agent_tools_from_probe: ERROR {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        mode = "dry-run" if args.dry_run else "write"
        print(
            f"sync_agent_tools_from_probe: {mode} "
            f"changes={len(result['changes'])} -> {result['yaml_path']}"
        )
        for item in result["changes"]:
            print(f"  - {item['tool']}: {', '.join(item['fields'].keys())}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
