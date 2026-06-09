# Tool Inventory

Date: 2026-06-09 (AL-008 Cursor CLI probe)  
Agent surface: Cursor (Tool-aware Agent Layer 2.0)  
Probe script: `python3 scripts/tool_probe.py --sync-docs`  
Machine report: `reports/tool_probe_report.json`

## Summary

| Category | Status | Notes |
|----------|--------|-------|
| Local shell / git | Available | macOS, branch `main`, repo at workspace root |
| Node / npm | Available | v26 / 11.12 |
| Python / uv | Available | 3.14.5 / uv 0.11.19 |
| Java / Maven / Docker | Unavailable | Not required for current pipeline |
| gh CLI | Available | v2.92.0 |
| ffmpeg | Available | v8.0.1 |
| Playwright | Available | npx v1.60.0; `@playwright/test` in package.json; MCP `@latest` — see `docs/testing/PLAYWRIGHT_VERSION_ALIGNMENT.md` |
| Cursor CLI | Available | `cursor-agent` on PATH — see § I below |
| Web search | Available | Cursor `WebSearch` in this thread |
| Codex | Manual | Protocol compatible; not verified in-thread |

`CURSOR_CONFIG_VISIBILITY: limited` — global Cursor settings, Cloud Agent quotas, and per-account Skills/Hooks must be confirmed in Cursor UI.

## A. Local Tools

| Tool | Available | Probe | Output (truncated) |
|------|-----------|-------|---------------------|
| shell | yes | `pwd` | `/Users/alalapi/PycharmProjects/light_novel` |
| git | yes | `git status --short` | working tree changes present |
| git branch | yes | `git branch --show-current` | `main` |
| node | yes | `node -v` | v26.0.0 |
| npm | yes | `npm -v` | 11.12.1 |
| pnpm | no | `pnpm -v` | not installed |
| python3 | yes | `python3 --version` | 3.14.5 |
| uv | yes | `uv --version` | 0.11.19 |
| java | no | `java -version` | JRE not found |
| mvn | no | `mvn -v` | not installed |
| docker | no | `docker --version` | not installed |
| make | yes | `make --version` | GNU Make 3.81 |
| gh | yes | `gh --version` | 2.92.0 |
| ffmpeg | yes | `ffmpeg -version` | 8.0.1 |
| playwright | yes | `npx playwright --version` | 1.60.0 (`@playwright/test` pin; MCP independent — AL-007) |

## B. Cursor Capabilities

| Artifact | Present | Path / notes |
|----------|---------|--------------|
| Project rules | yes | `.cursor/rules/*.mdc` (5 files + new agent-layer rules) |
| MCP config | yes | `.cursor/mcp.json` |
| AGENTS.md | yes | repo root; extended for Layer 2.0 |
| Browser runbook | yes | `docs/cursor_browser_ui_runbook.md` |
| MCP runbook | yes | `docs/runbooks/mcp_browser_tools_runbook.md` |
| Skills (global) | manual | `~/.cursor/skills-cursor/` — not repo-scoped |
| Hooks | manual | not configured in this repo |
| Cloud Agent | manual | confirm in Cursor account |
| Subagents | yes | Cursor Task tool; browser tasks forbidden in multitask |
| CLI | yes | `cursor-agent` — § I; `npm run check:cursor-mcp` |

Manual UI confirmation:

- Settings → MCP: reload after `.cursor/mcp.json` edits
- Browser tools: use foreground Agent only (project rule)
- Stitch: requires `STITCH_API_KEY` env var

## C. Codex Compatibility

| Item | Status |
|------|--------|
| `CODEX_AVAILABLE` | `manual` |
| `AGENTS.md` | present, cross-agent |
| `agent_layer.yaml` | present |
| Codex CLI on PATH | not detected |
| `~/.codex/config.toml` | not verified |

Future Codex sessions should read the same files listed in `docs/CODEX_USAGE.md`.

## D. MCP Servers (configured in `.cursor/mcp.json`)

| name | configured | callable_now | safe_probe | fallback |
|------|------------|--------------|------------|----------|
| filesystem | true | true | list_allowed_directories (read-only) | Read/Grep |
| github | true | false | list_commits or search (read-only if token present) | `gh` CLI |
| playwright | true | true | browser_snapshot on local URL | `npm run test:ui` |
| chrome-devtools | true | true | navigate local workbench + console check | playwright MCP |
| context7 | true | true | resolve-library-id + query-docs | WebSearch |
| stitch | true | true | list_projects (requires STITCH_API_KEY) | design docs |
| Prisma-Local | true | config_only | prisma mcp launcher check (not used by this repo) | N/A |

