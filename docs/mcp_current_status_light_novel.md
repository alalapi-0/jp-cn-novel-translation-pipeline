# MCP Current Status for light_novel

## 检查时间

2026-06-07（UTC 治理轮 MCP 隔离审计）

## 当前仓库

- 路径：`/Users/alalapi/PycharmProjects/light_novel`
- 分支：`main`
- 项目级 MCP 配置：`.cursor/mcp.json`

## MCP Server 总览

| server | status | tools | probe | note |
|---|---|---:|---|---|
| filesystem | ✅ 可用 | 15 | `list_allowed_directories` | 返回 `${workspaceFolder}` |
| playwright | ✅ 可用 | 23 | `browser_tabs` action=list/new | 使用独立 temp profile；本轮 probe 成功 |
| context7 | ✅ 可用 | 2 | descriptor 可见 | `resolve-library-id`, `query-docs` |
| github | ✅ 可用 | 27 | descriptor 可见 | 需 `GITHUB_TOKEN` 才能调用远程 API |
| stitch | ✅ 可用 | 15 | descriptor 可见 | 需 `STITCH_API_KEY` |
| chrome-devtools | ⚠️ 部分可用（共享 profile 冲突） | 29 | `list_pages` | 报错：`The browser is already running for .../chrome-profile` |

## chrome-devtools 问题

当前线程内 `list_pages` 失败，错误为：

```text
The browser is already running for /Users/alalapi/.cache/chrome-devtools-mcp/chrome-profile.
Use --isolated to run multiple browser instances.
```

根因：`.cursor/mcp.json` 原先使用 `npx chrome-devtools-mcp@latest` 默认参数，默认 `userDataDir` 为共享路径 `~/.cache/chrome-devtools-mcp/chrome-profile`。本机已有 Chrome 进程（PID 50160 等）占用该目录，疑似其他项目 Agent 的 chrome-devtools MCP 实例。

**结论：这是 profile / user-data-dir 锁冲突，不是单纯 remote debugging 端口冲突。**

本轮已改为项目 wrapper：`scripts/chrome_devtools_mcp_light_novel.sh`，目标 profile：

```text
~/.cache/chrome-devtools-mcp/light_novel-chrome-profile
```

可选调试端口：`9321`（经 `--chromeArg=--remote-debugging-port=9321`）。

修改 `.cursor/mcp.json` 后需 **Reload Window** 或重启 Cursor，新 MCP 进程才会使用独立 profile；当前线程 probe 仍反映旧配置下的冲突状态。

## playwright fallback 状态

- Playwright MCP 可用，本轮 `browser_tabs` 成功打开 `about:blank`。
- Playwright 使用 `/var/folders/.../playwright_chromiumdev_profile-*` 临时 profile，与 chrome-devtools 默认 profile 无冲突。
- 前端验收、截图、console 检查应 **优先 playwright**；chrome-devtools 作为 CDP 深度调试补充。

## 风险判断

| 风险 | 级别 | 说明 |
|---|---|---|
| 多项目共享 chrome-profile | 高 | 并行 Agent 会互相阻塞 chrome-devtools |
| 仅改端口不改 profile | 中 | 无法解除 user-data-dir 单实例锁 |
| MCP 配置未 reload | 中 | 改 mcp.json 后旧 MCP 子进程仍用旧参数 |
| Playwright 不可用 | 低 | 当前可用，须保持不破坏 |

## 建议处理方式

1. 使用本项目 wrapper + 独立 `light_novel-chrome-profile`（已落地）。
2. 其他项目也应配置各自 `--userDataDir`，勿共用 `chrome-profile`。
3. chrome-devtools profile 冲突时立即 fallback 到 playwright。
4. 每轮推进前运行 `python3 scripts/check_mcp_health.py`。
5. 不要 kill 其他项目 Chrome/MCP 进程以抢锁。
