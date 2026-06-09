# Agent 入口说明

本文件告诉 Agent 如何阅读、行动和避免风险。**Cursor 与 Codex 共用本文件。** 权威顺序以 `governance/repo_protocol_standard.yaml` 为准；Tool-aware Agent Layer 2.0 机器配置见 `agent_layer.yaml`。

## Repo Mission

中日文小说互译生产流水线：双向翻译、术语/角色一致性、批量初翻、润色、审核与前端 Workbench。当前阶段以治理、工具链与 pilot 为主，默认非生产发布。

## Tool-aware 每轮必读（Layer 2.0）

在下方治理顺序之前或并行读取：

1. `AGENTS.md`（本文件）
2. `agent_layer.yaml`
3. `agent_tools.yaml`
4. `docs/TOOL_USAGE_POLICY.md`
5. `docs/AGENT_RUNBOOK.md`
6. `reports/latest-agent-report.json`
7. `docs/TOOL_INVENTORY.md` 或 `reports/tool_probe_report.json`

## Read First（治理顺序）

1. `governance/repo_protocol_standard.yaml`
2. `project.yaml`
3. `governance/agent_policy.yaml`
4. `governance/round_state.yaml`
5. `governance/file_role_map.yaml`
6. `governance/novel_pipeline_contract.yaml`
7. `README.md`
8. `docs/index.md`

## 本仓库追加必读（治理与推进）

9. `docs/project_vision.md`
10. `docs/architecture_overview.md`
11. `docs/governance_rules.md`
12. `docs/repo_protocol_alignment.md`
13. `docs/roadmap_rounds_00_40.md`
14. `docs/roadmap_rounds_41_50_tooling_and_workbench.md`（工具链轮次）
15. `docs/agent_operating_manual.md`
16. `docs/agent_tooling_strategy.md`
17. 当前轮 Prompt（`prompts/round_XX_*.md` 或对应模板）

## 编辑前检查

- 使用 grep/glob 定位文件，避免全量读取大文件
- 禁止扫描：`.git/`、`node_modules/`、`.venv/`、`.cursor/`、`cache/`、`logs/`
- 禁止读取或打印 `.env` 内容
- 治理轮不得启动真实翻译或调用真实 API
- 运行 `scripts/agent_gate.py`（Round 41 起，实现前手动对照 `docs/agent_gate_and_protocol_check.md`）

## 编辑后检查

- 更新 `governance/round_state.yaml`
- 治理变更写入 `docs/reports/`（本地，默认不提交敏感报告正文）
- 用户或轮次 Prompt 明确要求时再 commit；commit 前确认无 `.env`/密钥/真实原文/真实译文
- push 需用户明确授权

## 硬阻塞

见 `docs/agent_operating_manual.md` 第 5.4 节。

## 工具链

见 `docs/agent_tooling_strategy.md`、`docs/mcp_playwright_setup_plan.md`、`docs/agent_skills/mcp_usage_skill.md`、`docs/agent_skills/translation_qa_skill.md`。

## MCP Tools

当前项目要求启用以下 **Workspace MCP Servers**（见 `.cursor/mcp.json`，与 Cursor 全局 MCP 合并，不覆盖已有全局配置）：

- `chrome-devtools`
- `context7`
- `filesystem`
- `github`
- `playwright`
- `stitch`

| Server | 用途 |
|--------|------|
| `chrome-devtools` | 浏览器调试、console、network、页面状态检查 |
| `context7` | 查询第三方库和框架文档 |
| `filesystem` | 安全读取和检查当前项目文件（仅 `${workspaceFolder}`） |
| `github` | 仓库、提交、分支、issue、PR 等相关操作 |
| `playwright` | 浏览器自动化、页面操作、E2E 检查 |
| `stitch` | UI 设计、原型、screen HTML/截图、DESIGN 输入（见 `docs/design/stitch/`） |

**自动推进轮约定：**

- 自动推进轮开始前，Agent **必须**确认上述 MCP 已在 Cursor Settings → MCP 中加载（修改 `mcp.json` 后通常需 **Reload / 重启 Cursor**）。
- 若某个 MCP 不可用，Agent 需记录原因，并使用可用替代方案继续推进（见 `docs/agent_skills/mcp_usage_skill.md`）。
- 涉及页面、审核台、生成结果、预览、发布流程的任务，**必须**使用 `chrome-devtools` 或 `playwright` 进行真实浏览器检查；不得仅凭代码推断成功。
- 文档和依赖不确定时，优先用 `context7` 查询。
- GitHub 操作前必须 `git diff`，避免泄露密钥或未授权内容。
- 缺少 token / API Key 时进入 mock / dry-run，**不要**卡死整体流程（除非该 token 为当前轮唯一硬阻塞）。