Additional thread MCP (Cursor built-in): `cursor-ide-browser`, `cursor-app-control`.

Probe note: AL-003 automated safe probes — no `deferred_to_agent_thread` results. filesystem scope `${workspaceFolder}` only; github via gh auth; chrome-devtools and Prisma-Local are `config_only` (not loaded in Cursor thread).

## E. Web Search

| Field | Value |
|-------|-------|
| Available | yes (Cursor WebSearch) |
| Policy | `docs/SEARCH_POLICY.md` |
| Log | `docs/RESEARCH_NOTES.md` |

## F. Browser / User-View

| Item | Status |
|------|--------|
| `playwright.config.ts` | present |
| `npm run test:ui` | defined |
| `npm run dev:frontend` | port 5174 |
| `scripts/run_browser_inspection.py` | present |
| `scripts/user_view_test.py` | present (Layer 2.0) |
| cursor-ide-browser MCP | available in thread |

## G. GitHub / Remote

| Item | Value |
|------|-------|
| remote | `origin` → GitHub |
| gh CLI | available |
| GitHub MCP | configured |
| commit / push / PR | user explicit only |

## H. Context7 / Docs

| Item | Status |
|------|--------|
| context7 MCP | configured |
| recommended_docs | Playwright, pytest, MCP SDK — see `agent_tools.yaml` |

## I. Cursor CLI (`cursor-agent`)

Machine-readable probe: `reports/tool_probe_report.json` → `cursor_cli` (AL-008).

| Field | Value (this environment) |
|-------|--------------------------|
| Binary | `cursor-agent` (preferred for repo checks) |
| On PATH | yes → `~/.local/bin/cursor-agent` |
| Version probe | `cursor-agent --version` → `2026.05.28-a70ca7c` |
| Install (macOS/Linux/WSL) | `curl https://cursor.com/install -fsS \| bash` |
| Post-install PATH | add `~/.local/bin` to shell PATH |
| Update | `cursor-agent update` (or `agent update` per official docs) |
| Repo check script | `npm run check:cursor-mcp` → `scripts/check_cursor_mcp_status.sh` |
| Official docs | [cursor.com/docs/cli/installation](https://cursor.com/docs/cli/installation) |

### Binary naming

| Command | Meaning in this repo |
|---------|----------------------|
| `cursor-agent` | **Cursor CLI** — use for `mcp list`, `--version`, headless agent |
| `agent` (official default) | Cursor docs install `agent` to `~/.local/bin`; **may collide** with other CLIs on PATH (e.g. Grok). If `which agent` ≠ Cursor, use `cursor-agent` explicitly. |

### Useful subcommands (read-only / local)

```bash
cursor-agent --version
cursor-agent mcp list
cursor-agent mcp list-tools <server>
cursor-agent status          # auth (no secret output in our scripts)
npm run check:cursor-mcp     # repo wrapper; see docs/cursor_tool_registry_check.md
```

### Limitations (important)

1. **CLI layer ≠ Agent thread** — `cursor-agent mcp list` showing ready does **not** prove the current Chat/Agent conversation exposes MCP tools. See `docs/cursor_tool_registry_check.md`.
2. **Approval gate** — CLI may report `not loaded (needs approval)` until servers are approved in Cursor Settings → MCP.
3. **Not a CI substitute** — use `npm run check:mcp`, `python3 scripts/tool_probe.py`, and `npm run test:ui` for deterministic gates; Cursor CLI is optional diagnostics.
4. **Subscription** — Cursor CLI requires a Cursor account/subscription per vendor docs; probe only checks binary presence.

### When to use

| Task | Tool |
|------|------|
| Terminal agent session | `cursor-agent` / `agent` interactive |
| MCP server list (CLI) | `cursor-agent mcp list` |
| Repo automated probe | `python3 scripts/tool_probe.py` → `cursor_cli` |
| Browser/UI in IDE Agent | foreground Chat + MCP (`playwright`, `cursor-ide-browser`) — not CLI |

## Blockers

None hard-blocking for Layer 2.0 documentation round. Soft: dev server may be offline during static probes.

## Refresh

```bash
python3 scripts/tool_probe.py
python3 scripts/agent_gate.py --json
```
