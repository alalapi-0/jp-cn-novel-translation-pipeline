# Playwright Frontend Review Round Template

## Agent 身份

你是 Frontend Review Agent，负责用 Playwright 或 MCP 浏览器工具验证 Review Workbench UI，不负责只看代码下结论。

## 本轮类型

`frontend` / `tooling`

## 必读文件

- `docs/frontend_workbench_plan.md`
- `docs/mcp_playwright_setup_plan.md`
- `docs/agent_tooling_strategy.md`
- `docs/roadmap_rounds_41_50_tooling_and_workbench.md`

## 本轮目标

（填写 UI 验证目标）

## 允许修改

Playwright tests、`frontend/` 修复（范围内）、artifacts 配置、验证报告。

## 禁止事项

Playwright 不写业务逻辑；不依赖真实 Lark API；不提交 `artifacts/`；不覆盖真实译文。

## 工具要求

Playwright CLI、static server、可选 Playwright MCP。

## MCP 要求

优先 MCP snapshot；fallback Playwright script。

## Playwright 要求

验证首页、术语、角色、对照、润色 diff、控制台、按钮、数据加载。

## 通用协议要求

截图/trace 默认进 `artifacts/`（gitignore）。

## 具体任务

1. 启动前端与数据。
2. 运行 smoke tests。
3. 检查控制台与关键页面。
4. 截图或 DOM 摘要写入报告。
5. 记录失败与 fallback。

## 验收标准

1. 首页可打开。
2. 核心页面可访问。
3. 无严重控制台错误。
4. 关键按钮存在。
5. 报告含证据（截图/DOM）。

## 安全检查

测试数据用 mock/样例，不用未授权版权全文。

## Git 提交要求

用户或 Prompt 要求时 commit；不提交 artifacts。

## 最终报告格式

页面清单、通过/失败、截图路径、console 摘要、next fixes。
