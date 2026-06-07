# MCP Health Report (light_novel)

Generated: 2026-06-07T08:46:17Z

## Summary

- Repository: `/Users/alalapi/PycharmProjects/light_novel`
- Git branch: `main`
- Isolation strategy doc: present
- `.cursor/mcp.json`: present
- chrome-devtools isolated config: **yes** (uses project wrapper script)
- Recommend Playwright fallback: **no**

## Chrome profile status

| profile | exists | locked | detail |
|---|---|---|---|
| default `/Users/alalapi/.cache/chrome-devtools-mcp/chrome-profile` | yes | yes | process list references profile path |
| project `/Users/alalapi/.cache/chrome-devtools-mcp/light_novel-chrome-profile` | yes | no | no open file handles detected |

## MCP config check

- `check_mcp_config.py`: PASS
- Last line: `  result: PASS`

## MCP documentation

- `mcp_current_status_light_novel.md`: present
- `chrome_devtools_profile_conflict_audit.md`: present
- `mcp_isolation_strategy_light_novel.md`: present
- `agent_tooling_strategy.md`: present
- `mcp_playwright_setup_plan.md`: present

## Agent guidance

1. Prefer **playwright** for UI verification when chrome-devtools reports profile lock.
2. Profile isolation (`userDataDir`) takes priority over port changes.
3. After editing `.cursor/mcp.json`, reload Cursor window before probing MCP tools.
4. Do not kill other projects' Chrome/MCP processes to reclaim the shared profile.
