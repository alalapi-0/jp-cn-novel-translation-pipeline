# Search Policy

When agents must search, how to search, and how to record results.

## Must search

1. Cursor / Codex / MCP / Playwright / Browser / Chrome DevTools / GitHub CLI capability questions.
2. Third-party library API, framework config, version differences.
3. Platform publish rules (WeChat, social, app stores) when publishing features are touched.
4. AI model API pricing, limits, auth, error codes before changing provider code.
5. Security, compliance, payment rules when relevant.
6. Errors not explainable from local code alone.
7. User says “查一下”, “搜索”, “最新”, or asks for current official behavior.

## Prefer sources (in order)

1. Official documentation (vendor site)
2. Official changelog / release notes
3. Official GitHub repository
4. Standards (RFC, W3C, etc.)
5. Peer-reviewed or authoritative technical writing
6. Community — supplementary only

## Must not

- Treat forum posts as official platform policy.
- Invent API versions or pricing.
- Skip logging when search was required.
- Use search results without noting uncertainty.

## Recording

All non-trivial searches → `docs/RESEARCH_NOTES.md` with:

- Date
- Query
- Source type
- Key finding
- Relevance
- Risk / uncertainty
- Action encoded into repo (file/link)

## If search unavailable

Record `TOOL_UNAVAILABLE_WEB_SEARCH` in round report and `docs/RESEARCH_NOTES.md`.

Fallback: ask user; use Context7; use pinned local docs with “may be stale” warning.

## This repo defaults

- `agent_layer.yaml`: `require_web_search_for_fresh_info: true`
- Context7 MCP configured for library docs
- Cursor WebSearch available in standard Agent thread

## Translation / novel pipeline

Search when changing:

- OpenRouter / model-router profiles
- Platform export (if enabled later)
- Copyright / licensing for source material handling

Default pipeline rounds use dry-run; search before enabling real API cost paths.
