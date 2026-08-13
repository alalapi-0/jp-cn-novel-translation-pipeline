# Codex Handoff

Template — copy and fill when transferring work from Cursor to Codex.

## Repo

- Name: `light_novel`
- Type: AI novel translation pipeline + workbench
- Root: `${REPO_ROOT}` _(resolve from the current checkout; do not hard-code a host path)_

## Current branch

`main` _(update)_

## Current goal

_One sentence objective for Codex round._

## Must read

- [ ] `AGENTS.md`
- [ ] `agent_layer.yaml`
- [ ] `agent_tools.yaml`
- [ ] `docs/TOOL_USAGE_POLICY.md`
- [ ] `docs/AGENT_RUNBOOK.md`
- [ ] `reports/current-cohort-report.json`
- [ ] _Task-specific files listed below_

## Current P0/P1

| ID | Severity | Description |
|----|----------|-------------|
| | | |

## Latest gate result

- Path: `reports/gate_result.json`
- Status: _passed | warning | failed_
- Notes: _

## Relevant files

- _
- _

## Do not touch

- `.env`, secrets, `input_jp/*`, `input_cn/*` real content
- `governance/repo_protocol_standard.yaml` unless governance round
- Real API enablement flags

## Tools expected

- [ ] shell / pytest
- [ ] Context7 or WebSearch for fresh API docs
- [ ] _optional: browser if UI task_

## Commands to run

```bash
npm run check:tooling   # live-safe control-plane checks
# Full agent_gate, when required by the task contract, runs only in a
# disposable isolated copy and none of its outputs may be written back.
```

## Acceptance criteria

- [ ] Scope limited to stated goal
- [ ] Contract-selected targeted checks pass; isolated full-gate warnings are documented when that gate is required
- [ ] `reports/current-cohort-report.json` updated
- [ ] No secrets in diff
- [ ] If the round changes Git-safe files: exact cohort plan is registered and approved, and the standing finalizer verifies remote SHA before the next handoff

## Return format

Codex reply should include:

1. Summary of changes
2. Gate/test commands run + results
3. Remaining P0/P1
4. Suggested next scoped task from `docs/final_state_round_task_list.md` or the current approved contract (`docs/AGENT_ROADMAP.md` is historical only)

Do not suggest item 4 while a Git-safe cohort is only local or remotely unverified.
