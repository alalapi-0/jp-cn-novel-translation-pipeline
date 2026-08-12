# MCP / Browser Tools Runbook for light_novel

本 Runbook 用于指导后续 Agent 在 `light_novel` 项目中稳定使用 MCP、Playwright、Chrome DevTools、GitHub、Context7、Stitch 等工具。

**权威顺序：** 本文件为浏览器/MCP 工具操作细则；UI 实现流程另见 `docs/cursor_browser_ui_runbook.md`；隔离策略见 `docs/mcp_isolation_strategy_light_novel.md`。

---

## 1. Runbook 目的

### 要解决的问题

1. 避免 MCP 已配置但 Agent 不使用。
2. 避免 chrome-devtools profile 冲突。
3. 避免多个项目共用默认 Chrome profile。
4. 避免端口冲突导致前端检查失败。
5. 明确每个工具何时使用。
6. 明确失败时 fallback。
7. 让后续 Agent 每轮都有固定健康检查入口。

### 适用范围

- 治理轮、工具链轮、前端轮、浏览器验收轮
- **不替代**翻译流水线业务规则（见 `governance/novel_pipeline_contract.yaml`）

---

## 2. 工具优先级

| 优先级 | 工具 | 角色 |
|--------|------|------|
| **P0** | `filesystem` | 文件读写、仓库检查、脚本检查 |
| **P0** | `playwright` | **默认浏览器自动化**；前端页面检查首选 |
| **P0** | `github` | 远程仓库、PR、issue、push 状态确认 |
| **P1** | `context7` | 查库文档；框架/API 用法不确定时使用 |
| **P1** | `chrome-devtools` | CDP 深度调试补充；须先解决 profile 冲突 |
| **P2** | `stitch` | UI 设计原型；非翻译主线必需 |

### 说明

- **Playwright 是默认浏览器工具**，不是 chrome-devtools。
- chrome-devtools 在 profile 隔离配置生效且 MCP 已 reload 后，才作为 console/network/CDP 深度调试的补充。
- Stitch 仅用于设计输入，不得无审查覆盖 `frontend/` 业务代码。

---

## 3. 工具使用决策树

```
任务类型判断
│
├─ 文件 / 代码 / 配置问题
│   → filesystem MCP 或 IDE Read/Write/Grep + shell
│
├─ 前端页面能否打开、点击、截图、smoke test
│   → playwright MCP（首选）
│   → chrome-devtools（仅当可用且需 CDP 特定能力）
│
├─ console / network 调试
│   → chrome-devtools（profile 无冲突时）
│   → playwright + `npm run test:ui` / `run_browser_inspection.py`（fallback）
│
├─ chrome-devtools 报 profile occupied
│   → 记录冲突 → playwright fallback → 不阻塞主任务
│
├─ 库文档 / API 用法不确定
│   → context7
│
├─ GitHub 远程状态 / PR / issue
│   → github MCP；无 token 时降级 gh CLI
│
├─ 设计稿 / 视觉原型
│   → stitch；不可用时用 `docs/design/stitch/` 模板
│
└─ 非前端任务（翻译、治理文档、脚本）
    → 不需要浏览器；用 CLI 测试即可
```

---

## 4. 每轮开始前健康检查

后续 Agent **每轮开始前**（尤其 UI / 浏览器 / 工具链轮）必须：

1. **读取本 Runbook**（`docs/runbooks/mcp_browser_tools_runbook.md`）。
2. 运行 MCP 健康检查脚本。
3. 确认 Playwright 相关配置存在（`playwright.config.ts`、`package.json`）。
4. 检查 chrome-devtools 是否 profile 冲突。
5. 若任务涉及浏览器，**优先用 Playwright** 打开页面。
6. 若 chrome-devtools 不可用，**不要停止任务**，走 fallback。
7. 在轮次报告中记录本轮实际使用了哪些工具。

### 建议命令

```bash
python3 scripts/check_mcp_health.py
npm run check:mcp          # 可选
npm run check:tooling      # 真实工作树可用的控制面目标检查
```

