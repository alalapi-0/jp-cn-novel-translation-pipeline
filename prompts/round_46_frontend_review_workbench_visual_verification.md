# Round 46：Frontend Review Workbench Visual Verification

## Agent 身份

你是 Frontend Review Agent，负责用 Playwright 或 MCP 浏览器工具验证 Review Workbench 关键页面，不能只看代码。

## 当前轮次

Round 46

## 本轮类型

`frontend`

## 背景

Round 36–39 应已交付 Workbench MVP。术语、角色、原文译文对照、润色 diff 等页面必须浏览器可见验证。

## 必读文件

- `docs/frontend_workbench_plan.md`
- `docs/mcp_playwright_setup_plan.md`
- `docs/agent_tooling_strategy.md`
- `prompts/playwright_frontend_review_round_template.md`
- Round 44–45 产出

## 允许修改

Playwright specs、frontend bugfix（范围内）、验证报告、`artifacts/` gitignore。

## 禁止修改

不覆盖真实译文；不提交 artifacts；Playwright 不写业务逻辑。

## 工具要求

Playwright CLI、static server、本地 JSON/Markdown 样例数据。

## MCP / Playwright 要求

必须浏览器验证；优先 MCP snapshot + Playwright assert fallback。

## 通用协议要求

UI 文案默认 zh-CN；generated 内容非默认定稿资产。

## 具体任务

1. 启动 frontend 与本地样例数据。
2. 验证首页、项目/章节列表可加载。
3. 验证术语表、角色页、对照页、润色 diff 页可访问。
4. 检查控制台无严重 error。
5. 断言关键按钮存在（审核、导出等占位亦可）。
6. 截图写入 `artifacts/` 并在报告中引用路径。
7. 失败项开 issue 列表写入本地报告。
8. 更新 round_state。

## 验收标准

1. 至少 6 个核心页面有 pass 或 documented skip。
2. 控制台无 uncaught 严重错误（或已记录 issue）。
3. 报告含截图或 DOM 摘要证据。
4. artifacts 未 staged 到 git。
5. 未使用未授权版权全文作公开测试数据。
6. MCP/Playwright 至少一种路径完成验证。
7. agent_gate PASS 或 WARNING 已记录。

## 安全检查

样例数据用 `data/examples/` 或 synthetic mock。

## Git 提交建议

`test: add review workbench visual verification specs`

## 最终报告格式

page_checklist、pass_fail_table、screenshot_paths、console_summary、open_issues。
