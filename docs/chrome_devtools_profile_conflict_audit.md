# Chrome DevTools MCP Profile Conflict Audit

## 问题描述

light_novel 项目与其他项目并行使用 Cursor Agent 时，chrome-devtools MCP 偶发无法 `list_pages` / 操控页面。典型错误：

```text
The browser is already running for /Users/alalapi/.cache/chrome-devtools-mcp/chrome-profile
```

## 当前共享 profile 路径

```text
/Users/alalapi/.cache/chrome-devtools-mcp/chrome-profile
```

来源：`chrome-devtools-mcp` CLI 默认值（`--userDataDir` 未指定时）。

项目原配置（`.cursor/mcp.json`）：

```json
"args": ["-y", "chrome-devtools-mcp@latest"]
```

未传入 `--userDataDir`，因此所有使用相同配置的项目/Agent 共享同一 Chrome user-data-dir。

## 进程检查结果

2026-06-07 只读检查（未 kill 任何进程）：

| 观察 | 详情 |
|---|---|
| 占用共享 profile 的 Chrome | PID **50160**，`--user-data-dir=/Users/alalapi/.cache/chrome-devtools-mcp/chrome-profile` |
| 关联 helper 进程 | PID 50167、50168、50169 等同目录 |
| chrome-devtools-mcp 实例 | 多个 `npm exec chrome-devtools-mcp@latest` / `chrome-devtools-mcp` 进程（4:14PM–4:30PM 启动） |
| 其中一个实例参数 | 含 `--autoConnect`（仍可能争用默认 profile 或连接策略） |
| Playwright 实例 | 使用 `playwright_chromiumdev_profile-*` 临时目录，**不**占用共享 chrome-profile |
| lsof 共享目录 | 至少 4 个 Google Chrome 进程持有 `chrome-profile` 下文件句柄 |

**判断：** 疑似其他项目 Agent 正在使用共享 chrome profile；无法 100% 映射到具体仓库名，但可确认是 **本机多 MCP 实例 + 单一默认 user-data-dir** 导致。

## 是否为端口冲突

**否（至少不是主因）。**

- 当前 chrome-devtools-mcp 默认通过 `--remote-debugging-pipe` 与浏览器通信，错误信息指向 **profile 已被占用**。
- 未见典型 `Address already in use :9222` 类端口错误。
- 即使为各项目分配不同 `--remote-debugging-port`，若仍共用同一 `user-data-dir`，Chrome 仍只允许一个实例使用该目录。

## 是否为 profile 冲突

**是。**

本次错误主要是 **profile lock / user-data-dir 冲突**，不是单纯端口冲突。

Chrome 对同一 `user-data-dir` 只允许一个浏览器实例；第二个 chrome-devtools-mcp 启动时会失败或无法 list pages。

## 为什么只换端口可能不够

1. `user-data-dir` 是 Chrome 配置文件根目录，包含锁文件、SQLite 状态、扩展数据等。
2. 两个 MCP server 若都默认 `--userDataDir=.../chrome-profile`，第二个实例会收到 “browser is already running” 错误。
3. `--remote-debugging-port` 只影响 CDP 连接端点；**不能**让两个进程同时打开同一 profile。
4. 正确顺序：**先隔离 profile → 再（可选）隔离 port**。

## 推荐解决方案

### light_novel 项目（已实施）

1. Wrapper：`scripts/chrome_devtools_mcp_light_novel.sh`
2. Profile：`~/.cache/chrome-devtools-mcp/light_novel-chrome-profile`
3. 可选端口：`9321`（环境变量 `CHROME_DEVTOOLS_MCP_DEBUG_PORT` 可覆盖）
4. `.cursor/mcp.json` 改为调用 wrapper，而非裸 `npx chrome-devtools-mcp@latest`

### 其他项目

每个项目配置独立 `--userDataDir`，例如：

```text
~/.cache/chrome-devtools-mcp/<project>-chrome-profile
```

### Fallback

profile 仍冲突或 MCP 未 reload 时：**优先 playwright MCP** 做页面打开、点击、截图、console 检查。

## 风险

| 风险 | 说明 |
|---|---|
| 修改 mcp.json 未 reload | Cursor 仍运行旧 MCP 子进程 |
| 误杀他项 Chrome | 可能中断其他 Agent 任务 |
| 复制共享 profile | 可能带入锁状态或敏感 cookie；本项目 **不复制** |
| 全局 ~/.cursor/mcp.json | 若存在全局 chrome-devtools，仍可能与项目配置合并冲突；需人工核对 Cursor Settings |

## 不建议直接做的事

1. **不要** `kill` 占用 `chrome-profile` 的其他项目 Chrome 进程。
2. **不要** 删除 `~/.cache/chrome-devtools-mcp/chrome-profile` 以“清锁”。
3. **不要** 把 cookie / 登录态从共享 profile 复制到项目 profile。
4. **不要** 仅修改 remote debugging port 而继续使用共享 user-data-dir。
5. **不要** 无审查覆盖全局 Cursor MCP 配置。

## 参考

- `chrome-devtools-mcp --help`：`--userDataDir`, `--chromeArg`, `--browserUrl`
- `docs/mcp_isolation_strategy_light_novel.md`
- `scripts/check_mcp_health.py`
