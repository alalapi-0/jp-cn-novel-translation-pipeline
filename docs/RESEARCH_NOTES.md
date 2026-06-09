# Research Notes

Date: 2026-06-09  
Agent: Cursor  
Search capability: available (WebSearch + Context7 configured)

---

## Query 1 — Cursor Agent customization (Rules, Skills, MCP, AGENTS.md)

- Query: Cursor IDE Agent AGENTS.md MCP Rules Skills official 2026
- Source type: official docs (cursor.com/learn, cursor.com/docs)
- Key finding: Cursor uses `.cursor/rules/` for always-on rules, Skills (`SKILL.md`) for on-demand workflows, MCP via `.cursor/mcp.json`, and AGENTS.md for Cloud Agent operational setup.
- Relevance to this repo: Validates existing `.cursor/rules/` + `AGENTS.md` split; extend AGENTS.md for cross-agent Layer 2.0 without duplicating rules.
- Risk / uncertainty: Cloud-only AGENTS.md behavior vs local Agent may differ; local rules still apply via `.cursor/rules/`.
- Action to encode into repo: Updated `AGENTS.md`, `docs/CODEX_USAGE.md`, `.cursor/rules/agent-layer.mdc`

## Query 2 — Codex AGENTS.md, Skills, MCP, web search

- Query: OpenAI Codex AGENTS.md MCP skills web search official
- Source type: official docs (developers.openai.com/codex)
- Key finding: Codex reads layered AGENTS.md from global + project paths; skills in `.agents/skills/`; MCP in config; built-in web search with cached/live modes.
- Relevance: Same root `AGENTS.md` can serve Codex with `docs/CODEX_HANDOFF.md` for session context.
- Risk / uncertainty: Codex quota/sandbox defaults vary by account; not verified in this environment.
- Action to encode into repo: `docs/CODEX_USAGE.md`, `docs/CODEX_HANDOFF.md`, `agent_tools.yaml` codex surface

## Query 3 — Playwright (project UI stack)

- Query: Playwright test documentation 2026
- Source type: official docs (playwright.dev)
- Key finding: Repo uses `@playwright/test` v1.60.0 with `npm run test:ui`.
- Relevance: Primary E2E path for workbench UI.
- Risk / uncertainty: Python pytest-playwright is alternate; repo standard is Node Playwright.
- Action to encode into repo: `docs/USER_VIEW_TESTING.md`, `agent_layer.yaml`

## Query 4 — MCP configuration

- Query: MCP Cursor project configuration
- Source type: official + ecosystem docs
- Key finding: Project `.cursor/mcp.json` for team sharing; reload Cursor after edits.
- Relevance: Matches `npm run check:mcp`.
- Action to encode into repo: `scripts/tool_probe.py`, `docs/TOOL_INVENTORY.md`
