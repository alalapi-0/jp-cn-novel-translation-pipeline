# MCP Health Report (light_novel)

Generated: 2026-06-07T09:26:16Z

## Summary

- Repository: `/Users/alalapi/PycharmProjects/light_novel`
- Git branch: `main`
- Decision: **RUNBOOK_READY**
- Runbook: present (`docs/runbooks/mcp_browser_tools_runbook.md`)
- Playwright: available (playwright dependencies present)
- `.cursor/mcp.json`: present
- chrome-devtools isolated config: **yes** (uses project wrapper script)
- Recommend Playwright fallback: **no**

## Chrome profile status

| profile | exists | locked | detail |
|---|---|---|---|
| default `/Users/alalapi/.cache/chrome-devtools-mcp/chrome-profile` | yes | no | no open file handles detected |
| project `/Users/alalapi/.cache/chrome-devtools-mcp/light_novel-chrome-profile` | yes | no | no open file handles detected |

## Infrastructure checks

- `agent_gate.py`: present
- Example MCP config: present
- Project wrapper executable: yes

## MCP config check

- `check_mcp_config.py`: PASS
- Last line: `  result: PASS`

## MCP documentation

- `mcp_current_status_light_novel.md`: present
- `chrome_devtools_profile_conflict_audit.md`: present
- `mcp_isolation_strategy_light_novel.md`: present
- `tooling_current_status.md`: present
- `agent_tooling_strategy.md`: present
- `mcp_playwright_setup_plan.md`: present

## Agent guidance

1. Read `docs/runbooks/mcp_browser_tools_runbook.md` before browser/MCP tasks.
2. Prefer **playwright** for UI verification when chrome-devtools reports profile lock.
3. Profile isolation (`userDataDir`) takes priority over port changes.
4. After editing `.cursor/mcp.json`, reload Cursor window before probing MCP tools.
5. Do not kill other projects' Chrome/MCP processes to reclaim the shared profile.
