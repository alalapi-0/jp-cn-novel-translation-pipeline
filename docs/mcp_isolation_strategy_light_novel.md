# MCP Isolation Strategy for light_novel

## 6.1 目标

让 light_novel 项目在与其他项目并行使用 Agent 时，仍能稳定使用 MCP 工具，尤其是浏览器相关工具。

## 6.2 工具优先级

当前项目工具优先级建议：

```text
filesystem：文件读写主工具
playwright：默认浏览器自动化主工具
chrome-devtools：调试补充工具，需独立 profile 后再优先使用
context7：库文档查询
github：提交、PR、仓库查询
stitch：设计相关工具，非翻译主线
```

| 场景 | 首选 | 备选 |
|---|---|---|
| Workbench UI 验收 | playwright | cursor-ide-browser |
| console / network 深度调试 | chrome-devtools（独立 profile 后） | playwright + CLI |
| 文件读写 | filesystem | Read/Write 工具 |
| 第三方库文档 | context7 | 官方 docs |
| PR / issue | github | gh CLI |
| UI 原型 | stitch | `docs/design/stitch/` 模板 |

## 6.3 chrome-devtools 隔离策略

### Profile（必须）

```text
~/.cache/chrome-devtools-mcp/light_novel-chrome-profile
```

环境变量覆盖：

```text
CHROME_DEVTOOLS_MCP_USER_DATA_DIR
```

实现：`scripts/chrome_devtools_mcp_light_novel.sh` → `npx chrome-devtools-mcp@latest --userDataDir=...`

### Port（可选，次要）

```text
默认 remote debugging port：9321
```

环境变量覆盖：

```text
CHROME_DEVTOOLS_MCP_DEBUG_PORT
```

经 `--chromeArg=--remote-debugging-port=9321` 传入。**profile 隔离优先级高于端口隔离。只换端口不能解决同一个 user-data-dir 被占用的问题。**

### 配置入口

- 生效配置：`.cursor/mcp.json` → `chrome-devtools` → `bash scripts/chrome_devtools_mcp_light_novel.sh`
- 示例模板：`.cursor/mcp.light_novel.example.json`、`docs/examples/mcp.light_novel.example.json`

### 验证步骤

1. `python3 scripts/check_mcp_health.py`
2. Reload Cursor Window
3. MCP probe：`list_pages`（chrome-devtools）应不再报共享 `chrome-profile` 错误
4. 若仍失败 → 使用 playwright fallback，并检查是否有旧 MCP 子进程

## 6.4 Playwright fallback 策略

如果 chrome-devtools 失败：

1. **优先使用 playwright MCP**（`browser_navigate`, `browser_snapshot`, `browser_click` 等）。
2. 若本轮只是打开页面、点击、截图、检查 console，playwright 足够。
3. 只有需要 Chrome DevTools Protocol 特定能力（Performance trace、Lighthouse、heap snapshot 等）时，再尝试 chrome-devtools。
4. chrome-devtools profile 冲突 **不得** 阻塞核心翻译流水线或 UI 验收。

CLI 备选：

```bash
npm run test:ui
python3 scripts/run_browser_inspection.py
```

## 6.5 多项目并行规则

1. 每个项目使用独立 browser profile（`--userDataDir`）。
2. 每个项目使用独立调试端口（若工具支持 `--chromeArg=--remote-debugging-port=...`）。
3. 每个项目使用独立 workspace / run directory（本仓库 `workspace/` 已隔离）。
4. 不同项目的 Agent **不共享** chrome-devtools 默认 profile `chrome-profile`。
5. 不要让全局 chrome-devtools MCP 使用固定默认 profile；全局配置若无法 per-project，则该项目默认 playwright 为主。
6. 如果全局无法配置多个 profile，则项目内 **默认禁用依赖 chrome-devtools 的关键路径**，改用 playwright。

## 6.6 推进轮检查清单

每轮 Agent 开始前（Tooling / UI / 翻译无关治理轮亦适用）：

```bash
python3 scripts/check_mcp_health.py
npm run check:mcp
```

软阻塞记录：`governance/round_state.yaml` → soft blockers（若 MCP 未 reload 或 chrome-devtools 仍冲突）。

## 6.7 相关文件

| 文件 | 用途 |
|---|---|
| `scripts/chrome_devtools_mcp_light_novel.sh` | 项目隔离 launcher |
| `scripts/check_mcp_health.py` | 健康检查 + 报告 |
| `docs/mcp_current_status_light_novel.md` | 当前 MCP probe 快照 |
| `docs/chrome_devtools_profile_conflict_audit.md` | 冲突审计 |
| `docs/mcp_health_report.md` | 脚本生成的最新报告 |

## MCP 浏览器工具隔离规则

1. light_novel 项目不得依赖全局共享 chrome-devtools profile。
2. chrome-devtools 必须优先使用项目独立 profile。
3. 如果 chrome-devtools 出现 profile lock，优先切换 playwright。
4. 端口冲突和 profile 冲突不同；profile 冲突必须通过独立 user-data-dir/profile 解决。
5. 多 Agent 并行时，不要 kill 其他项目进程。
6. 前端页面检查优先使用 playwright，chrome-devtools 作为补充。
7. 后续推进轮开始时应运行 MCP 健康检查。
