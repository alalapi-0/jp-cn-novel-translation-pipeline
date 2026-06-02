# MCP and Playwright Setup Plan

## 为什么本项目需要 Playwright / MCP

1. 未来会有前端 Review Workbench（见 `docs/frontend_workbench_plan.md`）。
2. Agent 需要能**打开页面检查**，而不是只看代码。
3. 需要检查术语库编辑页、原文译文对照页、润色 diff 页。
4. 需要检查浏览器控制台错误。
5. 截图或 DOM 检查可辅助判断 UI 状态。
6. Playwright 可作为前端 smoke test 自动化工具。
7. Playwright MCP 可让 Agent 更直接操作浏览器（Cursor 等环境）。

---

## 安装时机

**本轮（Governance Round 02）不安装。** 除非仓库已进入前端实现阶段并完成静态 MVP。

| 轮次 | 内容 |
|------|------|
| Round 36 | 前端信息架构落地（见 `docs/roadmap_rounds_00_40.md`） |
| Round 37 | 前端静态 MVP |
| Round 38 | 前端与本地数据连接 |
| Round 39 | 前端编辑能力 MVP |
| Round 40 | 完整短篇闭环验证 |
| Round 44 | Playwright Smoke Test Setup |
| Round 45 | Playwright MCP 接入与验证 |
| Round 46 | Review Workbench 浏览器自动化验证 |

---

## Playwright 基础安装方案

### Node 路线（前端为 React/Vite 时优先）

```bash
npm init -y
npm install -D playwright
npx playwright install chromium
```

### Python 路线（脚本以 Python 为主时可选）

```bash
pip install playwright
python -m playwright install chromium
```

**选择标准：**

- 前端是 Node/React/Vite → 优先 Node Playwright
- 后端与脚本主要是 Python → 可用 Python Playwright
- 不要同时乱装两套，除非文档说明原因

**产物目录：** 截图、trace、报告默认写入 `artifacts/`（不提交 Git）。

---

## Playwright 验证目标

未来至少验证：

1. 前端首页可打开
2. 项目列表可显示
3. 章节列表可显示
4. 术语表页面可显示
5. 角色页面可显示
6. 原文译文对照页面可显示
7. 润色对比页面可显示
8. 控制台无严重报错
9. 页面核心按钮存在
10. 本地数据加载成功

---

## MCP 安装路线

不要假设所有环境支持同一 MCP。可替换路线：

### Option A: Cursor 内置 MCP 配置

在 Cursor MCP 设置中启用 browser / playwright 类 MCP（若可用）。验证：Agent 能否 snapshot 与 click。

### Option B: Claude Desktop MCP 配置

在 Claude Desktop `claude_desktop_config.json` 中添加 MCP server。验证：列出 tools 并执行 noop 检查。

### Option C: Codex / 本地 Agent MCP 配置

按本地 Agent 文档配置 MCP。验证：最小 tool call 成功。

### Option D: 不使用 MCP，Playwright 脚本 fallback

```bash
npx playwright test tests/ui/smoke.spec.ts
npm run test:ui
```

**规则：**

1. 先确认当前 Agent 环境是否支持 MCP
2. 再安装最小必要 MCP
3. 不要为了工具而工具
4. 每个 MCP 都要有验证步骤
5. MCP 失败不能阻塞整个项目，除非当前轮目标依赖它

---

## MCP 安全规则

1. 不允许 MCP 输出 API Key
2. 不允许 MCP 读取 `.env` 后展示
3. 不允许 MCP 自动公开发布译文
4. 不允许 MCP 删除真实原文
5. 不允许 MCP 覆盖已完成译文
6. 不允许 MCP 绕过 Git 审查
7. 不允许 MCP 在没有用户明确要求时执行外部发布动作

---

## 验证清单（Round 45 执行）

