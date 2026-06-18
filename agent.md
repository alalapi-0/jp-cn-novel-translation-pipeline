# Agent 快捷入口（agent.md）

与 `AGENTS.md` 互补的简短指引。跨仓库安全规则见 `governance/repo_protocol_standard.yaml`；项目最终目标以 `docs/product_final_state_spec.md` 为最高锚点。

## 当前推进入口

1. 读 `docs/product_final_state_spec.md`
2. 读 `docs/final_state_implementation_roadmap.md`
3. 读 `docs/final_state_round_task_list.md`
4. 运行 `python3 scripts/local_scheduler_status.py --json`
5. 按首个可执行未完成轮推进，不从旧 Round 00–57 文档重新推导路线

2026-06-11 治理复核时：Phase A 连续完成 355/613 章，下一安全 micro round 为 `D-MR-052`（356–358 章）；S1 调度器与 S3 资产层已完成，S4 UI 基座未开始。

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

## Workspace Tooling Standard

本项目的通用 MCP 工具（chrome-devtools / playwright / context7 / github / stitch）与跨项目分工规则
遵循工作区级标准，详见：
`/Users/alalapi/PycharmProjects/.agent_workspace/docs/AGENT_TOOLING_STANDARD.md`

本项目专属、不可全局化的工具（如有）：见本文件 MCP 配置章节。
