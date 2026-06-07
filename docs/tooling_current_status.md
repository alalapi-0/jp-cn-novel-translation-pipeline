# Tooling Current Status

## 检查时间

2026-06-07（MCP / Browser Tools Runbook 治理轮）

## 当前项目路径

`/Users/alalapi/PycharmProjects/light_novel`

## 当前 Git 分支

`main`

## MCP Server 状态总览

| Tool / Server | Status | Authentication | Main Use | Fallback | Notes |
|---|---|---|---|---|---|
| filesystem | ✅ 可用 | 无需 | 文件读写、仓库检查 | IDE Read/Write/Grep | 授权范围 `${workspaceFolder}` |
| playwright | ✅ 可用 | 无需 | **默认浏览器自动化**、UI 验收 | `npm run test:ui`、`run_browser_inspection.py` | 使用独立 temp profile，不与 chrome-devtools 冲突 |
| context7 | ✅ 可用 | 无需 | 第三方库/API 文档查询 | 官方文档、Web 搜索 | `resolve-library-id`、`query-docs` |
| github | ✅ 可用 | 已认证 | PR、issue、远程仓库状态 | `git` / `gh` CLI | 需 `GITHUB_TOKEN`；不打印 token |
| stitch | ✅ 可用 | 已认证 | UI 设计原型、screen | `docs/design/stitch/` 模板 | 需 `STITCH_API_KEY`；非翻译主线 |
| chrome-devtools | ⚠️ 部分可用 | 无需 | CDP 深度调试、console/network | **playwright**（首选） | 共享 `chrome-profile` 仍被占用；项目已配置独立 profile wrapper，需 Reload MCP |

## 当前已知问题

1. **chrome-devtools 共享 profile 冲突**：本机仍有 Chrome 进程（如 PID 50160）占用 `~/.cache/chrome-devtools-mcp/chrome-profile`，疑似其他项目（如 `wechat-article-scheduler`）的 chrome-devtools MCP 实例。
2. **MCP 配置已更新但未 reload**：`.cursor/mcp.json` 已改为 `scripts/chrome_devtools_mcp_light_novel.sh`，当前 Agent 线程 probe 可能仍反映旧配置下的冲突。
3. **多 chrome-devtools-mcp 子进程**：本机存在多个 `npm exec chrome-devtools-mcp@latest` 实例，加剧共享 profile 争用。

## chrome-devtools profile 冲突

| 路径 | 状态 |
|------|------|
| 共享默认 `~/.cache/chrome-devtools-mcp/chrome-profile` | 存在；**疑似被占用**（多 Chrome helper 进程） |
| 项目专属 `~/.cache/chrome-devtools-mcp/light_novel-chrome-profile` | 已创建（空目录）；**未被占用** |
| 项目 launcher | `scripts/chrome_devtools_mcp_light_novel.sh`（`--userDataDir` + port `9321`） |

典型错误：

```text
The browser is already running for /Users/alalapi/.cache/chrome-devtools-mcp/chrome-profile
```

**结论：** profile lock / user-data-dir 冲突，不是单纯端口冲突。只换端口不能解决。

## Playwright 可用性

| 检查项 | 状态 |
|--------|------|
| `playwright.config.ts` | 存在 |
| `@playwright/test` / `playwright` npm 依赖 | 已安装 |
| Playwright MCP | 可用；`browser_tabs` probe 成功 |
| Profile 策略 | 临时 `playwright_chromiumdev_profile-*`，与 chrome-devtools 默认 profile 隔离 |
| CLI 入口 | `npm run test:ui`、`python3 scripts/run_browser_inspection.py` |

**建议：** 前端验收、截图、console 检查 **优先 Playwright**。

## GitHub 可用性

- MCP server 已加载，descriptor 可见（27 tools）。
- 认证状态：已认证（`GITHUB_TOKEN` 环境变量）。
- Fallback：`gh` CLI；无 token 时不阻断非 GitHub 任务。

## Stitch 可用性

- MCP server 已加载（15 tools）。
- 认证：已认证（`STITCH_API_KEY`）。
- 用途：UI 设计输入；导出物入 `docs/design/stitch/`，不得无审查覆盖业务代码。

## 文件系统权限

- filesystem MCP 限制为项目根目录。
- 健康检查脚本、Runbook、隔离文档均可读写。
- 不读取或打印 `.env` 内容。

## 后续建议

1. **Reload Cursor Window** 使 chrome-devtools 使用 `light_novel-chrome-profile`。
2. 其他并行项目也应配置独立 `--userDataDir`，勿共用 `chrome-profile`。
3. 每轮开始前运行 `python3 scripts/check_mcp_health.py` 并读取 `docs/runbooks/mcp_browser_tools_runbook.md`。
4. chrome-devtools 仍冲突时立即 fallback 到 Playwright，不阻塞主线。
5. 确认 chrome-devtools MCP 真实 CLI 参数与 wrapper 一致（`--userDataDir`、`--chromeArg`）。

## 相关文档

- Runbook：`docs/runbooks/mcp_browser_tools_runbook.md`
- 隔离策略：`docs/mcp_isolation_strategy_light_novel.md`
- 冲突审计：`docs/chrome_devtools_profile_conflict_audit.md`
- 健康报告：`docs/mcp_health_report.md`（由 `scripts/check_mcp_health.py` 生成）
