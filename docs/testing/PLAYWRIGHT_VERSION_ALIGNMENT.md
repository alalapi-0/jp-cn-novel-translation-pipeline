# Playwright 版本对齐说明

Date: 2026-06-09 (AL-007)  
Scope: `@playwright/test`（E2E CLI）与 `@playwright/mcp`（Cursor MCP）的版本策略

---

## 本仓库当前版本（2026-06-09）

| 组件 | 位置 | 版本 / 策略 |
|------|------|-------------|
| `@playwright/test` | `package.json` devDependencies | `^1.60.0`（锁到 1.60.0） |
| `playwright`（CLI 核心） | 由 `@playwright/test` 依赖 | 1.60.0 |
| `@playwright/mcp` | `.cursor/mcp.json` → `npx -y @playwright/mcp@latest` | npm 最新（例：0.0.75） |
| `npx playwright --version` | 工作区 CLI | 1.60.0 |
| 浏览器二进制 | 本地 `~/.cache/ms-playwright` | 由 `npx playwright install` 安装，对应工作区 1.60.0 |

**结论：** 两套包 **独立版本号**，不要求数字相同；E2E 以 `package.json` 为准，MCP 以官方推荐的 `@latest` 为准。

---

## 为什么不对齐到同一 semver

1. **官方独立发布** — Playwright 团队说明 `@playwright/mcp` 与 `playwright` / `@playwright/test` 分开版本管理（[playwright-mcp#1091](https://github.com/microsoft/playwright-mcp/issues/1091)）。
2. **MCP 可能依赖 alpha core** — `@playwright/mcp` 有时使用实验性 API，内部 bundled 的 `playwright-core` 可与工作区稳定版不同（[playwright-mcp#917](https://github.com/microsoft/playwright-mcp/issues/917)）。
3. **官方 MCP 配置** — [Playwright MCP 文档](https://playwright.dev/docs/getting-started-mcp) 推荐 `npx @playwright/mcp@latest`，而非与 `@playwright/test` 同号 pin。
4. **职责分离**
   - `@playwright/test` + `npm run test:ui` → **可复现 CI / 回归**
   - `@playwright/mcp` → **Agent 交互式浏览器**（snapshot、click、console）

---

## 本仓库策略

### Pin（锁定）

- **`@playwright/test`** 在 `package.json` 中显式 semver（当前 `^1.60.0`）。
- 升级时同步：`package-lock.json`、`npx playwright install`、跑 `npm run test:ui`。

### Float（浮动）

- **`.cursor/mcp.json`** 保持 `@playwright/mcp@latest`（与官方示例一致）。
- 不在 `package.json` 安装 `@playwright/mcp` — 避免与工作区 `playwright@1.60.x` 的 alpha/stable 冲突。

### 验收双轨

| 路径 | 命令 | 通过标准 |
|------|------|----------|
| CLI E2E | `npm run test:ui` | 全部 spec 绿 |
| MCP 探针 | `python3 scripts/tool_probe.py` | `playwright` server `callable_now=true` |
| 可选交互 | Cursor `playwright` MCP snapshot | 首页可 snapshot（非 gate 硬阻塞） |

MCP 不可用时不阻塞文档/后端轮次，但 **UI 实现轮** 须至少 CLI E2E 通过。

---

## 升级 `@playwright/test` 检查清单

1. 修改 `package.json` 中 `@playwright/test` 版本。
2. `npm install` 更新 lockfile。
3. `npx playwright install`（必要时 `--with-deps`）刷新浏览器二进制。
4. `npx playwright --version` 确认 CLI 版本。
5. `npm run test:ui` 全绿。
6. `python3 scripts/tool_probe.py --sync-docs` 刷新 `reports/tool_probe_report.json`。
7. 可选：Cursor 中 reload MCP，对 `http://127.0.0.1:5174/` 做一次 snapshot。

**不要** 为了对齐 MCP 而强行把 `@playwright/mcp` pin 到与 `@playwright/test` 相同数字 — 两者 semver 体系不同。

---

## 浏览器版本不匹配（troubleshooting）

症状：MCP 报找不到某 build 的 Chromium/Firefox，或 `browserType.launch` 失败。

| 步骤 | 操作 |
|------|------|
| 1 | `npx playwright --version` 确认工作区 CLI 版本 |
| 2 | `npx playwright install` 重装浏览器（对应 CLI 版本） |
| 3 | 仍失败 → `npx playwright install --force` |
| 4 | MCP 仍失败 → 用 `npm run test:ui` 或 `cursor-ide-browser` fallback |
| 5 | 记录于 `reports/latest-agent-report.json` → `remaining_issues` |

根因通常是 **MCP 进程 bundled 的 core** 与 **全局/工作区已装浏览器** 不一致；CLI 路径以工作区 `@playwright/test` 为准修复。

---

## 配置文件索引

| 文件 | 作用 |
|------|------|
| `package.json` | `@playwright/test` pin |
| `playwright.config.ts` | E2E baseURL、webServer、artifacts 输出 |
| `.cursor/mcp.json` | `@playwright/mcp@latest` launcher |
| `scripts/tool_probe.py` | 探测 `npx playwright --version` 与 MCP callable |
| `docs/USER_VIEW_TESTING.md` | 用户视角验收流程 |
| `docs/mcp_playwright_setup_plan.md` | MCP 安装与隔离总览 |

---

## 相关研究记录

见 `docs/RESEARCH_NOTES.md` → Query 6（AL-007）。
