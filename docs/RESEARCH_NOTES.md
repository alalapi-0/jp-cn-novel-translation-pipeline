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

## Query 5 — OpenRouter pricing (AL-006)

- Query: OpenRouter API pricing official per million tokens 2026
- Source type: official docs (openrouter.ai/docs/faq, openrouter.ai/pricing, GET /api/v1/models)
- Key finding: No flat rate — per-model input/output $/M tokens; OpenRouter passes through provider list prices (no inference markup); credit purchase has ~5.5% platform fee on pay-as-you-go tier; live prices in Models API `pricing` object.
- Relevance: Cost guard and smoke scripts must not hardcode model prices; fetch catalog or document refresh cadence.
- Risk / uncertainty: Model IDs and $/M change frequently; third-party aggregators (costgoat, apicents) are hints only — use OpenRouter API as source of truth.
- Action to encode into repo: `docs/api_provider_strategy.md` OpenRouter section, `docs/RESEARCH_NOTES.md` (this entry)

## Query 6 — Playwright test vs MCP version alignment (AL-007)

- Query: @playwright/mcp @playwright/test version pin alignment official 2026
- Source type: official docs (playwright.dev MCP getting started) + GitHub issues (microsoft/playwright-mcp #1091, #917)
- Key finding: `@playwright/mcp` and `@playwright/test` are versioned independently; official MCP config uses `@playwright/mcp@latest`; MCP may bundle alpha playwright-core while repo pins stable `@playwright/test` for CI; browser mismatch fixed via `npx playwright install` from workspace CLI version.
- Relevance: Agents must not assume MCP semver equals test semver; E2E gate uses `npm run test:ui`; MCP is interactive fallback.
- Risk / uncertainty: `@playwright/mcp` npm version (e.g. 0.0.x) ≠ Playwright 1.x; `npx playwright run-mcp-server` mentioned for 1.56+ but not stable replacement for separate package as of 1.60.
- Action to encode into repo: `docs/testing/PLAYWRIGHT_VERSION_ALIGNMENT.md`, cross-links in TOOL_INVENTORY and USER_VIEW_TESTING

## Query 7 — Cursor CLI / cursor-agent install probe (AL-008)

- Query: Cursor CLI cursor-agent installation official docs mcp list 2026
- Source type: official docs (cursor.com/docs/cli/installation, cli/overview, cli/reference/parameters)
- Key finding: Install via `curl https://cursor.com/install -fsS | bash`; verify with `agent --version` (official) or `cursor-agent --version` (this repo); subcommands include `mcp list`, `mcp list-tools`, `status`, `update`; CLI MCP state is separate from IDE Agent thread tool registry.
- Relevance: `npm run check:cursor-mcp` and `tool_probe.py` → `cursor_cli` for machine-readable availability; PATH `agent` may alias non-Cursor products — prefer `cursor-agent` in scripts.
- Risk / uncertainty: Account/plan features (Cloud Agent, sandbox) vary; CLI `mcp list` may show needs approval even when IDE thread has tools loaded.
- Action to encode into repo: `docs/TOOL_INVENTORY.md` § I, `scripts/tool_probe.py` probe_cursor_cli(), `reports/tool_probe_report.json`

## Query 8 — Model provider fallback matrix (AL-T05)

- Query: OpenRouter model fallback routing official 2026
- Source type: official docs (openrouter.ai/docs) + `docs/api_provider_strategy.md`
- Key finding: Prefer OpenRouter `models` catalog + per-run router in repo; fallback order should be documented not hardcoded prices; on provider error use alternate model ID from same tier in dry-run first.
- Relevance: Smoke scripts and autopilot should log chosen model + fallback reason without enabling real API in agent rounds.
- Action: extend `docs/api_provider_strategy.md` fallback section; cost-sensitive runs re-query Models API
