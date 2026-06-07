# MCP 使用技能（Agent Skill）

本文档说明本仓库 `.cursor/mcp.json` 中声明的 MCP 工具、用途、安全边界与降级策略。自动推进轮（Round 44+ 前端验证、Round 45+ MCP 验证）开始前应阅读本文档。

## 当前启用的 MCP

| Server 名称 | 包 / 命令 | 状态 | 用途 |
|-------------|-----------|------|------|
| `chrome-devtools` | `bash scripts/chrome_devtools_mcp_light_novel.sh` | 已配置（项目隔离 profile） | 浏览器调试、console、network、Performance；**勿共用默认 chrome-profile** |
| `context7` | `npx -y @upstash/context7-mcp@latest` | 已配置 | 第三方库文档查询 |
| `playwright` | `npx -y @playwright/mcp@latest` | 已配置 | 浏览器自动化：打开页面、snapshot、点击、截图、辅助 E2E 验收 |
| `filesystem` | `npx -y @modelcontextprotocol/server-filesystem` | 已配置 | 项目内文件读写与目录检查（仅 `${workspaceFolder}`） |
| `github` | `npx -y @modelcontextprotocol/server-github` | 已配置（需 token） | 读取仓库、commit、issue、PR 状态（需 `GITHUB_TOKEN`） |
| `stitch` | `node scripts/stitch_mcp_proxy.mjs` | 已配置（需 `STITCH_API_KEY`） | UI 设计原型、screen HTML/截图；产物入 `docs/design/stitch/` |

### Cursor 内置 MCP（非本仓库 mcp.json）

Cursor 可能额外加载 IDE 内置能力（例如 `cursor-ide-browser`、`cursor-app-control`）。**不要**在仓库中重复声明或覆盖全局 `~/.cursor/mcp.json`；项目级配置以 `.cursor/mcp.json` 为准，与全局配置合并由 Cursor 处理。

## Playwright MCP

**用于：**

- 打开本地或 dev server 上的 Review Workbench 页面
- 获取页面 snapshot、点击导航、检查按钮与表单
- 配合 console / network 检查（通过浏览器工具或 Playwright trace）
- 前端 Round 46+ 的视觉与交互验证

**不用于：**

- 读取 `.env` 或输出 API Key
- 自动 push、公开发布译文
- 删除 `input_jp/`、`input_cn/` 中的真实原文

**最低验证要求（UI 相关任务）：**

1. 页面能加载（非仅看代码）
2. 核心路由 / 按钮存在
3. 控制台无严重错误
4. 关键数据加载路径可走通（或 documented skip 原因）
5. 失败时截图或 trace 写入 `artifacts/`（不提交 Git）

CLI fallback：`npx playwright test`（Round 44 搭建后）。详见 `docs/mcp_playwright_setup_plan.md`。

## chrome-devtools 隔离与 fallback

- **独立 profile：** `~/.cache/chrome-devtools-mcp/light_novel-chrome-profile`（经 `scripts/chrome_devtools_mcp_light_novel.sh`）
- **共享默认 profile 冲突：** 错误含 `browser is already running for .../chrome-profile` → **改用 playwright**，不要 kill 其他项目 Chrome
- **检查：** `python3 scripts/check_mcp_health.py`
- **文档：** `docs/mcp_isolation_strategy_light_novel.md`

修改 `.cursor/mcp.json` 后须 Reload Cursor Window，MCP 子进程才会使用新 profile。

## Stitch MCP（UI 设计）

**用于：**

- 生成 Dashboard、审核台、导出页、Debug 面板等 UI 原型
- 获取 screen HTML 与截图作为实现参考
- 多方案 variants 对比布局

**不用于：**

- 无审查覆盖 `frontend/` 或 `src/` 业务代码
- 翻译 API、embedding、向量库操作
- 删除项目文件或自动 commit 大段生成代码

**环境变量：** `STITCH_API_KEY`（仅环境，见 `.env.example` 占位符）

**产物路径：** `docs/design/stitch/exports/`、`screenshots/`、`reviews/`

**验证：** `npm run check:stitch`

详见 `docs/design/stitch/STITCH_MCP_SETUP.md`、`.cursor/rules/stitch-design-mcp.mdc`。

## 文件系统 MCP 授权范围