- [x] Playwright CLI 可运行（`npm run test:ui`，3 passed，2026-06-02）
- [x] Chromium 已安装（Round 44）
- [x] 至少 1 个 smoke test 通过（homepage / review / console）
- [x] MCP（若启用）可 snapshot 首页（`cursor-ide-browser` → `index.html`）
- [x] `artifacts/` 在 `.gitignore` 中
- [x] 测试不依赖真实 Lark/API（dry-run + mock JSON）

详细 10 项清单见 [`docs/mcp_verification_checklist.md`](mcp_verification_checklist.md)。

---

## Round 45 最小 MCP 配置与验证步骤

### Workspace MCP（`.cursor/mcp.json`）

已声明 5 个 server：`chrome-devtools`、`context7`、`playwright`、`filesystem`、`github`。验证：

```bash
npm run check:mcp
```

修改 `mcp.json` 后需在 Cursor **Reload Window** 或重启 Cursor。

### Cursor IDE Browser（Option A，本轮实测）

1. 启动前端：`npm run dev:frontend`（默认 `http://127.0.0.1:5174`）
2. MCP：`browser_navigate` → `http://127.0.0.1:5174/index.html`
3. MCP：`browser_snapshot`（navigate 常附带 snapshot）
4. 可选：`browser_navigate` → `review.html`；`browser_click` 需 snapshot 中的 `ref`
5. 操作顺序备忘：navigate →（lock）→ snapshot → click → unlock；见 `mcp_verification_checklist.md`

### Playwright CLI Fallback（Option D）

```bash
npm run test:ui
npm run test:ui:headed   # 本地 headed 调试
```

MCP 失败时记 **WARNING**，不阻塞 Round 45/46，只要 CLI 通过。

---

## Round 46 页面对齐（术语 / 对照 / diff）

| `frontend_workbench_plan.md` 页面 | 当前静态文件 | Round 45 MCP/CLI | Round 46 目标 |
|-----------------------------------|--------------|------------------|---------------|
| Project Home | `frontend/index.html` | ✓ snapshot + smoke | 保持回归 |
| Side-by-side Review | `frontend/review.html` | ✓ snapshot + smoke | 控制台 error 扫描 |
| Glossary Editor | 未单独 HTML | — skip | snapshot 或扩路由 + spec |
| Character Sheet | 未单独 HTML | — skip | 同上 |
| Polish Diff | 未单独 HTML | — skip | 同上 |
| Chapter Manager | mock 于首页卡片 | 部分（章节数文案） | 列表导航 spec |

Round 46 Prompt：`prompts/round_46_frontend_review_workbench_visual_verification.md`。最低门槛：**CLI smoke 全绿**；MCP 为增强路径（至少 6 页 pass 或 documented skip）。

---

## 实测结果（Round 45，2026-06-02）

| 检查 | 结果 |
|------|------|
| `check:mcp` | PASS（5 servers） |
| `cursor-ide-browser` 首页 snapshot | PASS（「翻译工作台」、`apiMode=dry-run`） |
| `cursor-ide-browser` 对照页 snapshot | PASS（`review.html`，审核按钮可见） |
| `npm run test:ui` | PASS（3/3） |
| `agent_gate` | PASS |
| `check:tooling` | PASS（含 pytest 9） |
| `.venv/bin/pytest` | PASS（9） |

报告全文：`docs/reports/mcp_playwright_validation_report.md`。

**Warnings（非硬阻塞）：**

- Workspace `@playwright/mcp` 未在本轮单独调用 tool；已用 `cursor-ide-browser` 满足 snapshot 验收。
- `browser_click` 首页「进入对照审核」未触发 URL 变更；Round 46 对导航链可用 `browser_navigate` 或修 href。

---

## Fallback 矩阵

| 失败场景 | Fallback |
|----------|----------|
| MCP 不可用 | Playwright CLI 脚本 |
| Playwright 未安装 | 静态 server + curl + 人工截图 |
| 前端未启动 | 硬阻塞（Round 46）；软阻塞（Round 44 仅搭框架） |
| 浏览器 CI 无头失败 | 本地 headed 调试并记录 trace |
