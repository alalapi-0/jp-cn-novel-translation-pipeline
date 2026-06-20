# Tool Usage Policy

Tool-aware Agent Layer 2.0 — maps tasks to tools for Cursor, Codex, and local scripts.

## 1. Must-use by task

| Task stage | Must use | Why |
|------------|----------|-----|
| Round start | Read `AGENTS.md`, `agent_tools.yaml`, `reports/latest-agent-report.json` | Continuity |
| Tool planning | `scripts/tool_probe.py` or read `reports/tool_probe_report.json` | Avoid false assumptions |
| Code understanding | repo search, Read/Grep, filesystem MCP | Ground truth in repo |
| Fresh external facts | WebSearch and/or Context7 | Avoid stale training data |
| UI change | Browser MCP or Playwright + dev server | User-view required |
| Deterministic validation | `scripts/agent_gate.py`, `npm run check:tooling` | Gate-driven |
| Round end | `reports/latest-agent-report.json` + audit log | Next agent handoff |

## 2. Preferred tools

| Task | Preferred | Alternative |
|------|-----------|-------------|
| Library API questions | Context7 | WebSearch official docs |
| Platform / pricing / rules | WebSearch official | User-provided docs |
| DOM/console/network debug | chrome-devtools MCP | cursor-ide-browser CDP |
| E2E regression | `npm run test:ui` | Playwright MCP |
| UI design input | Stitch MCP → `docs/design/stitch/` | Manual templates |
| Issues/PRs | GitHub MCP | `gh` CLI |
| File verification | filesystem MCP | Read tool |
| Long refactor | Codex (handoff) | Cursor multi-round |

## 3. Forbidden / restricted

| Action | Rule |
|--------|------|
| Real paid API | Default off; only if env + protocol allow |
| Real publish | Default off |
| Read/print `.env` | Forbidden |
| Force push / hard reset | User explicit only |
| Auto push / auto PR | Forbidden unless user asks |
| Browser in Multitask subagent | Forbidden (project rule) |
| Stitch → blind overwrite `frontend/` | Forbidden |
| MCP filesystem outside workspace | Forbidden |
| Delete failing tests to pass gate | Forbidden |

## 4. Fallback matrix

| Tool unavailable | Fallback |
|------------------|----------|
| WebSearch | Record `TOOL_UNAVAILABLE_WEB_SEARCH`; ask user |
| Context7 | WebSearch official docs |
| Playwright MCP | `npm run test:ui` |
| chrome-devtools | Playwright MCP or cursor-ide-browser |
| GitHub MCP | `git` + `gh` |
| Stitch | `docs/design/stitch/` templates |
| Codex | Cursor small rounds + `docs/CODEX_HANDOFF.md` when quota returns |

## 5. Cursor vs Codex

**Cursor (primary):** local edits, MCP, browser, small scoped rounds, docs/rules, gates.

**Codex (secondary):** large refactors, deep review, worktree parallelism — only after handoff pack.

See `docs/CODEX_USAGE.md`.

## 6. Avoid “configured but unused” MCP

Each round report must list `tools_used` and `tools_not_used` with reasons.

If MCP was available and task involved UI/docs/GitHub, explain why a tool was skipped.

## 7. Web search hygiene

- Prefer official docs, release notes, GitHub repos of vendors.
- Log in `docs/RESEARCH_NOTES.md` with date and uncertainty.
- Community posts are hints, not policy.

## 8. Browser user-view

1. `npm run dev:frontend`
2. Open `http://127.0.0.1:5174/`
3. Snapshot + console + key network paths
4. Before/after notes in `artifacts/` (not committed)

See `docs/USER_VIEW_TESTING.md`.

## 9. Real API / publish guards

- `REAL_API_TESTS_ENABLED`, `MAX_TEST_COST_USD` — see README
- Scripts: `run_real_api_smoke.py`, `run_openrouter_smoke.py --dry-run`
- Never enable real publish in agent layer rounds unless user explicitly opts in

## 10. Tool usage logging

Record in `reports/latest-agent-report.json`:

```json
{"tool": "context7", "purpose": "Playwright config", "result": "ok", "fallback_used": false}
```

Append summary line to `reports/agent_audit_log.jsonl` each round.

## Project-specific mapping (translation pipeline)

| Pipeline stage | Tools |
|----------------|-------|
| Chapter ingest | local scripts, dry-run |
| Translation / consistency | model-router dry-run; real API gated |
| Quality review | `run_quality_review.py`, workbench UI |
| Terminology | glossary fixtures, review pages |
| Continuous run | `scripts/agent.py`, `.agent_runtime/` |

Legacy tooling docs remain valid: `docs/agent_tooling_strategy.md`, `docs/runbooks/mcp_browser_tools_runbook.md`.

Rules coverage audit (AL-009): `docs/AGENT_RULES_COVERAGE_AUDIT.md`.
