# Agent Layer Roadmap

Incremental Tool-aware rounds (AL-xxx). Complements `docs/final_state_implementation_roadmap.md` and the FS-v2 task list.

> **历史、非执行性路线图（2026-06-09 已完成）：** 下列 AL 条目保留当时的目标、命令与依赖事实，但不再定义当前验证或授权。任何 `tool_probe`、`agent_gate`、`check:tooling`、报告写入或 Git 表述都必须服从 `AGENTS.md`、`project.yaml`、`docs/TOOL_USAGE_POLICY.md`、`docs/git_safe_cohort_delivery.md` 与 `scripts/run_tooling_checks.sh` 的现行规则：真实工作树仅运行 scoped targeted/read-only checks；完整 gate 仅可在不回写的一次性隔离副本运行；写入型 probe/inventory/report 同步不是隐式验证；Prompt 不能扩大 Git scope，approved Git-safe cohort 必须经 standing finalizer 远端闭环。

**Legend:** `web_search_needed: true` → check `docs/SEARCH_POLICY.md` first.

---

## Phase 0 — Repo facts

### AL-001 — Agent Layer 2.0 bootstrap
- **goal:** Tool inventory, policies, gate reports, cross-agent AGENTS.md
- **why_now:** Agents lack unified tool-aware entry
- **scope:** docs + yaml + probe scripts
- **likely_files:** AGENTS.md, agent_layer.yaml, docs/TOOL_*.md
- **tools_to_use:** shell, web_search, filesystem_mcp
- **tools_to_probe:** all MCP
- **web_search_needed:** true
- **commands_to_run:** tool_probe, agent_gate
- **acceptance_criteria:** all Layer 2.0 required files exist; gate ≤ warning
- **risks:** doc drift vs governance
- **fallback:** extend existing agent_tooling_strategy.md only
- **depends_on:** none

### AL-002 — Index docs navigation
- **goal:** Link Layer 2.0 docs from docs/index.md
- **why_now:** Discoverability
- **scope:** docs/index.md only
- **tools_to_use:** filesystem
- **web_search_needed:** false
- **commands:** agent_gate
- **acceptance:** index links AGENT_RUNBOOK, TOOL_USAGE_POLICY
- **depends_on:** AL-001

---

## Phase 1 — Tool probe

### AL-003 — MCP live probe automation
- **goal:** Extend tool_probe with optional MCP health (read-only)
- **scope:** scripts/tool_probe.py
- **tools_to_use:** shell, MCP
- **tools_to_probe:** github, context7, playwright
- **web_search_needed:** false
- **commands:** python3 scripts/tool_probe.py
- **acceptance:** probe_result not "deferred" for callable servers
- **depends_on:** AL-001

### AL-004 — agent_tools.yaml sync from probe
- **goal:** Script sync probe → yaml available fields
- **scope:** scripts/sync_agent_tools_from_probe.py (new)
- **tools_to_use:** shell
- **depends_on:** AL-003

### AL-005 — check:tooling includes tool_probe
- **goal:** run_tooling_checks.sh calls tool_probe
- **scope:** scripts/run_tooling_checks.sh
- **depends_on:** AL-003

---

## Phase 2 — Search & docs

### AL-006 — OpenRouter pricing refresh
- **goal:** Search official pricing; update RESEARCH_NOTES + api_provider_strategy pointers
- **web_search_needed:** true
- **tools:** web_search, context7
- **depends_on:** AL-001

### AL-007 — Playwright version pin doc
- **goal:** Document @playwright/test vs MCP version alignment
- **web_search_needed:** true
- **depends_on:** AL-001

### AL-008 — Cursor CLI capability note
- **goal:** Document cursor-agent install probe in TOOL_INVENTORY
- **web_search_needed:** true
- **depends_on:** AL-003

---

## Phase 3 — Rules

### AL-009 — Validate .cursor/rules coverage
- **goal:** Audit rules vs TOOL_USAGE_POLICY gaps
- **tools:** grep, Read
- **depends_on:** AL-001

### AL-010 — Agent skills stub for repo
- **goal:** Optional `.cursor/skills/` or docs pointer for translation QA skill
- **depends_on:** AL-009

---

## Phase 4 — Gate

