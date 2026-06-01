# Round 44：Playwright Smoke Test Setup

## Agent 身份

你是 Playwright Setup Agent，负责为未来 Review Workbench 建立最小 Playwright smoke 测试框架。

## 当前轮次

Round 44

## 本轮类型

`frontend` / `tooling`

## 背景

Round 36–40 应已完成前端 MVP（若未完成，本轮仅搭框架与 skip 测试）。Agent 不能只看代码验证 UI，需要 Playwright 基础设施。

## 必读文件

- `docs/mcp_playwright_setup_plan.md`
- `docs/frontend_workbench_plan.md`
- `docs/agent_tooling_strategy.md`
- `docs/roadmap_rounds_41_50_tooling_and_workbench.md`

## 允许修改

`package.json`（若采用 Node 路线）、`playwright.config.ts` 或等效、`tests/ui/`、`artifacts/` gitignore、相关文档。

## 禁止修改

不在 Playwright 测试中写业务翻译逻辑；不提交 `artifacts/`；不依赖真实 Lark API。

## 工具要求

Node.js + npm 或 Python Playwright（二选一，文档说明选择）。

## MCP / Playwright 要求

本轮安装 Playwright CLI + Chromium；MCP 留给 Round 45。

## 通用协议要求

screenshots/traces 默认 `artifacts/`；`artifacts/` 在 `.gitignore`。

## 具体任务

1. 选择 Node 或 Python Playwright 路线并文档化。
2. 安装 playwright 与 chromium（`npx playwright install chromium`）。
3. 创建最小 smoke spec：打开 frontend 首页（或 placeholder）。
4. 配置 baseURL 与 static server 启动说明。
5. 添加 npm/pnpm script 或 Makefile target 运行 smoke。
6. 确保 artifacts 目录 gitignore。
7. 若前端未就绪，测试 marked skip 并文档说明前置 Round。
8. 更新 round_state。

## 验收标准

1. Playwright 可本地运行（或 skip 有 documented reason）。
2. 至少 1 个 spec 文件存在。
3. artifacts 不进入 git diff。
4. 文档含安装与运行命令。
5. 控制台严重错误可在 spec 中断言（若 UI 存在）。
6. 不调用真实翻译 API。
7. agent_gate 仍 PASS/WARNING。

## 安全检查

测试用 mock/样例 URL；不用未授权版权全文。

## Git 提交建议

`feat: add playwright smoke test scaffold`

## 最终报告格式

playwright_route_chosen、commands、spec_list、skip_reasons_if_any、next_round_45。
