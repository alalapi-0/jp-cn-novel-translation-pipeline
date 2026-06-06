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

完整 Agent 协议见 **`AGENTS.md`**。
