# Agent 入口说明

本文件告诉 Agent 如何阅读、行动和避免风险。**Cursor 与 Codex 共用本文件。** `governance/repo_protocol_standard.yaml` 管理跨仓库安全与治理规则；本项目的产品目标、阶段顺序和验收终点以 `docs/product_final_state_spec.md` 为最高锚点（项目级 override 见 `project.yaml`）。Tool-aware Agent Layer 2.0 机器配置见 `agent_layer.yaml`。

## 项目级 Git 最终化覆盖（local-only）

本仓库的 `project.yaml` 覆盖通用协议中的 approved-round automatic Git finalization。Judge `PASS` 且 Governor `APPROVE` 后，批准的 scoped candidate **只在本地工作树完成**；Agent 不得自动 stage、commit、checkout、merge 或 push。

- edit/build 请求不隐含任何 Git 授权；任何 Round Prompt 或轮次任务书也不得授权 Git 操作。
- commit 与 push 是两个独立授权：两者分别都必须由用户在**当前轮**明确措辞授权。push 失败后不得沿用旧授权重试，必须取得用户新的当前轮明确授权。
- 仅由已验证 scoped task / baseline-owned changes 产生的 dirty worktree warning 是预期状态，不构成阻断；真实的 `FAIL` 或 `BLOCKED` 仍然阻断完成。
- 即使用户授权 commit，也永远不得提交真实原文、真实译文、workspace runtime artifacts 或 secrets；只能精确暂存已批准路径，禁止使用指向当前目录或全匹配路径的 `git add` 全量暂存形式。

## Workspace 逐文件基线与完整门禁隔离

`workspace_file_baseline` 的机器真值同时位于 `project.yaml` 与 `governance/agent_policy.yaml`：保护根目录为 `workspace`，manifest 为 `.agent_runtime/inspection_reports/workspace_file_baseline.json`，校验器为 `scripts/workspace_file_baseline.py`，算法为逐文件 SHA-256。

- 任何已知或可能写入 `workspace` 的工具，运行前必须先执行 `python3 scripts/workspace_file_baseline.py verify --json`；工具结束后必须再次执行同一 verify 命令。
- 前置或后置 verify 发现 drift、返回非零或校验器报错时均为硬阻断：立即停止该工具链并报告，不得自动执行 `create`，不得用 create/rebaseline 覆盖 drift。
- `auto_rebaseline=false`。只有用户在**当前轮明确授权**后，才可执行 baseline `create` 或 rebaseline；历史授权、Round Prompt、edit/build 请求均不授权该操作。
- 禁止在真实仓库工作树运行完整 `scripts/agent_gate.py`。完整 gate 只允许在一次性隔离临时副本中运行，且隔离副本产生的 `workspace/`、`reports/`、`.agent_runtime/` 等输出不得写回真实仓库。真实工作树只运行合同指定的 targeted/read-only checks。

## 🎯 最终成品规格（最高优先级，2026-06-10 起）

**`docs/product_final_state_spec.md` 是本仓库最高级别目标锚点**，优先级高于普通 Roadmap、Round Report、临时 Prompt 与单轮执行指令。任何冲突以它为准。任何 Agent 不得删除、弱化或绕过该文件。

每轮推进前必读（按序）：

1. `docs/product_final_state_spec.md` —— 最终成品规格 / 防跑偏锚点
2. `docs/next_agent_execution_protocol.md` —— 每轮标准执行流程
3. `docs/final_state_implementation_roadmap.md` —— 总路线图（S0–S15 阶段）
4. `docs/final_state_round_task_list.md` —— 轮次任务（FS-000…FS-070，含状态）
5. `docs/phase_acceptance_criteria.md` —— 阶段验收（可检查条件）
6. `docs/definition_of_done.md` —— 各级 Done 定义
7. `docs/non_goals_and_guardrails.md` —— 非目标与防跑偏约束
8. `docs/local_scheduler_runbook.md` —— 本地调度（S1 完成后存在）
9. `docs/translation_production_protocol.md` —— API / Agent 额度双路径翻译协议
10. `docs/translation_consistency_protocol.md` —— 一致性治理 / 唯一最终译文协议

执行要点：

- **下一轮做什么**：在 `final_state_round_task_list.md` 中找第一个未完成的 FS 轮，按其"输入 / 文件 / 命令 / 验收 / 禁止 / 产物"执行；不重新发明路线。
- **当前状态以探针为准**：先运行 `python3 scripts/local_scheduler_status.py --json`、`python3 scripts/check_orphan_workers.py --json`、`python3 scripts/check_final_translation_singleton.py --json`；叙述性快照若与探针冲突，先修正文档再推进。2026-06-18 v2.0 实测为 `current_phase=final_ready`、scheduler paused、`next_round_id=null`、0 active / 0 orphan worker、singleton final PASS。
- **生产翻译有两条合法路径**：外部真实 API（cost guard + 预算限制 + pause file 尊重）或 Agent 自身额度（结构化写入 + 一致性校对 + 报告记录）。生产模型切换 / 并发 / 提价需用户确认。
- **Web UI 是主线**而非附属：UI 轮必须真实浏览器 before/after 检查（页面、console、network），中文优先，统一设计系统，危险操作二次确认。
- **旧 R-MR / refinement / production_candidate 路线已废弃**：不得作为下一轮主任务；旧文档只可作历史参考。
- **永远不得**：自动标记 human_approved_final、自动发布、覆盖 baseline / 原文、提交真实原文或真实译文、提交 workspace runtime artifacts 或 secrets、使用 `git add` 全量暂存、留下 orphan worker。
- **完整门禁隔离**：完整 `agent_gate.py` 可能运行诊断 worker 或写运行产物，禁止在真实工作树执行；如合同要求，只能在一次性隔离临时副本中串行运行且不得回写。
- P0 / P1 未清零不做 P2 / P3；硬阻塞时停止并输出 BLOCKED（见 `non_goals_and_guardrails.md` §7）。