**验证：** `node scripts/check_mcp_config.js` 或 `npm run check:mcp`；`npm run check:stitch`；亦可 `python3 scripts/check_mcp_config.py`

**禁止：** 提交 token / cookie / API Key；filesystem 授权系统根目录或整个用户主目录。

## Stitch Design MCP

1. 本项目可使用 **Stitch** 作为 UI 设计工具（server 名：`stitch`）。
2. 涉及 UI、页面、审核台、预览页、管理后台、视觉检查页时，Agent **应先查看**：
   - `docs/design/DESIGN.md`
   - `docs/design/stitch/README.md`
   - `docs/design/stitch/UI_TASKS.md`
   - `docs/design/stitch/PROMPT_TEMPLATES.md`
3. 若 Stitch MCP 可用，Agent 可用其生成：UI 原型、screen、screenshot、HTML、DESIGN.md、多方案 variants。
4. Stitch 生成结果 **必须保存到**：
   - `docs/design/stitch/exports/`
   - `docs/design/stitch/screenshots/`
   - `docs/design/stitch/reviews/`
5. Agent **不得** 将 Stitch 导出代码无审查地覆盖 `frontend/` 或 `src/` 业务代码。
6. 实现 UI 前须将 Stitch 结果拆成可落地任务（见 `docs/design/stitch/STITCH_WORKFLOW.md`）。
7. 实现 UI 后 **必须** 使用 Playwright 或 chrome-devtools 检查（见 `docs/testing/BROWSER_TESTING.md`）。
8. 若 Stitch MCP 不可用，记录原因（`governance/round_state.yaml` soft blockers 或轮次报告），并用文档模板继续推进。

配置：`STITCH_API_KEY` 环境变量；`npm run check:stitch`；详见 `docs/design/stitch/STITCH_MCP_SETUP.md`。

## Continuous Real API Multi-Agent Foundation

本仓库使用 `.agent_runtime/` 保存连续推进状态、任务队列、阻塞记录和本地检查报告。`.agent_runtime/status.json`、`.agent_runtime/queue.jsonl`、`.agent_runtime/blockers.jsonl` 可提交；各类运行报告、截图、日志和真实 API 摘要产物默认不提交。

使用 `scripts/agent.py` 管理轮次、队列和阻塞：

```bash
python3 scripts/agent.py status
python3 scripts/agent.py next
python3 scripts/agent.py queue
python3 scripts/agent.py enqueue --type bugfix --reason test_failure
python3 scripts/agent.py block --reason "..."
python3 scripts/agent.py unblock
```

每轮推进前应执行：

```bash
python3 scripts/agent.py status
python3 scripts/agent.py next
```

真实 API 小规模测试统一入口：

```bash
python3 scripts/run_real_api_smoke.py
python3 scripts/run_real_api_smoke.py --real
```

有 API Key 时优先真实 API 小测；没有 Key 时进入 dry-run 或 `missing_api_key`，不阻断可 mock / dry-run 的整体流程。脚本只从环境变量读取 Key，不读取 `.env`，不打印 Key，不保存完整真实 API 返回全文。

浏览器检查统一入口：

```bash
python3 scripts/run_browser_inspection.py
```

页面相关任务应由 Cursor 后续结合 MCP / Playwright / `chrome-devtools` 做真实浏览器检查。多 Agent 分工见 `docs/agent_workflow/`：

- `runner_agent.md`
- `browser_inspector_agent.md`
- `bugfix_agent.md`
- `quality_optimizer_agent.md`
- `continuous_multi_agent_loop.md`
- `quality_gate.md`

生成质量差时写入 `quality_optimization` 队列；流程 bug 时写入 `bugfix` 队列；页面显示问题写入 `browser_inspection` 或 `bugfix`。无硬阻塞时继续下一轮。

## Cursor Browser UI Workflow

浏览器 UI 推进须遵守 `docs/cursor_browser_ui_runbook.md` 与 `docs/cursor_tool_registry_check.md`。

1. Cursor 做 UI 优化时必须使用 **普通前台 Agent**。
2. **禁止 Multitask** 控制浏览器（子 Agent 通常不继承 Workspace MCP）。
3. 每轮 UI 实现必须先检查 **真实页面**（启动 dev server 后打开 URL）。
4. 每轮 UI 实现必须使用 **before / after** 浏览器检查（截图、console、network）。
5. **Stitch** 用作设计输入；导出物入 `docs/design/stitch/`，不得无审查覆盖业务代码。
6. **chrome-devtools** 用作页面调试（console、network、截图）。
7. **playwright** 用作回归测试（`npm run test:ui` 或 MCP）。
8. **filesystem** 用作文件真值检查（确认写入磁盘）。
9. **context7** 用作文档查询。
10. **github** 用作提交和远程状态（无 token 时降级 git/gh CLI）。
11. 微信已登录页面只允许 **wechat-chrome-session**（本项目通常不适用）。
12. 如果当前线程缺工具，输出 **`BLOCKED: MISSING_FROM_THREAD_TOOL_REGISTRY`**，不要继续假装执行。

