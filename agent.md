# Agent 快捷入口（agent.md）

与 `AGENTS.md` 互补的简短指引。权威顺序仍以 `governance/repo_protocol_standard.yaml` 为准。

## UI / 设计任务

1. 读 `docs/design/DESIGN.md` 与 `docs/design/stitch/UI_TASKS.md`
2. 有 `STITCH_API_KEY` 时用 **stitch** MCP 生成原型
3. 导出到 `docs/design/stitch/exports/` 与 `screenshots/`
4. Cursor 拆分任务落地 `frontend/`
5. **Playwright / chrome-devtools** 验收

## Stitch Design MCP

- **设计输入**：Stitch → `docs/design/stitch/`
- **实现**：Cursor Agent → `frontend/assets/`
- **用户视角测试**：Codex 只报问题，不改代码
- **禁止**：无审查覆盖业务代码；提交 API Key

## MCP 一览

见 `docs/mcp/WORKSPACE_MCP_SERVERS.md`：`chrome-devtools`、`context7`、`filesystem`、`github`、`playwright`、`stitch`。

```bash
npm run check:mcp
npm run check:stitch
```

## 测试

- 浏览器：`docs/testing/BROWSER_TESTING.md`
- 真实 API：`docs/testing/REAL_API_TESTING.md`
- 用户视角：`docs/testing/USER_PERSPECTIVE_TESTING.md`

## Cursor Browser UI Workflow

1. 使用 **普通前台 Agent**；禁止 Multitask 控制浏览器。
2. 开始前确认当前线程暴露 chrome-devtools / playwright / browser 工具；缺失则 `BLOCKED: MISSING_FROM_THREAD_TOOL_REGISTRY`。
3. before/after 真实页面检查 + console/network + 测试。
4. Stitch → 设计；chrome-devtools → 调试；playwright → 回归。
5. Runbook：`docs/cursor_browser_ui_runbook.md`；Prompt：`docs/prompts/CURSOR_UI_IMPLEMENTATION_PROMPT.md`。
6. 检查：`npm run check:cursor-mcp`。

完整 Agent 协议见 **`AGENTS.md`**。
