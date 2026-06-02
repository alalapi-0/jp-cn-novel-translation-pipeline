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

本项目优先使用 **`.cursor/mcp.json`** 中声明的 MCP server（与 Cursor 全局 MCP 合并，不覆盖已有全局配置）。

| 能力 | Server | 说明 |
|------|--------|------|
| 浏览器 / E2E | `playwright` | UI 任务**必须**优先使用；边实现边浏览器检查 |
| 项目文件 | `filesystem` | 仅 `${workspaceFolder}`；写入后确认真实文件状态 |
| GitHub | `github` | 需环境变量 `GITHUB_TOKEN`；无 token 时降级为 git/gh CLI |

**自动推进轮约定：**

- 轮次开始前确认 MCP 已在 Cursor Settings → MCP 中加载（修改配置后通常需 **Reload / 重启 Cursor**）。
- 浏览器相关任务不得仅凭代码判断成功；须查看页面、console、network 与核心流程。
- GitHub 操作前必须 `git diff`，避免泄露密钥或未授权内容。
- MCP 不可用时：记录原因于轮次报告或 `governance/round_state.yaml` soft blockers，并按 `docs/agent_skills/mcp_usage_skill.md` fallback 继续推进。
- 缺少 token / API Key 时进入 mock / dry-run，**不要**卡死整体流程（除非该 token 为当前轮唯一硬阻塞）。

**验证：** `python3 scripts/check_mcp_config.py`

**禁止：** 提交 token / cookie / API Key；filesystem 授权系统根目录或整个用户主目录。
