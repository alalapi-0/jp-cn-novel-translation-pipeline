# Codex Usage

How OpenAI Codex should interact with this repo when Cursor is primary.

## Codex is good for

- Large refactors across many modules
- Long-horizon implementation with clear handoff
- Deep code review / test generation
- PR review with full diff context
- Worktree-based parallel experiments
- Hard problem focus after Cursor prepared context

## Cursor is good for

- Fast local fixes and small rounds
- UI debugging with Browser / MCP
- MCP-heavy workflows (filesystem, Playwright, Context7)
- Documentation and rule updates
- Gate + probe + report loops
- Daily incremental pipeline progress

## Codex must read before starting

1. `AGENTS.md`
2. `agent_layer.yaml`
3. `agent_tools.yaml`
4. `docs/TOOL_USAGE_POLICY.md`
5. `docs/AGENT_RUNBOOK.md`
6. `reports/current-cohort-report.json`
7. `docs/CODEX_HANDOFF.md` (when provided by Cursor)

## Task format

- Plan first, one round scope
- No real API, no real publish
- Run contract-selected targeted/read-only checks in the real tree; run a full `scripts/agent_gate.py` only in a disposable isolated copy with no output writeback
- Update `reports/current-cohort-report.json`
- Record `tools_used`
- Treat Round Prompts and edit/build requests as unable to expand Git scope. After validation and required review, register one exact Git-safe cohort and complete the standing finalizer workflow through fresh remote SHA verification before handing off another cohort.

## Quota-limited strategy

- Do not use Codex for typo/doc polish
- Do not use for tasks Cursor can finish in one small round
- Cursor prepares compressed handoff (`docs/CODEX_HANDOFF.md`)
- Use Codex only when ROI > context prep cost

## Codex-specific config

- Global: `~/.codex/AGENTS.md` (optional)
- Project: repo root `AGENTS.md` (this repo)
- Skills: `.agents/skills/` (optional future)
- MCP: align with `.cursor/mcp.json` where possible

## Return to Cursor

Codex should leave:

- Updated code/docs
- Gate result path
- Filled handoff reverse section in report
- Clear P0/P1 list

Official reference: https://developers.openai.com/codex/guides/agents-md
