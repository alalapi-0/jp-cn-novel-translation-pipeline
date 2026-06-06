# Workspace MCP Servers

配置源：`.cursor/mcp.json`

## Server 列表

| 名称 | 传输 | 用途 |
|------|------|------|
| `chrome-devtools` | stdio (npx) | 浏览器调试：console、network、页面 DOM、性能 |
| `context7` | stdio (npx) | 查询第三方库与框架文档 |
| `filesystem` | stdio (npx) | 读写 **仅** `${workspaceFolder}` 内文件 |
| `github` | stdio (npx) | 仓库、issue、PR、分支（需 `GITHUB_TOKEN`） |
| `playwright` | stdio (npx) | 浏览器自动化、E2E、snapshot、截图 |
| `stitch` | stdio (node proxy) | UI 设计、原型、screen HTML、截图、DESIGN 输入 |

## 各 Server 说明

### chrome-devtools

- **用于**：Review Workbench 页面检查、console 错误、network 关键请求
- **不用于**：读取 `.env`、自动 push、删除原文目录

### context7

- **用于**：Playwright、MCP SDK、前端 API 等文档查询
- **不用于**：替代阅读本仓库 `docs/` 治理文档

### filesystem

- **授权范围**：`${workspaceFolder}` 仅此仓库根
- **禁止**：`/`, `~`, 用户主目录

### github

- **环境变量**：`GITHUB_TOKEN` → `GITHUB_PERSONAL_ACCESS_TOKEN`
- **无 token**：降级 `git` / `gh` CLI

### playwright

- **用于**：打开 `http://127.0.0.1:5174/`、跑核心流程、截图到 `artifacts/`（不提交）
- **CLI 备选**：`npm run test:ui`

### stitch

- **用于**：生成 Dashboard、审核台、Debug 面板等 UI 原型；导出到 `docs/design/stitch/`
- **环境变量**：`STITCH_API_KEY`（仅环境，不写仓库）
- **实现**：`scripts/stitch_mcp_proxy.mjs` + `@google/stitch-sdk`
- **不用于**：覆盖业务代码、调用翻译 API、删除项目文件

## 验证

```bash
npm run check:mcp
npm run check:stitch
```

Cursor Settings → MCP 确认各 server 已启用。

## 安全总则

- 提交前 `git diff` 确认无 token / API Key
- MCP 配置使用 `${env:...}` 引用密钥
- 不可用 MCP 时记录 soft blocker，不阻断无关任务