- **唯一授权根目录：** `${workspaceFolder}`（即包含 `.cursor/mcp.json` 的本仓库根目录）
- **禁止：** 授权 `/`、`C:\`、`${userHome}` 整目录或仓库外路径
- **目的：** 让 Agent 通过 MCP 稳定确认文件是否存在、内容是否已写入，而不是仅凭记忆推断

若 filesystem MCP 未加载，使用 Cursor 内置 Read / Write / Grep 工具，并在轮次报告中记录原因。

## GitHub MCP 与 Token

- **环境变量：** 在 shell 或 Cursor 环境中设置 `GITHUB_TOKEN`（fine-grained 或 classic PAT，仅需本任务最小 scope：repo 读、issues/PR 读；push 仍优先 `git` / `gh` CLI）
- **配置映射：** `GITHUB_PERSONAL_ACCESS_TOKEN=${env:GITHUB_TOKEN}`（见 `.cursor/mcp.json`）
- **禁止：** 将 token 写入仓库、`.cursor/mcp.json`、文档或 commit message

**无 token 时降级：**

- 使用 `git log`、`git status`、`git diff` 本地检查
- 若已安装 `gh` 且已登录，使用 `gh pr list`、`gh issue list` 等
- 进入 mock / dry-run，**不要**因缺少 GitHub MCP 阻塞非 GitHub 依赖轮次

## 文档查询 MCP（可选，未默认启用）

本仓库**未**在 `.cursor/mcp.json` 中默认启用 Context7、library-docs 等第三方文档 MCP，以避免安装无法验证的包。

可选方案（需用户本地确认后手动添加到 `~/.cursor/mcp.json` 或合并到项目配置）：

- **Context7：** 用于查询库文档；需 Context7 API Key，见 [Context7 MCP 文档](https://github.com/upstash/context7)
- **项目内文档：** 优先阅读 `docs/index.md`、`AGENTS.md` 与当前轮 Prompt，不依赖外部 MCP

## 无 API Key / Token 时的降级矩阵

| 缺失项 | 降级方案 |
|--------|----------|
| Playwright MCP 未加载 | Playwright CLI smoke；或 static server + curl；记录 WARNING |
| filesystem MCP 未加载 | 内置 Read/Write/Grep；`git status` 确认文件变更 |
| `GITHUB_TOKEN` 未设置 | 本地 git / gh CLI；跳过远程 PR/issue 查询 |
| Context7 未配置 | 阅读仓库 `docs/`；Web 搜索（治理轮慎用） |
| `STITCH_API_KEY` 未设置 | 使用 `docs/design/stitch/PROMPT_TEMPLATES.md` 文字模板 + 现有 `frontend/` 参考 |
| stitch MCP 未加载 | 同上；记录 soft blocker |
| Node/npx 不可用 | 文档化阻塞项；不无限重试 npx |

## 自动推进轮如何使用 MCP

1. **轮次开始：** 运行 `python3 scripts/check_mcp_config.py`（或阅读其输出说明）
2. **确认加载：** Cursor → Settings → MCP，确认 `playwright`、`filesystem`、`github` 状态；**修改 mcp.json 后需重启 Cursor 或 Reload MCP**
3. **UI 任务：** 必须 Playwright / 浏览器 MCP；实现过程中边改边查页面
4. **文件任务：** 写入后通过 filesystem 或 Read 确认磁盘状态
5. **GitHub 任务：** commit 前 `git diff`；无 token 时用本地 git
6. **轮次结束：** 更新 `governance/round_state.yaml`；MCP 失败写入 soft blockers，非唯一阻塞则不 hard stop

## 安全禁令（必须遵守）

1. **禁止** 提交 token、cookie、API Key、`.env` 内容
2. **禁止** filesystem MCP 授权系统根目录或用户主目录整树
3. **禁止** MCP 输出或日志打印密钥
4. **禁止** MCP 绕过 Git 审查（push 仍需用户授权与 diff 检查）
5. **禁止** MCP 自动公开发布译文或删除真实原文

## 相关文档

- `AGENTS.md` — MCP Tools 节、Stitch Design MCP 节
- `agent.md` — 快捷入口
- `.cursor/rules/mcp-agent-tools.mdc` — Agent 行为规则
- `.cursor/rules/stitch-design-mcp.mdc` — Stitch UI 设计规则
- `docs/mcp/README.md` — MCP 文档索引
- `docs/design/stitch/` — 设计输入层
- `docs/mcp_playwright_setup_plan.md` — Playwright / MCP 安装与验证计划
- `docs/agent_tooling_strategy.md` — 工具分层与 fallback

## Cursor 重启说明

新建或修改 `.cursor/mcp.json` 后，Cursor **通常需要** Reload Window 或重启 IDE 才能加载新 MCP server。验证路径：Settings → MCP → 查看各 server 连接状态与 Output 日志。
