# Cursor UI 实现轮 Prompt 模板

复制下方整段到 **新的普通前台 Agent 对话**（禁用 Multitask），用于下一轮 UI 推进。

---

## 复制用 Prompt

```
你现在要在当前仓库执行一轮 UI 实现与浏览器验收。请严格遵守以下约束。

## 环境与工具

1. 必须使用 **普通前台 Agent**；**禁止 Multitask** 和后台子 Agent。
2. 任务开始前检查 **当前对话线程** 是否暴露浏览器 MCP 工具（chrome-devtools / playwright / Cursor 内置 browser）。
3. 若当前线程缺少目标工具，输出 `BLOCKED: MISSING_FROM_THREAD_TOOL_REGISTRY` 并停止，不要假装执行浏览器检查。
4. 参考 `docs/cursor_tool_registry_check.md` 与 `docs/cursor_browser_ui_runbook.md`。

## 工具分工

- **stitch**：设计输入（原型、screen）；产物入 `docs/design/stitch/`
- **chrome-devtools**：页面调试、console、network、截图
- **playwright**：E2E 回归（`npm run test:ui` 或 MCP）
- **filesystem**：确认文件真实写入
- **context7**：查前端库文档
- **github**：commit / push / PR（用户授权后）

本项目为本地 Web Workbench，**不得**使用 wechat-chrome-session。

## 阅读顺序

1. README.md、AGENTS.md
2. 当前 ROADMAP（`docs/final_state_implementation_roadmap.md` 与 `docs/final_state_round_task_list.md`）
3. `docs/design/DESIGN.md`、`docs/design/stitch/UI_TASKS.md`
4. 选定页面的现有实现（`frontend/`）

## 本轮范围

- 只选择 **一个 UI 改造切片**（例如单页、单组件、单交互流）
- **不改变业务逻辑**、API 契约或后端行为
- Stitch 导出 **不得** 无审查覆盖 `frontend/` 业务代码

## 执行流程（14 步）

1. 读取 README / AGENTS / ROADMAP / docs/design
2. 启动项目：`npm run dev:frontend`（默认 http://127.0.0.1:5174/）
3. 用 browser / chrome-devtools / playwright **打开目标页面**
4. 保存 **before** screenshot（`artifacts/`，不提交）
5. 读取 Stitch 设计或调用 Stitch MCP（无 Key 时用 PROMPT_TEMPLATES fallback）
6. 确认本轮 UI 切片
7. 修改 `frontend/` 代码（最小 diff）
8. **重新打开页面**
9. 检查 **console** 与 **network**
10. 检查 **响应式**（桌面 + 窄屏）
11. 运行测试：`npm run test:ui`（相关 grep）或项目规定的低成本测试
12. 保存 **after** screenshot
13. 更新文档（reviews / 轮次记录）
14. 用户要求时 **commit / push**（commit 前 `git diff` 确认无密钥/原文/译文）

## 验收标准

- 页面非空白、核心导航与操作可用
- Console 无未解释的严重错误
- Network 关键 API 路径可走通或 documented skip
- before/after 有记录
- 测试通过或清楚记录环境阻塞

## 阻塞处理

- MCP 未加载：记录 soft blocker，**不要**用读代码代替浏览器验收
- 缺浏览器工具：BLOCKED，指引用户重启 Cursor + 新建普通 Agent

现在开始：先自检当前线程工具，再按上述流程执行。
```

---

## 使用前检查清单

- [ ] 已禁用 Multitask
- [ ] 新建普通前台 Agent 对话（非旧对话）
- [ ] Settings → Tools & MCP 中相关 server 为 ready
- [ ] 必要时已完全退出并重开 Cursor
- [ ] `npm run check:cursor-mcp` 已运行（CLI 参考，非线程保证）

## 参考

- `docs/cursor_browser_ui_runbook.md`
- `docs/testing/BROWSER_TESTING.md`
- `docs/rounds/STITCH_UI_IMPLEMENTATION_ROUND.md`
