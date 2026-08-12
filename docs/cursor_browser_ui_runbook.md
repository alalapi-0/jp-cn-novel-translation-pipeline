# Cursor 浏览器 UI 推进 Runbook

本 runbook 用于配置与执行 Cursor Agent 的浏览器检查、Stitch 设计、UI 实现与回归验证。**不替代**业务代码规范；详见 `AGENTS.md`、`docs/testing/BROWSER_TESTING.md`。

---

## 1. Cursor 浏览器任务的基本原则

- **MCP server ready ≠ 当前 Agent 线程可用。** CLI 或 Settings 显示 ready，只说明 server 进程可启动，不代表当前对话能调用工具。
- **Settings 中启用 ≠ 旧对话能调用。** 已开启的 MCP 不会自动注入到批准前创建的旧 Agent 线程。
- **批准 MCP 后需要完全退出 Cursor 并重开仓库。** Reload Window 有时不够；完全 quit 再打开项目最可靠。
- **浏览器任务必须使用普通前台 Agent。** 在 Cursor Chat / Agent 主线程中执行，不要用后台轮询或 detached 模式。
- **禁止 Multitask / 后台子 Agent 执行浏览器控制任务。** 子 Agent 通常不继承 Workspace MCP 工具注册表。
- **浏览器任务开始前必须检查当前线程实际暴露的工具。** 在 system 提示或可用 tool 列表中确认 `browser_*`、`playwright`、`chrome-devtools` 等原生工具存在。
- **如果当前线程没有暴露目标工具，必须停止并输出 BLOCKED，不要继续假装执行。** 不得用 Read/Grep 推断页面状态替代真实浏览器检查。

---

## 2. 工具选择规则

### 普通本地 Web 项目 UI 优化

本项目（中日文互译 Workbench 静态前端）属于此类。优先使用：

| 工具 | 用途 |
|------|------|
| **stitch** | 生成 UI 设计依据（原型、screen、截图） |
| **chrome-devtools** | 检查页面、console、network、截图 |
| **playwright** | 跑 E2E 和稳定回归（`npm run test:ui` 或 MCP） |
| **filesystem** | 检查代码和产物是否真实写入磁盘 |
| **context7** | 查前端库与框架文档 |
| **github** | commit / push / issue / PR |

### 微信公众号已登录页面操作

**本项目不是微信项目，通常不适用。** 若未来有微信相关任务，规则如下：

只使用：

- **wechat-chrome-session**（接管已登录 Chrome 会话）

禁止使用：

- ordinary **chrome-devtools**
- **playwright**
- **browser_tabs**、**new_page**、**navigate_page**
- 任何会新开未登录浏览器的工具

### 真实页面 UI 优化

必须执行完整 before/after 清单：

1. 打开页面
2. 截图
3. 检查 console
4. 检查 network
5. 记录 before 状态
6. 修改 UI
7. 再打开页面
8. 截图
9. 检查 after 状态
10. 修复发现的问题

截图与 trace 写入 `artifacts/`，**不提交 Git**。

---

## 3. 标准 UI 优化流程

固定 14 步流程（每轮 UI 推进遵循）：

1. 读取 README / AGENTS / ROADMAP / `docs/design`
2. 启动项目（如 `npm run dev:frontend`）
3. 用 browser / chrome-devtools / playwright 打开页面
4. 保存 before screenshot
5. 读取 Stitch 设计文档或调用 Stitch MCP
6. 选择一个 UI 改造切片（每轮一个主要切片）
7. 修改代码
8. 重新打开页面
9. 检查 console / network
10. 检查响应式（窄屏 / 桌面）
11. 运行测试（`npm run test:ui` 或 `npm run test:py` 相关项）
12. 保存 after screenshot
13. 更新文档（设计 reviews、轮次记录）
14. 本地验证后默认保持未 stage；Round Prompt/edit/build 不授权 Git。commit 与 push 分别取得用户当前轮明确授权后才执行，push 失败重试需新授权

Prompt 模板见 `docs/prompts/CURSOR_UI_IMPLEMENTATION_PROMPT.md`。

---

## 4. 当前线程工具检查

如果用户要求使用某个 MCP，Agent **必须先确认「当前对话线程」是否暴露对应原生工具**。

**不要只依赖：**

- `cursor-agent mcp list`（CLI 层）
- Settings 中的 ready 状态
- `.cursor/mcp.json` 存在

**如果当前线程没有对应工具，输出：**

```
BLOCKED: MISSING_FROM_THREAD_TOOL_REGISTRY
```

并说明用户应：

1. 完全退出 Cursor
2. 重新打开仓库
3. 在 Settings → Tools & MCP 中确认工具 ready
4. 新建普通前台 Agent 对话
5. 禁用 Multitask
6. 重新执行任务

详细排查见 `docs/cursor_tool_registry_check.md`。

**CLI 检查（辅助，非线程注册表）：**

```bash
npm run check:cursor-mcp
# 或
bash scripts/check_cursor_mcp_status.sh
npm run check:mcp
npm run check:stitch
```

---

## 参考

- `docs/cursor_tool_registry_check.md`
- `docs/testing/BROWSER_TESTING.md`
- `docs/agent_skills/mcp_usage_skill.md`
- `.cursor/rules/cursor-browser-ui.mdc`
- `.cursor/rules/no-multitask-for-browser.mdc`
