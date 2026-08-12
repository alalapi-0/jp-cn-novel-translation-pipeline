# Agent Runbook

Operational steps for every Tool-aware Agent round (Cursor primary, Codex compatible).

## Before you touch code

1. `python3 scripts/agent.py status` (optional; continuous mode)
2. Read in order:
   - `AGENTS.md`
   - `agent_layer.yaml`
   - `agent_tools.yaml`
   - `docs/TOOL_USAGE_POLICY.md`
   - `reports/latest-agent-report.json`
3. `git status --short`
4. Read `reports/tool_probe_report.json`; refreshing reports or syncing YAML is a separate authorized write, never an automatic startup step
5. Decide: need web search? → `docs/SEARCH_POLICY.md`

## During implementation

- One small scope (`agent_layer.yaml`: `max_scope_per_round: small`)
- Match tools to stage (`agent_tools.yaml` → `task_stage_mapping`)
- UI work: start dev server, use browser tools
- No `.env` reads; no secret output
- No real API / publish unless explicitly allowed

## Validation

In the real working tree, run only the contract-selected targeted/read-only checks. For control-plane changes, `npm run check:tooling` is the live-safe entrypoint. A full `scripts/agent_gate.py` run is allowed only in a disposable isolated copy, and none of its outputs may be written back.

UI work still requires the task-specific browser checks and tests named by the active contract.

## After implementation

1. Update `governance/round_state.yaml` if governance round
2. Write `reports/latest-agent-report.json`
3. Append `reports/agent_audit_log.jsonl`
4. `git diff` — verify no secrets / raw novel text
5. Commit only after an explicit current-turn owner request; push requires a separate current-turn authorization, and retrying a failed push requires new authorization

## Exit codes (`agent_gate.py`)

| Code | Meaning |
|------|---------|
| 0 | PASS |
| 1 | WARNING |
| 2 | BLOCKED |

## Blockers

| Tag | Meaning |
|-----|---------|
| `BLOCKED_ENV` | Missing dependency or permission |
| `TOOL_UNAVAILABLE` | Tool not callable; document fallback |
| `BLOCKED: MISSING_FROM_THREAD_TOOL_REGISTRY` | Browser MCP missing in thread |

## Cross-references

- Safety: `docs/AGENT_SAFETY.md`
- Reporting: `docs/AGENT_REPORTING.md`
- Current roadmap: `docs/final_state_implementation_roadmap.md` and `docs/final_state_round_task_list.md`
- Historical Agent Layer snapshot (non-operative): `docs/AGENT_ROADMAP.md`
- Legacy pipeline: `docs/agent_operating_manual.md`
- MCP: `docs/runbooks/mcp_browser_tools_runbook.md`

## Common commands

```bash
npm run dev:frontend
npm run test:py
npm run test:ui
npm run check:mcp
python3 scripts/run_real_api_smoke.py          # dry-run default
python3 scripts/run_browser_inspection.py
npm run check:tooling
# Full gate: run python3 scripts/agent_gate.py only inside a disposable isolated copy.
```
