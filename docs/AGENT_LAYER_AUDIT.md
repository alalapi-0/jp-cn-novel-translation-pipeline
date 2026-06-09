# Agent Layer 2.0 Audit

Date: 2026-06-09  
Round: Tool-aware Agent Layer bootstrap (AL-001)

## Scope

Integrate Tool-aware Agent Layer without replacing governance Round 41–57 artifacts.

## Existing assets reused

| Asset | Status |
|-------|--------|
| `AGENTS.md` | Extended, not replaced |
| `governance/repo_protocol_standard.yaml` | Unchanged authority |
| `scripts/agent_gate.py` | Extended with Layer 2.0 checks + `gate_result.json` |
| `scripts/agent.py` | Unchanged |
| `.cursor/rules/*.mdc` | Extended with agent-layer rules |
| `docs/agent_tooling_strategy.md` | Referenced by TOOL_USAGE_POLICY |
| `docs/roadmap_rounds_*` | Legacy pipeline roadmap preserved |
| `npm run check:tooling` | Still valid aggregate gate |

## New Layer 2.0 assets

| File | Purpose |
|------|---------|
| `agent_layer.yaml` | Machine config |
| `agent_tools.yaml` | Tool inventory + policies |
| `docs/AGENT_ROADMAP.md` | 30 incremental agent rounds |
| `docs/TOOL_*` | Inventory + usage |
| `docs/SEARCH_POLICY.md` | Search when/how |
| `docs/RESEARCH_NOTES.md` | Search log |
| `scripts/tool_probe.py` | Probe runner |
| `scripts/user_view_test.py` | User-view smoke |
| `schemas/agent_round_report.schema.json` | Report schema |
| `reports/*` | Machine reports |

## Gaps / next

- Wire `check:tooling` to include `tool_probe.py` (AL-005)
- Populate `.agents/skills/` if Codex skills needed (AL-028)
- CI publish `reports/gate_result.json` as artifact optional (AL-030)

## Conflicts avoided

- Did not duplicate `governance/agent_policy.yaml` — cross-linked
- Did not remove MCP rules — complementary
- Reports at repo `reports/` vs `docs/reports/` — both kept; gate markdown stays in `docs/reports/`