完整 `scripts/agent_gate.py` 仅可在一次性隔离副本运行，且隔离产生的 workspace、reports、runtime 输出不得写回真实仓库。

### 软阻塞记录

若 MCP 未 reload 或 chrome-devtools 仍冲突，写入 `governance/round_state.yaml` → `soft_blockers`，并继续用 Playwright。

---

## 5. chrome-devtools profile 冲突处理

### 根因

当前典型错误：

```text
The browser is already running for <home>/.cache/chrome-devtools-mcp/chrome-profile
```

这是 **profile lock / user-data-dir 冲突**，不是单纯端口冲突。只换 `--remote-debugging-port` **不能**解决同一 `user-data-dir` 被占用的问题。

### light_novel 推荐配置

| 项 | 值 |
|----|-----|
| 项目专属 profile | `~/.cache/chrome-devtools-mcp/light_novel-chrome-profile` |
| 推荐调试端口 | `9321`（环境变量 `CHROME_DEVTOOLS_MCP_DEBUG_PORT` 可覆盖） |
| Launcher | `scripts/chrome_devtools_mcp_light_novel.sh` |
| 生效配置 | `.cursor/mcp.json` → `chrome-devtools` → 调用上述 wrapper |

### 处理规则

1. **profile 隔离优先于端口隔离。**
2. 不要删除共享 profile `chrome-profile`。
3. **不要 kill** 其他项目 Chrome / MCP 进程。
4. 不要复制 cookie / 登录态到其他 profile。
5. 若无法配置独立 profile，**默认使用 Playwright**。
6. 若 chrome-devtools 报 profile occupied：**记录并 fallback**，不阻塞翻译或 UI 验收主线。
7. 修改 `.cursor/mcp.json` 后须 **Reload Window** 或重启 Cursor，新 MCP 子进程才会使用独立 profile。

### 审计参考

- `docs/chrome_devtools_profile_conflict_audit.md`
- `docs/mcp_isolation_strategy_light_novel.md`

---

## 6. 端口冲突处理

适用于：前端 dev server、Playwright 测试、浏览器 remote debugging 端口。

| 规则 | 说明 |
|------|------|
| 默认端口被占用 | 自动换新端口；在报告中记录 |
| 禁止 kill | 不 kill 其他项目 / Agent 进程 |
| 禁止抢占 | 不抢占其他 Agent 已声明端口 |
| 配置可化 | 写死端口改为环境变量或 CLI 参数 |
| 测试可见 | 命令输出中打印实际使用端口 |
| Playwright | 测试应读取实际 dev server 端口（见 `playwright.config.ts`） |

---

## 7. 多 Agent 并行规则

1. 不同项目 **不得** 共享 Chrome DevTools 默认 profile（`chrome-profile`）。
2. 不同项目 **不得** 共享 workspace run 输出目录（本仓库使用 `workspace/`）。
3. 不同项目 **不得** 互相 kill 进程。
4. 多 Agent 同时运行时，遇到 lock 应先判断归属；**无法确认则只记录，不处理**。
5. 翻译 pipeline 进程、MCP 浏览器进程、前端 dev server 应分别管理。
6. light_novel 后续应始终使用项目专属 profile 和端口（见第 5 节）。
7. **浏览器控制禁止使用 Multitask 子 Agent**（见 `.cursor/rules/no-multitask-for-browser.mdc`）。

---

## 8. Browser Tool Fallback Matrix

| 场景 | 首选工具 | fallback | 不应做的事 |
|------|----------|----------|------------|
| 打开前端页面 | playwright | chrome-devtools / cursor-ide-browser | 不要只看代码 |
| 截图检查 | playwright | chrome-devtools | 不要提交大截图到 Git |
| console error | playwright | chrome-devtools | 不要忽略白屏 |
| network error | playwright | chrome-devtools | 不要伪造通过 |
| CDP 深调试 | chrome-devtools | playwright + CLI | profile 冲突时不要硬卡 |
| 非前端任务 | 不需要浏览器 | CLI 测试 | 不要强行打开页面 |
| MCP 未暴露 | 报告 BLOCKED | `npm run test:ui` | 不要假装已浏览器验收 |

