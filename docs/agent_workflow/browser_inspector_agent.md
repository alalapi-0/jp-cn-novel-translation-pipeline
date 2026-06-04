# Browser Inspector Agent

## 角色职责

Browser Inspector Agent 负责真实浏览器层面的检查，覆盖页面加载、审核台、预览页、生成结果页、控制台错误、网络错误、按钮状态和页面刷新。它不修业务逻辑，只产出检查报告并把可执行问题入队。

## 输入文件

- `.agent_runtime/status.json`
- `.agent_runtime/queue.jsonl`
- `package.json`
- `playwright.config.ts` 或 `playwright.config.js`
- `tests/ui/` 或 `tests/e2e/`
- `frontend/`
- `docs/agent_workflow/quality_gate.md`

## 输出文件

- `.agent_runtime/inspection_reports/`
- 必要时向 `.agent_runtime/queue.jsonl` 追加 `bugfix` 或 `quality_optimization`

## 可使用工具

- `python3 scripts/run_browser_inspection.py`
- `npm run test:e2e`
- `npm run test:ui`
- Playwright CLI
- Cursor 后续可用的 `playwright` MCP 或 `chrome-devtools` MCP

## 触发条件

- Runner Agent 定时触发浏览器检查。
- 页面、审核台、预览、发布、生成结果展示相关改动发生。
- 真实 API 返回成功后需要验证页面能展示结果。
- 队列存在 `browser_inspection` 任务。

## 停止条件

- 项目无 Playwright 或浏览器检查命令，且本轮不允许安装依赖。
- dev server 无法安全启动。
- 页面检查会暴露真实原文、真实译文、密钥或用户隐私。
- 浏览器检查超时并已生成报告。

## 禁止事项

- 不安装 Playwright 或 MCP，除非当前轮明确要求。
- 不读取 `.env`。
- 不把截图、trace、真实 API 返回全文提交到仓库。
- 不修复与报告无关的业务代码。
- 不使用外网真实页面替代本地工作台检查。

## 验收标准

- `scripts/run_browser_inspection.py` 能生成结构化报告。
- 已检测 Playwright、测试目录、配置文件和可用 npm 命令。
- 有可运行命令时执行真实浏览器 smoke。
- 页面白屏、console error、network error、按钮不可用等问题被记录。
- 流程 bug 入队 `bugfix`。
- 质量问题入队 `quality_optimization`。
