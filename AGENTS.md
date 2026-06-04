# Agent 入口说明

本文件告诉 Agent 如何阅读、行动和避免风险。权威顺序以 `governance/repo_protocol_standard.yaml` 为准；本仓库追加文档见文末。

## 默认阅读顺序

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

见 `docs/agent_tooling_strategy.md`、`docs/mcp_playwright_setup_plan.md`、`docs/agent_skills/mcp_usage_skill.md`。

## MCP Tools

当前项目要求启用以下 **Workspace MCP Servers**（见 `.cursor/mcp.json`，与 Cursor 全局 MCP 合并，不覆盖已有全局配置）：

- `chrome-devtools`
- `context7`
- `filesystem`
- `github`
- `playwright`

| Server | 用途 |
|--------|------|
| `chrome-devtools` | 浏览器调试、console、network、页面状态检查 |
| `context7` | 查询第三方库和框架文档 |
| `filesystem` | 安全读取和检查当前项目文件（仅 `${workspaceFolder}`） |
| `github` | 仓库、提交、分支、issue、PR 等相关操作 |
| `playwright` | 浏览器自动化、页面操作、E2E 检查 |

**自动推进轮约定：**

- 自动推进轮开始前，Agent **必须**确认上述 MCP 已在 Cursor Settings → MCP 中加载（修改 `mcp.json` 后通常需 **Reload / 重启 Cursor**）。
- 若某个 MCP 不可用，Agent 需记录原因，并使用可用替代方案继续推进（见 `docs/agent_skills/mcp_usage_skill.md`）。
- 涉及页面、审核台、生成结果、预览、发布流程的任务，**必须**使用 `chrome-devtools` 或 `playwright` 进行真实浏览器检查；不得仅凭代码推断成功。
- 文档和依赖不确定时，优先用 `context7` 查询。
- GitHub 操作前必须 `git diff`，避免泄露密钥或未授权内容。
- 缺少 token / API Key 时进入 mock / dry-run，**不要**卡死整体流程（除非该 token 为当前轮唯一硬阻塞）。

**验证：** `node scripts/check_mcp_config.js` 或 `npm run check:mcp`；亦可 `python3 scripts/check_mcp_config.py`

**禁止：** 提交 token / cookie / API Key；filesystem 授权系统根目录或整个用户主目录。

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
