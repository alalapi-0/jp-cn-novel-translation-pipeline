# 浏览器测试说明

本项目前端为静态 Workbench（`frontend/`），由 `scripts/serve_frontend.py` 提供本地服务（默认 **5174**）。

## 原则

- **不得** 仅凭读代码宣称 UI 完成
- 页面相关任务必须使用 **真实浏览器** 验证

## 工具

| 工具 | 入口 |
|------|------|
| Playwright MCP | Cursor MCP `playwright` |
| chrome-devtools MCP | Cursor MCP `chrome-devtools` |
| Playwright CLI | `npm run test:ui` |
| 检查脚本 | `python3 scripts/run_browser_inspection.py` |

## 最低验收（UI 任务）

1. 页面可加载（非 404/空白）
2. 核心路由与导航存在（index / review / export）
3. Console 无未解释的严重错误
4. 关键 API 请求路径可走通或 documented skip
5. 失败时截图/trace 写入 `artifacts/`（**不提交 Git**）

## 本地启动

```bash
npm run dev:frontend
# http://127.0.0.1:5174/
```

## 与 Stitch 设计的关系

1. Stitch 产出设计参考 → `docs/design/stitch/`
2. Cursor 实现 `frontend/` 变更
3. 本节的浏览器工具做 **实现后** 验收
4. 可选在 `docs/design/stitch/reviews/` 附实现截图对比

## 与多 Agent 分工

- **browser_inspector_agent**：周期性或队列触发的页面检查
- **bugfix_agent**：修复检查发现的流程/显示 bug
- 见 `docs/agent_workflow/browser_inspector_agent.md`

## 版本对齐

`@playwright/test`（CLI E2E）与 `@playwright/mcp`（Agent MCP）**独立版本** — 详见 [`PLAYWRIGHT_VERSION_ALIGNMENT.md`](PLAYWRIGHT_VERSION_ALIGNMENT.md)。

## Issues 页回归 (AL-017 / AL-023)

- Spec: `tests/ui/issues.spec.ts`（fixture 报告、console 无错误）
- 一并覆盖：`workbench.spec.ts` 中 issues 相关用例
- 运行：`npm run test:ui -- tests/ui/issues.spec.ts`

## 参考

- `tests/ui/workbench.spec.ts`
- `tests/ui/issues.spec.ts`
- `docs/mcp_playwright_setup_plan.md`
- `docs/testing/PLAYWRIGHT_VERSION_ALIGNMENT.md`
- `.cursor/rules/mcp-agent-tools.mdc`