## Repo Mission

中日文小说互译生产流水线：双向翻译、术语/角色一致性、批量翻译、一致性校对、唯一最终译文导出与前端 Workbench。最终成品：本地 Web UI 驱动的全书"翻译 → 一致性检查 → baseline → singleton final export"生产系统（见最终规格 v2.0）。默认非生产发布。

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
2. `docs/product_final_state_spec.md`
3. `project.yaml`
4. `governance/agent_policy.yaml`
5. `governance/round_state.yaml`
6. `governance/file_role_map.yaml`
7. `governance/novel_pipeline_contract.yaml`
8. `README.md`
9. `docs/index.md`

## 本仓库追加必读（治理与推进）

10. `docs/project_vision.md`
11. `docs/architecture_overview.md`
12. `docs/governance_rules.md`
13. `docs/repo_protocol_alignment.md`
14. `docs/agent_operating_manual.md`
15. `docs/agent_tooling_strategy.md`
16. `docs/translation_production_protocol.md`
17. `docs/translation_consistency_protocol.md`
18. 当前轮 Prompt（`prompts/round_XX_*.md` 或对应模板）

旧 Round 路线图已移入 `docs/archive/legacy_roadmaps/`，仅作历史参考；与 v2 最终规格冲突时不得作为任务来源。

## 编辑前检查

- 使用 grep/glob 定位文件，避免全量读取大文件
- 禁止扫描：`.git/`、`node_modules/`、`.venv/`、`.cursor/`、`cache/`、`logs/`
- 禁止读取或打印 `.env` 内容
- 治理轮不得启动真实翻译或调用真实 API
- 对任何已知或可能写入 `workspace` 的工具，先运行 `python3 scripts/workspace_file_baseline.py verify --json`；drift 或 verifier error 立即阻断并报告
- 在真实工作树只运行当前合同指定的 targeted/read-only checks；完整 `scripts/agent_gate.py` 只能在不得回写的一次性隔离临时副本中运行

## 编辑后检查

- 更新 `governance/round_state.yaml`
- 治理变更写入 `docs/reports/`（本地，默认不提交敏感报告正文）
- 默认在未 stage/commit/push 的工作树中本地完成；Round Prompt 不得授权任何 Git 操作
- 仅当用户在当前轮明确要求 commit 时，才可精确暂存本轮批准路径；commit 前确认无 `.env`、密钥、真实原文、真实译文或 workspace runtime artifacts
- push 必须另有用户当前轮明确授权；失败后不得无新授权重试
- 已运行任何已知或可能写入 `workspace` 的工具时，结束后再次运行 `python3 scripts/workspace_file_baseline.py verify --json`；drift 或 verifier error 阻断完成，且不得自动 create/rebaseline

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
- 写入型探针刷新：`python3 scripts/tool_probe.py`（会更新报告；仅在当前 scoped task 明确拥有该刷新时运行，不是普通验证命令）

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
3. 从 `docs/final_state_round_task_list.md` 与当前批准合同选择一个小范围实现；`docs/AGENT_ROADMAP.md` 仅为已完成历史快照
4. 验证：在真实工作树只运行合同指定的 targeted/read-only checks；完整 gate 如确有要求，只能在不得回写的一次性隔离临时副本中运行
5. 报告：`reports/latest-agent-report.json` + `reports/agent_audit_log.jsonl`

### Common Commands

```bash
python3 scripts/workspace_file_baseline.py verify --json
python3 scripts/user_view_test.py
npm run dev:frontend
npm run check:tooling
npm run test:py
npm run test:ui
python3 scripts/agent.py status
```

### Gate 执行边界

| 场景 | 当前规则 |
|------|----------|
| 真实仓库工作树 | 禁止运行完整 `scripts/agent_gate.py`；仅运行合同指定的 targeted/read-only checks |
| 一次性隔离临时副本 | 合同确有要求时可运行完整 gate；副本产生的 workspace、reports、runtime outputs 不得写回 |
| Workspace 敏感工具 | 前后都执行 baseline verify；drift 或 verifier error 均为硬阻断 |

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

本仓库默认 local-only：批准轮在本地工作树完成，不自动 stage、commit、checkout、merge 或 push。edit/build 请求和 Round Prompt 均不构成 Git 授权。commit 与 push 分别需要用户在当前轮明确授权；commit 前仅精确暂存批准路径，并用 `git diff` 检查 secrets、真实原文、真实译文和 workspace runtime artifacts。任何上述类别都永不提交；push 失败后必须取得新的当前轮用户授权才能重试。

### Next Round Policy

以 `docs/final_state_round_task_list.md`、`governance/round_state.yaml` 与当前批准合同为准；`reports/latest-agent-report.json` 只作报告快照，`docs/AGENT_ROADMAP.md` 只作历史参考。

### Human Required Decisions

- 是否 push / 开 PR
- 是否启用真实 API 与成本上限
- 是否保留或清理 workspace 运行产物（这些产物永远不得提交）
- Codex 额度分配

### Prompt 模板

`docs/PROMPTS.md`

## Workspace Tooling Standard

本项目的通用 MCP 工具（chrome-devtools / playwright / context7 / github / stitch）与跨项目分工规则
遵循工作区级标准，详见：
`../.agent_workspace/docs/AGENT_TOOLING_STANDARD.md`（从当前仓库根目录解析）

本项目专属、不可全局化的工具（如有）：见本文件 MCP 配置章节。
