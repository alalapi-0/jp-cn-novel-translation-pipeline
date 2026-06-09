# Codex Handoff

Template — copy and fill when transferring work from Cursor to Codex.

## Repo

- Name: `light_novel`
- Type: AI novel translation pipeline + workbench
- Root: `/Users/alalapi/PycharmProjects/light_novel`

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
- [ ] `reports/latest-agent-report.json`
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
python3 scripts/tool_probe.py
python3 scripts/agent_gate.py --json
npm run check:tooling   # if code changed
```

## Acceptance criteria

- [ ] Scope limited to stated goal
- [ ] Gate pass or documented warnings
- [ ] `reports/latest-agent-report.json` updated
- [ ] No secrets in diff

## Return format

Codex reply should include:

1. Summary of changes
2. Gate/test commands run + results
3. Remaining P0/P1
4. Suggested next Cursor round ID from `docs/AGENT_ROADMAP.md`
