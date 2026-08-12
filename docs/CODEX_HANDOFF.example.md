# Codex Handoff — Example (AL-027, no secrets)

Filled example for a hypothetical post-AL-013 session. Copy patterns only; update branch/goal before use.

## Repo

- Name: `light_novel`
- Type: AI novel translation pipeline + workbench
- Root: _(your clone path)_

## Current branch

`main`

## Current goal

Implement AL-018 gate triage helper and wire severity into `write_agent_report.py`.

## Must read

- [x] `AGENTS.md`
- [x] `agent_layer.yaml`
- [x] `agent_tools.yaml`
- [x] `docs/TOOL_USAGE_POLICY.md`
- [x] `docs/AGENT_RUNBOOK.md`
- [x] `reports/latest-agent-report.json`
- [ ] `scripts/gate_triage.py`, `scripts/write_agent_report.py`

## Current P0/P1

| ID | Severity | Description |
|----|----------|-------------|
| — | — | None at handoff time |

## Latest gate result

- Path: `reports/gate_result.json`
- Status: warning
- Notes: dirty tree expected during active development

## Relevant files

- `scripts/gate_triage.py`
- `scripts/write_agent_report.py`
- `schemas/agent_round_report.schema.json`

## Do not touch

- `.env`, secrets, `input_jp/*`, `input_cn/*` real content
- Real API enablement without user approval

## Commands to run

```bash
npm run check:tooling  # real-worktree targeted/read-only control-plane checks
# Run a full agent_gate only when the task contract requires it, inside a
# disposable isolated copy whose outputs are never written back.
```

`tool_probe.py` writes a report (and `--sync-docs` writes active docs), so it is not an implicit validation command. Run it only when the scoped task explicitly owns that refresh and review its exact outputs.

## Acceptance criteria

- [ ] Scope limited to stated goal
- [ ] Scoped targeted checks pass; any contract-required full gate was isolated with no writeback
- [ ] `reports/latest-agent-report.json` updated via `write_agent_report.py`
- [ ] No secrets in diff

Canonical template: `docs/CODEX_HANDOFF.md`