### AL-011 — agent_gate strict mode for Layer files
- **goal:** FAIL if Layer 2.0 files missing under --strict-layer flag
- **scope:** scripts/agent_gate.py
- **depends_on:** AL-001

### AL-012 — JSON schema validate latest report
- **goal:** scripts/validate_agent_report.py
- **depends_on:** AL-001

---

## Phase 5 — Reports

### AL-013 — Report writer helper
- **goal:** scripts/write_agent_report.py template filler
- **depends_on:** AL-012

### AL-014 — Audit log rotation doc
- **goal:** AGENT_REPORTING retention policy
- **depends_on:** AL-013

---

## Phase 6 — User-view

### AL-015 — user_view_test with server spawn option
- **goal:** optional --spawn-dev-server flag (timeout bounded)
- **depends_on:** AL-001

### AL-016 — Browser inspection ↔ report link
- **goal:** run_browser_inspection writes user_view_test.json merge
- **depends_on:** AL-015

### AL-017 — Playwright smoke for issues page
- **goal:** one test covering issues.html API mock
- **tools:** playwright
- **depends_on:** AL-015

---

## Phase 7 — Core stability

### AL-018 — P0/P1 triage from gate JSON
- **goal:** map gate failures → severity in report helper
- **depends_on:** AL-011

### AL-019 — pytest for tool_probe + user_view_test
- **goal:** tests/test_tool_probe.py
- **depends_on:** AL-003

---

## Phase 8 — P0/P1 loop

### AL-020 — bugfix queue integration
- **goal:** agent.py enqueue from gate failures
- **depends_on:** AL-018

### AL-021 — Auto-suggest next AL round in report
- **goal:** read AGENT_ROADMAP depends_on graph
- **depends_on:** AL-013

---

## Phase 9 — Quality UI

### AL-022 — Workbench review flow user-view checklist
- **goal:** expand USER_VIEW_TESTING with review.html steps
- **tools:** browser
- **depends_on:** AL-016

### AL-023 — Quality review page regression
- **goal:** test:ui coverage for /issues
- **depends_on:** AL-017

---

## Phase 10 — Mock / real API separation

### AL-024 — Env flag documentation audit
- **goal:** AGENT_SAFETY ↔ README alignment
- **depends_on:** AL-006

### AL-025 — Gate forbids REAL_API in agent rounds
- **goal:** optional check env in agent_gate for governance mode
- **depends_on:** AL-024

---

## Phase 11 — Cost

### AL-026 — Cost ledger read-only inspector script
- **goal:** scripts/inspect_cost_ledger.py dry-run
- **depends_on:** AL-024

---

## Phase 12 — Codex handoff

### AL-027 — Sample filled CODEX_HANDOFF for Round 57
- **goal:** one real handoff example (no secrets)
- **depends_on:** AL-001

### AL-028 — .agents/skills translation-qa stub
- **goal:** Codex-compatible skill md
- **depends_on:** AL-010

---

## Phase 13 — Cursor incremental

### AL-029 — PROMPTS.md dry-run in CI
- **goal:** verify prompt templates reference current files
- **depends_on:** AL-001

### AL-030 — CI artifact upload gate_result.json
- **goal:** .github/workflows optional report artifact
- **depends_on:** AL-005

---

## Translation-specific (parallel track)

### AL-T01 — Chapter integrity checker
- **goal:** script validates segment JSON chapter bounds
- **tools:** shell, pytest
- **web_search_needed:** false

### AL-T02 — Terminology consistency report
- **goal:** glossary diff between runs
- **depends_on:** AL-T01

### AL-T03 — Resume checkpoint validation
- **goal:** micro_round_progress.json schema check
- **depends_on:** AL-T01

### AL-T04 — Human sampling interface doc
- **goal:** review.html operator runbook section
- **tools:** browser
- **depends_on:** AL-022

### AL-T05 — Model fallback matrix search
- **goal:** document provider fallback in RESEARCH_NOTES
- **web_search_needed:** true
- **depends_on:** AL-006

---

## Historical completion snapshot

All AL-001–AL-030 and AL-T01–T05 items were recorded as addressed in the 2026-06-09 snapshot. This statement is retained as history and does not authorize a push or make this file a current-round selector. Use the final-state authorities routed by `AGENTS.md` for current work; run `scripts/suggest_next_al_round.py` only when a separately scoped task explicitly owns that read/update workflow.
