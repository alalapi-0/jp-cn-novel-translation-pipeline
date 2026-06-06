# Stitch MCP 配置指南

## 传输方式（本项目采用）

本项目使用 **本地 stdio proxy**，而非 Remote HTTP 直连：

| 方式 | 说明 |
|------|------|
| **本地 proxy（默认）** | `node scripts/stitch_mcp_proxy.mjs`，基于官方 `@google/stitch-sdk` 的 `StitchProxy` |
| Remote HTTP（备选） | `https://stitch.googleapis.com/mcp` + `X-Goog-Api-Key` header；Cursor 对 header 环境变量插值支持不稳定，故不作为默认 |

### 为何不用 Remote 作为默认

社区反馈与 Google 论坛记录表明：部分编辑器在 Remote MCP 上无法可靠注入 `X-Goog-Api-Key`；本地 proxy 从进程环境读取 Key 更安全、更稳定。

## `.cursor/mcp.json` 配置

已合并进项目配置（勿覆盖其他 server）：

```json
"stitch": {
  "type": "stdio",
  "command": "node",
  "args": ["scripts/stitch_mcp_proxy.mjs"],
  "env": {
    "STITCH_API_KEY": "${env:STITCH_API_KEY}"
  }
}
```

## API Key

1. 从 Stitch 控制台获取 API Key
2. 写入 **本机环境**，任选其一：
   - Shell：`export STITCH_API_KEY=...`
   - Cursor：Settings → MCP → stitch → 环境变量（若 UI 支持）
   - 本机 `~/.cursor/mcp.json` 用户级 env（**勿提交到 Git**）
3. 在 `.env.example` 中仅有占位符；真实值放 `.env`（已 gitignore）

```env
STITCH_API_KEY=your_stitch_api_key_here
```

**禁止** 将真实 Key 写入：`.cursor/mcp.json`、README、设计文档、commit。

## 依赖

Proxy 使用 devDependency（已写入 `package.json`）：

- `@google/stitch-sdk`
- `@modelcontextprotocol/sdk`

安装：

```bash
npm ci
```

## 验证步骤

```bash
# 1. JSON 格式与 stitch 条目
npm run check:stitch

# 2. 全部 MCP（不含 stitch 必填，见 check_mcp_config.js）
npm run check:mcp
```

在 Cursor 中：

1. Reload Window
2. Settings → MCP → 确认 `stitch` 显示为已连接
3. 在 Agent 对话中尝试列出 Stitch 工具（如 `list_projects`、`generate_screen_from_text`）

若 proxy 启动失败且 stderr 为 `STITCH_API_KEY is not set`，说明环境变量未传入 Cursor MCP 子进程。

## Remote MCP 备选（高级）

若你确认 Cursor 版本支持 header 环境插值，可在**用户级**配置尝试：

```json
"stitch-remote": {
  "url": "https://stitch.googleapis.com/mcp",
  "headers": {
    "X-Goog-Api-Key": "${env:STITCH_API_KEY}"
  }
}
```

**不要** 在仓库 `.cursor/mcp.json` 中同时保留两个 stitch 名称；仓库统一使用 server 名 `stitch` + 本地 proxy。

## 故障排除

| 现象 | 处理 |
|------|------|
| stitch 未出现在 MCP 列表 | Reload Window；检查 `node` 与 `npm ci` |
| API key 错误 | 旋转 Key；确认未混用 OAuth-only 配置 |
| 工具调用超时 | Stitch 生成较慢，属正常；勿重复并发大量请求 |
| 无 Key 仍需推进 UI | 使用 `PROMPT_TEMPLATES.md` + `UI_TASKS.md` 手工描述，记录 soft blocker |

## 检查脚本

`scripts/check_stitch_config.js` 会检查：

- `mcp.json` 含 `stitch`
- 无硬编码疑似 API Key
- `.env.example` 含 `STITCH_API_KEY`
- `.gitignore` 忽略 `.env`
- `docs/design/stitch/` 目录完整
