# Agent Rules Coverage Audit

Date: 2026-06-09  
Round: **AL-009**  
Authority: `docs/TOOL_USAGE_POLICY.md` (10 sections + translation mapping)  
Scope: `.cursor/rules/*.mdc` (10 files, all `alwaysApply: true`)

---

## Executive summary

| Status | Count | Meaning |
|--------|-------|---------|
| **Covered** | 8 / 11 policy areas | Explicit rule text or dedicated rule file |
| **Partial** | 2 | Referenced in policy; thin or split across files |
| **Gap** | 1 | No rule mention; docs-only in policy |

**Verdict:** Rules adequately enforce Layer 2.0 tool policy for Cursor. Remaining gaps are **P3** (translation-stage tool hints, Codex depth). No P0/P1 rule hole found.

Machine refresh: re-run this audit when `TOOL_USAGE_POLICY.md` or `.cursor/rules/` changes.

---

## Rule inventory

| File | Primary policy sections |
|------|-------------------------|
| `agent-layer.mdc` | §1 round start/end, §6 logging, §5 Codex cross-ref |
| `tool-usage.mdc` | §1–4, §6 summary; points to full policy |
| `search-policy.mdc` | §7 web search hygiene |
| `safety-gates.mdc` | §3 forbidden (tests/secrets), §9 real API defaults, §1 gate |
| `mcp-required.mdc` | §2 MCP servers, §4 partial fallbacks |
| `mcp-agent-tools.mdc` | §3 `.env`/filesystem scope, §4 GitHub fallback |
| `cursor-browser-ui.mdc` | §8 browser user-view, §3 Stitch overwrite |
| `user-view-testing.mdc` | §8 user-view, REAL_API/MOCK indicators |
| `no-multitask-for-browser.mdc` | §3 Multitask browser forbidden |
| `stitch-design-mcp.mdc` | §2 Stitch preferred path, §3 blind overwrite |

---

## Section-by-section mapping

### §1 Must-use by task

| Requirement | Rule coverage | Notes |
|-------------|---------------|-------|
| Round start reads (AGENTS, agent_tools, latest report) | `agent-layer.mdc` | Also lists agent_layer, TOOL_USAGE_POLICY, AGENT_RUNBOOK |
| Tool planning / tool_probe | `agent-layer.mdc` | `tool_probe.py` or report JSON |
| Code understanding (search, filesystem) | `tool-usage.mdc`, `mcp-agent-tools.mdc` | |
| Fresh facts (WebSearch / Context7) | `tool-usage.mdc`, `search-policy.mdc` | |
| UI change → browser + dev server | `cursor-browser-ui.mdc`, `user-view-testing.mdc` | |
| Deterministic validation (gate, check:tooling) | `agent-layer.mdc`, `safety-gates.mdc`, `tool-usage.mdc` | |
| Round end report + audit log | `agent-layer.mdc` | |

**Status:** Covered

### §2 Preferred tools

| Requirement | Rule coverage | Notes |
|-------------|---------------|-------|
| Context7 / WebSearch / browser / Stitch / GitHub / filesystem | Split across `tool-usage`, `mcp-required`, `stitch-design-mcp` | |
| E2E → `npm run test:ui` | `cursor-browser-ui.mdc`, `user-view-testing.mdc` | |
| Long refactor → Codex | `agent-layer.mdc` one-liner only | **Partial** — see §5 |

**Status:** Covered (Codex detail partial)

### §3 Forbidden / restricted

| Requirement | Rule coverage |
|-------------|---------------|
| Real API / publish default off | `safety-gates.mdc`, `tool-usage.mdc` |
| No `.env` read/print | `mcp-agent-tools.mdc`, `safety-gates.mdc` |
| No force push / auto PR | `tool-usage.mdc`, `safety-gates.mdc` (auto push) |
| No Multitask browser | `no-multitask-for-browser.mdc`, `tool-usage.mdc` |
| No Stitch blind overwrite | `stitch-design-mcp.mdc`, `cursor-browser-ui.mdc` |
| MCP filesystem scope | `mcp-agent-tools.mdc`, `mcp-required.mdc` |
| No delete failing tests | `safety-gates.mdc` |

**Status:** Covered

### §4 Fallback matrix