CLI 备选：

```bash
npm run test:ui
python3 scripts/run_browser_inspection.py
```

---

## 9. 安全规则

1. 不打印 API Key、GitHub token、cookie。
2. 不提交 `.env`。
3. 不提交 Chrome profile、浏览器缓存。
4. 不提交大截图、`artifacts/` 产物。
5. 不提交 `workspace/` 大型运行输出。
6. 不删除其他项目 profile。
7. 不 kill 不属于当前任务的进程。
8. filesystem MCP 仅授权 `${workspaceFolder}`，不得访问 `/` 或用户主目录全文。
9. 不得通过 MCP 自动 push 或公开发布译文。

---

## 10. 常见故障与处理

### chrome-devtools profile occupied

1. 确认是否为共享 `chrome-profile`（非 `light_novel-chrome-profile`）。
2. 只读记录占用信息（`lsof` / `ps`，不 kill）。
3. 切换 **Playwright** 继续任务。
4. 确认 `.cursor/mcp.json` 是否已指向 `chrome_devtools_mcp_light_novel.sh`。
5. Reload Cursor Window 后重试 chrome-devtools。
6. 在报告中说明冲突与 fallback 路径。

### port already in use

1. 为 dev server 或测试换端口。
2. 更新测试 URL / 环境变量。
3. 不 kill 其他进程。
4. 在报告中记录新端口。

### MCP loaded but Agent did not use it

1. 读取本 Runbook。
2. 确认工具优先级（Playwright 优先于 chrome-devtools）。
3. 在报告中列出**实际使用**的工具。
4. 前端任务必须使用 Playwright 或 chrome-devtools；不得仅凭 Read/Grep 验收。

### Playwright available but page not opened

1. 启动 dev server：`npm run dev:frontend`（或项目文档指定命令）。
2. 确认端口（查看终端输出）。
3. 用 Playwright MCP 打开目标 URL。
4. 检查 console / network。
5. 不能只看代码宣称完成。

### GitHub MCP authenticated but push failed

1. 检查 `git remote` 与当前 branch。
2. 检查 token 权限（不打印 token）。
3. 不反复 push；记录失败原因。
4. 降级使用 `git` / `gh` CLI。

### Cursor 线程缺浏览器工具

输出：`BLOCKED: MISSING_FROM_THREAD_TOOL_REGISTRY`（见 `docs/cursor_tool_registry_check.md`）。新建**普通前台 Agent** 对话，必要时 Reload Window。

---

## 11. 相关文件索引

| 文件 | 用途 |
|------|------|
| `docs/runbooks/mcp_browser_tools_runbook.md` | 本 Runbook（权威） |
| `docs/tooling_current_status.md` | 工具状态快照 |
| `docs/mcp_isolation_strategy_light_novel.md` | Profile/端口隔离策略 |
| `docs/chrome_devtools_profile_conflict_audit.md` | 冲突审计 |
| `docs/mcp_current_status_light_novel.md` | MCP probe 记录 |
| `docs/examples/mcp.light_novel.example.json` | MCP 配置示例 |
| `scripts/check_mcp_health.py` | 健康检查入口 |
| `scripts/chrome_devtools_mcp_light_novel.sh` | 项目隔离 launcher |
| `docs/cursor_browser_ui_runbook.md` | UI 实现流程 |
| `.cursor/mcp.json` | 生效的 Workspace MCP 配置 |

---

## 12. 快速检查清单（复制到轮次报告）

```text
[ ] 已读 docs/runbooks/mcp_browser_tools_runbook.md
[ ] 已运行 python3 scripts/check_mcp_health.py
[ ] 前端任务已用 Playwright（或记录 chrome-devtools fallback 原因）
[ ] 未 kill 其他项目 Chrome/MCP 进程
[ ] 轮次报告列出实际使用工具
[ ] chrome-devtools profile 冲突已记录（如有）
```
