# Cursor Current Thread Tool Registry Check

本文档说明 **CLI / Settings 层的 MCP ready** 与 **当前 Agent 对话线程实际暴露的工具** 之间的差异，以及如何排查「server does not exist」类失败。

---

## 核心原则

1. **终端里的 MCP ready 只能说明 server 可用。** `cursor-agent mcp list` 或 Settings 绿灯只表示 MCP 进程可连接，不保证当前 Chat/Agent 线程已注册工具。
2. **当前 Agent 对话必须实际暴露工具。** Agent 只能在 system 提供的 tool 列表中调用工具；列表里没有则无法调用，无论配置多正确。
3. **Multitask 子 Agent 可能没有继承 Workspace MCP。** 后台子 Agent / Task 工具派生的会话常缺少 `playwright`、`chrome-devtools` 等浏览器工具。
4. **旧对话可能仍停留在批准前的工具注册表。** 用户在 Settings 批准 MCP 之前创建的对话，可能永久缺少新工具，直到新建对话或重启 Cursor。
5. **正确处理方式是完全重启 Cursor 并新开普通 Agent 对话。** 流程：Quit Cursor → 重开仓库 → Settings 确认 ready → **新建**普通前台 Agent → 禁用 Multitask → 重试任务。
6. **如果 server 名称带连字符导致路由问题，可以考虑增加 underscore alias。** 例如 `wechat-chrome-session` 与 `wechat_chrome_session`；若添加 alias，须在 `docs/cursor_browser_ui_runbook.md` 或本文件注明，且仅在项目需要时配置。

---

## 排查表

| 现象 | 可能原因 | 解决方法 |
| --------------------------------------------------------- | ----------------------------------- | -------------------------------------------- |
| cursor-agent mcp list 显示 ready，但对话中 server does not exist | 当前线程未继承工具注册表 | 重启 Cursor，新建普通 Agent |
| Multitask 中缺少 MCP 工具 | 子 Agent 未继承 Workspace MCP | 禁用 Multitask |
| wechat-chrome-session ready 但无法调用 | 工具未暴露给当前线程或名称路由问题 | 新建前台 Agent，必要时增加 wechat_chrome_session alias |
| playwright 打开的是未登录页面 | Playwright 新开隔离浏览器 | 微信任务改用 wechat-chrome-session |
| chrome-devtools 不能接管现有页面 | Chrome 未开启 remote debugging 或线程没有工具 | 启动 remote debugging 并重启 Cursor |

---

## Agent 自检步骤（每轮浏览器任务前）

1. 确认当前为 **普通前台 Agent**，非 Multitask / 后台子 Agent。
2. 在可用 tool 列表中查找目标 MCP 工具名（如 `browser_snapshot`、`browser_navigate`、Playwright 或 chrome-devtools 对应工具）。
3. 若缺失 → 输出 `BLOCKED: MISSING_FROM_THREAD_TOOL_REGISTRY`，停止浏览器相关步骤。
4. 可选：运行 `npm run check:cursor-mcp` 记录 CLI 状态（**不代表**线程已暴露工具）。

---

## 参考

- `docs/cursor_browser_ui_runbook.md`
- `scripts/check_cursor_mcp_status.sh`
- `.cursor/rules/no-multitask-for-browser.mdc`
