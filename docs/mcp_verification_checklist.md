# MCP 浏览器验证清单（Round 45）

Agent 在每轮涉及 UI 的任务前可快速执行。完整背景见 [`mcp_playwright_setup_plan.md`](mcp_playwright_setup_plan.md)。

## 前置

1. 确认 `.cursor/mcp.json` 有效：`npm run check:mcp`
2. 启动前端（端口冲突时改用 5175+）：`npm run dev:frontend` 或 `python3 scripts/serve_frontend.py --port 5174`

## 清单（≤10 项）

| # | 检查项 | 通过标准 |
|---|--------|----------|
| 1 | MCP 配置 | `check:mcp` 列出 chrome-devtools、playwright、filesystem 等且无 secrets |
| 2 | Browser MCP 可用 | `cursor-ide-browser` 或 workspace `playwright` MCP 在 Cursor Settings → MCP 为已加载 |
| 3 | 首页 snapshot | `browser_navigate` → `http://127.0.0.1:5174/index.html`，snapshot 含标题「翻译工作台」与 `apiMode=dry-run` |
| 4 | 对照页 snapshot | 打开 `review.html`，snapshot 含「Side-by-side Translation Review」与审核按钮 |
| 5 | Playwright CLI | `npm run test:ui` 全部通过（3 specs） |
| 6 | Chromium | Playwright 已安装（Round 44）；失败时 `npx playwright install chromium` |
| 7 | artifacts 隔离 | `artifacts/` 在 `.gitignore`，截图/trace 不 stage |
| 8 | 无真实 API | 测试与 MCP 仅 dry-run / mock JSON，不读 `.env` |
| 9 | MCP 安全 7 条 | 不输出密钥、不自动发布译文、不删原文、不绕过 Git（见 setup plan） |
| 10 | Fallback 就绪 | MCP 失败时改用 `npm run test:ui`；记录 WARNING，非 Round 45/46 硬阻塞 |

## 推荐 MCP 操作顺序（Cursor IDE Browser）

1. `browser_navigate` 目标 URL（后台自动化勿设 `position`）
2. 需要长操作时 `browser_lock` → 交互 → `unlock`
3. `browser_snapshot` 获取 ref
4. `browser_click` / `browser_fill` 使用 snapshot 中的 `ref`
5. 视觉证据：`take_screenshot_afterwards: true` 或 CLI trace 至 `artifacts/`

## CLI Fallback（MCP 不可用时）

```bash
npm run dev:frontend   # 另开终端，或依赖 playwright webServer
npm run test:ui
npm run test:ui:headed # 本地调试
```

## Round 46 前置

- **必须**：CLI smoke 通过（上表 #5）
- **增强**：MCP snapshot 覆盖首页 + 对照页；Round 46 扩展至术语/角色/diff 页（见 setup plan「Round 46 页面对齐」）
