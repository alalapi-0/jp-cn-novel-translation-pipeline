# Agent Prompt Templates

Copy-paste prompts for Tool-aware rounds. Each requires: read AGENTS.md, agent_tools.yaml, latest-agent-report; tool plan; small scope; gate; report; no real API/publish; no auto push.

> **FS 连续推进轮（2026-06-11 起的主线模式）**：使用 `docs/prompts/CONTINUOUS_FS_ADVANCE_PROMPT.md`。
> 该 Prompt 由用户授权每轮 commit + push main 与按轮次边界使用真实 API，优先级规则见其正文；与下方旧模板冲突时以其为准。

---

## 1. Cursor tool probe round

```
You are running AL-003 tool probe round for light_novel.

Read first: AGENTS.md, agent_tools.yaml, reports/latest-agent-report.json, docs/TOOL_USAGE_POLICY.md.

Tasks:
1. Run python3 scripts/tool_probe.py and review reports/tool_probe_report.json
2. For each MCP in .cursor/mcp.json, run one read-only safe probe; record callable_now
3. Update docs/TOOL_INVENTORY.md and agent_tools.yaml if changed
4. Run python3 scripts/agent_gate.py --json
5. Write reports/latest-agent-report.json with tools_used / tools_not_used

Constraints: no real API, no publish, no commit unless asked.
```

---

## 2. Cursor small implementation round

```
You are running a small implementation round (one AL-xxx item from docs/AGENT_ROADMAP.md).

Read first: AGENTS.md, agent_layer.yaml, agent_tools.yaml, reports/latest-agent-report.json.

Before coding:
- Confirm tool probe status
- List tools you will use and why
- Confirm web_search_needed flag for this AL round

Implement ONE scoped change only. Run npm run check:tooling if code touched.
Write reports/latest-agent-report.json and append agent_audit_log.jsonl.
```

---

## 3. Cursor user-view test round

```
User-view test round for light_novel workbench.

Read: docs/USER_VIEW_TESTING.md, docs/cursor_browser_ui_runbook.md.

Start npm run dev:frontend (or verify running).
Use Browser/Playwright MCP: home, review, issues — snapshot, console, network.
Run python3 scripts/user_view_test.py and npm run test:ui if applicable.

Record before/after in artifacts/ (not committed).
Update latest-agent-report with browser tool usage.
No Multitask for browser.
```

---

## 4. Cursor P0/P1 fix round

```
P0/P1 fix round — clear blockers before P2/P3.

Read latest-agent-report.json severity_summary and reports/gate_result.json.

Fix highest severity first. Re-run agent_gate and relevant tests.
Do not delete tests to pass. Document remaining issues in report.
```

---

## 5. Codex high-value handoff prompt

```
Codex session for light_novel — high-value task only.

Read: AGENTS.md, agent_layer.yaml, agent_tools.yaml, docs/CODEX_HANDOFF.md (filled), reports/latest-agent-report.json.

Task: [from handoff Current goal]
Constraints: one round, no real API, no publish, run python3 scripts/agent_gate.py --json.

Return: summary, gate result, updated report fields, next Cursor AL round ID.
```

---

## 6. Codex review prompt

```
Review-only Codex round. No feature work.

Read handoff + git diff scope. Focus on correctness, safety, secrets, test gaps.
Output structured review: P0/P1/P2 findings, suggested fixes for Cursor.
Do not push or commit.
```

---

## 7. Web research prompt

```
Web research round per docs/SEARCH_POLICY.md.

Query: [specific official topic]
Log each query in docs/RESEARCH_NOTES.md with source type and uncertainty.
Encode actionable findings into repo docs (minimal diff).
No code changes unless research requires doc correction.
Update latest-agent-report web_research section.
```

---

## 8. MCP probe prompt

```
MCP probe round — read-only only.

Read .cursor/mcp.json and docs/TOOL_INVENTORY.md.
For each server: safe_probe_command, probe_result, fallback.
Update reports/tool_probe_report.json and agent_tools.yaml callable_now fields.
Never call write/publish/delete MCP methods.
Generate latest-agent-report mode=tool-probe.
```

---

## Legacy prompts

Pipeline rounds: `prompts/round_XX_*.md`, `prompts/agent_gate_round_template.md`.

UI: `docs/prompts/CURSOR_UI_IMPLEMENTATION_PROMPT.md`.