**检查命令：** `npm run check:cursor-mcp`、`npm run check:mcp`、`npm run check:stitch`

**UI 轮 Prompt 模板：** `docs/prompts/CURSOR_UI_IMPLEMENTATION_PROMPT.md`

**Cursor Rules：** `.cursor/rules/cursor-browser-ui.mdc`、`.cursor/rules/no-multitask-for-browser.mdc`、`.cursor/rules/agent-layer.mdc`、`.cursor/rules/tool-usage.mdc`

---

## Tool-aware Agent Layer 2.0（Cursor + Codex）

### Tool Inventory

- 人类可读：`docs/TOOL_INVENTORY.md`
- 机器可读：`agent_tools.yaml`、`reports/tool_probe_report.json`
- 探针：`python3 scripts/tool_probe.py`

### Tool Usage Policy

`docs/TOOL_USAGE_POLICY.md` — 任务阶段 → 工具映射、禁止项、fallback。

### Search Policy

`docs/SEARCH_POLICY.md` — 何时必须搜索；结果写入 `docs/RESEARCH_NOTES.md`。

### Safe Operating Rules

- 默认禁止真实付费 API 与真实发布（见 `agent_layer.yaml`）
- 不读、不打印 `.env`
- 工具未知 → 只读探针；不可用 → 记录 `TOOL_UNAVAILABLE` / `BLOCKED_ENV`
- 详见 `docs/AGENT_SAFETY.md`、`docs/COST_CONTROL.md`

### Round Lifecycle

1. 读 Layer 2.0 必读文件 + `git status`
2. 工具探针 / 工具计划
3. 小范围实现（`docs/AGENT_ROADMAP.md` 中一条 AL-xxx）
4. 门禁：`python3 scripts/agent_gate.py --json`；必要时 `npm run check:tooling`
5. 报告：`reports/latest-agent-report.json` + `reports/agent_audit_log.jsonl`

### Common Commands

```bash
python3 scripts/tool_probe.py
python3 scripts/agent_gate.py --json
python3 scripts/user_view_test.py
npm run dev:frontend
npm run check:tooling
npm run test:py
npm run test:ui
python3 scripts/agent.py status
```

### Gate Commands

| 命令 | 输出 |
|------|------|
| `python3 scripts/agent_gate.py` | exit 0/1/2；`docs/reports/agent_gate_report.md` |
| `python3 scripts/agent_gate.py --json` | stdout JSON |
| — | `reports/gate_result.json` |

### Severity Rules

| 级别 | 含义 |
|------|------|
| P0 | 数据丢失、密钥泄露、无法启动、误触发真实 API/发布 |
| P1 | 主流程不可用、核心测试失败 |
| P2 | 非核心缺陷、UI 问题 |
| P3 | 文档、抛光 |

P0/P1 未清零不做 P2/P3。

### Report Format

Schema：`schemas/agent_round_report.schema.json`  
最新：`reports/latest-agent-report.json`  
说明：`docs/AGENT_REPORTING.md`

### Cursor-specific Notes

- 主力 Agent；MCP 见 `.cursor/mcp.json`
- UI 必须真实浏览器检查；禁止 Multitask 控浏览器
- Cloud Agent 额外依赖本文件中的命令与环境说明

### Codex-specific Notes

- 高价值、长程、审查任务；额度有限时见 `docs/CODEX_USAGE.md`
- 启动前读 `docs/CODEX_HANDOFF.md`（若 Cursor 已填写）
- 同一 `AGENTS.md` + `agent_layer.yaml`

### MCP-specific Notes

见上文 MCP Tools 与 `docs/runbooks/mcp_browser_tools_runbook.md`。配置了就要在报告中说明是否使用。

### Browser / Playwright Notes

`docs/USER_VIEW_TESTING.md`、`docs/cursor_browser_ui_runbook.md`

### Real API / Real Publish Rules

仅当用户与环境变量显式允许且仓库协议允许。Agent Layer 轮默认 dry-run。

### Commit / Push Policy

用户或轮次 Prompt 明确要求才 commit；push 需用户授权；commit 前 `git diff` 查密钥与原文。

### Next Round Policy

读 `reports/latest-agent-report.json` 的 `next_recommended_round` 与 `docs/AGENT_ROADMAP.md`。

### Human Required Decisions

- 是否 push / 开 PR
- 是否启用真实 API 与成本上限
- 是否提交含 workspace 运行产物
- Codex 额度分配

### Prompt 模板

`docs/PROMPTS.md`