| Fallback | Rule coverage |
|----------|---------------|
| WebSearch unavailable | `search-policy.mdc` |
| Context7 → WebSearch | `search-policy.mdc` |
| Playwright MCP → test:ui | `mcp-required.mdc`, `cursor-browser-ui.mdc` |
| chrome-devtools → playwright / ide-browser | `mcp-required.mdc`, `no-multitask` runbook refs |
| GitHub MCP → git/gh | `mcp-agent-tools.mdc`, `mcp-required.mdc` |
| Stitch → design templates | **Partial** — policy only; added to `tool-usage.mdc` AL-009 |
| Codex → Cursor + handoff | **Partial** — `agent-layer.mdc` only |

**Status:** Partial → tightened in `tool-usage.mdc` (AL-009)

### §5 Cursor vs Codex

| Requirement | Rule coverage |
|-------------|---------------|
| Cursor primary | `agent-layer.mdc` |
| Codex secondary + handoff | `agent-layer.mdc` → `docs/CODEX_USAGE.md` |

**Status:** Partial (acceptable — Codex sessions read same AGENTS.md)

### §6 Avoid “configured but unused” MCP

| Requirement | Rule coverage |
|-------------|---------------|
| Log tools_used / tools_not_used | `agent-layer.mdc`, `tool-usage.mdc` |

**Status:** Covered

### §7 Web search hygiene

| Requirement | Rule coverage |
|-------------|---------------|
| Official sources, RESEARCH_NOTES | `search-policy.mdc` |

**Status:** Covered

### §8 Browser user-view

| Requirement | Rule coverage |
|-------------|---------------|
| dev:frontend, snapshot, console, artifacts | `cursor-browser-ui.mdc`, `user-view-testing.mdc` |

**Status:** Covered

### §9 Real API / publish guards

| Requirement | Rule coverage |
|-------------|---------------|
| allow_real_* defaults | `safety-gates.mdc` |
| Env vars REAL_API_TESTS_ENABLED, MAX_TEST_COST_USD | **Gap** → added to `safety-gates.mdc` AL-009 |
| Script pointers | Policy + README; rules cite AGENT_SAFETY |

**Status:** Partial → env var names added to rule (AL-009)

### §10 Tool usage logging

| Requirement | Rule coverage |
|-------------|---------------|
| latest-agent-report.json shape | `agent-layer.mdc` |
| agent_audit_log.jsonl | `agent-layer.mdc` |

**Status:** Covered

### §11 Project-specific (translation pipeline)

| Requirement | Rule coverage |
|-------------|---------------|
| Stage → tool mapping (ingest, draft, QA, terminology, agent.py) | **Gap** — policy only; pointer added to `tool-usage.mdc` AL-009 |

**Status:** Gap (P3 — operational detail stays in policy + AGENTS.md)

---

## Gap register (post AL-009 fixes)

| ID | Severity | Gap | Action |
|----|----------|-----|--------|
| G-01 | P3 | Translation pipeline stage table not duplicated in rules | Pointer in `tool-usage.mdc`; full table stays in policy |
| G-02 | P3 | Codex handoff workflow not in rules | `docs/CODEX_HANDOFF.md` + AL-027 |
| G-03 | P3 | Optional gate: fail if rules stale vs policy | AL-011 `--strict-layer` |
| G-04 | P3 | No rule for `cursor-agent` CLI vs IDE thread | Documented in TOOL_INVENTORY § I (AL-008); not a Cursor rule |

---

## Recommendations

1. **AL-010** — Translation QA skill stub — **done** → `.cursor/skills/translation-qa/`, `docs/agent_skills/translation_qa_skill.md`
2. **AL-011** — Optional `agent_gate.py --strict-layer` to require this audit file freshness.
3. Re-run this audit when adding MCP servers or new forbidden actions to policy.

---

## Verification commands

```bash
# List rules
ls .cursor/rules/*.mdc

# Cross-check policy sections referenced in rules
rg -l 'TOOL_USAGE_POLICY|agent_gate|tool_probe|Multitask|Stitch' .cursor/rules/

# Gate
python3 scripts/agent_gate.py --json
```

---

## Related

- `docs/TOOL_USAGE_POLICY.md`
- `docs/AGENT_LAYER_AUDIT.md` (AL-001 bootstrap)
- `docs/AGENT_ROADMAP.md` → AL-009, AL-010
