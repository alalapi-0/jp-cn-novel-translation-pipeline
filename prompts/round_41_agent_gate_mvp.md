# Round 41：Agent Gate MVP

## Agent 身份

你是 Agent Gate Agent，负责实现确定性仓库门控脚本 `scripts/agent_gate.py`，不调用 LLM，不执行真实翻译。

## 当前轮次

Round 41

## 本轮类型

`tooling`

## 背景

Round 02 已完成 Agent Gate 规划（`docs/agent_gate_and_protocol_check.md`），但脚本尚未实现。缺少门控会导致 secrets、原文/译文误提交与必读文档缺失在后续轮次被放大。

## 必读文件

- `governance/repo_protocol_standard.yaml`（automation_policy）
- `docs/agent_gate_and_protocol_check.md`
- `docs/agent_tooling_strategy.md`
- `docs/roadmap_rounds_41_50_tooling_and_workbench.md`
- `governance/agent_policy.yaml`
- `prompts/agent_gate_round_template.md`

## 允许修改

`scripts/agent_gate.py`、相关 `tests/`、`docs/agent_gate_and_protocol_check.md`（补充 MVP 清单）、`governance/round_state.yaml`。

## 禁止修改

不得修改协议正文；不得调用真实 API；不得读取 `.env` 内容；不得改动 `input_jp/`、`output_cn/` 真实内容。

## 工具要求

Python 3.8+、git CLI、标准库优先（可选 PyYAML 若已存在）。

## MCP / Playwright 要求

N/A。Gate 不依赖 MCP/Playwright；可检查 Playwright 是否安装（WARNING 级）。

## 通用协议要求

exit code 对齐协议：0=PASS、1=WARNING、2=BLOCKED；报告写入 `docs/reports/agent_gate_report.md`。

## 具体任务

1. 创建 `scripts/agent_gate.py`，支持 `--json`、`--strict`。
2. 实现 docs_exist、roadmap_exists、protocol_exists、protocol_alignment_exists 检查。
3. 实现 gitignore_safe、env_not_tracked、input_sources_ignored、outputs_ignored。
4. 实现 tooling_strategy_exists、mcp_plan_exists、frontend_plan_exists、prompt_templates_exist。
5. 输出 Markdown 报告与结构化 JSON（`--json`）。
6. 对齐 BLOCKED：`.env` 被 Git 跟踪、核心 roadmap 缺失。
7. 编写最小 self-test 或 `tests/test_agent_gate.py`。
8. 更新 `governance/round_state.yaml` 标记 Round 41 完成。

## 验收标准

1. `python3 scripts/agent_gate.py` 在本仓库可运行并产生报告。
2. exit code 语义正确（本仓库预期 0 或 1，不应无故 2）。
3. 检测到 `.env` 被跟踪时能 exit 2（可用 mock 测试）。
4. 报告包含检查项 pass/fail 列表。
5. 脚本 stdout 不输出 secret 值。
6. 文档已更新运行示例。
7. 未调用真实 API 或 LLM。

## 安全检查

 suspected secrets 只报 path，不输出值；不读取 `.env`。

## Git 提交建议

`feat: add agent gate MVP script`

## 最终报告格式

summary、checks_implemented、exit_code_demo、files_changed、validation_results、warnings、next_round_42。
