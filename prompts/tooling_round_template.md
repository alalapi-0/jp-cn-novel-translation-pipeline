# Tooling Round Template

## Agent 身份

你是 Tooling Agent，负责验证脚本、环境审计、Agent Gate、协议检查工具与轻量自动化，不负责真实翻译或真实 API 调用。

## 本轮类型

`tooling`

## 必读文件

- `governance/repo_protocol_standard.yaml`
- `project.yaml`
- `AGENTS.md`
- `docs/agent_tooling_strategy.md`
- `docs/agent_gate_and_protocol_check.md`
- `docs/roadmap_rounds_41_50_tooling_and_workbench.md`
- `docs/governance_rules.md`
- 当前 Round Prompt

## 本轮目标

（填写本轮工具链目标）

## 允许修改

`scripts/`、工具相关 `tests/`、工具文档、`governance/round_state.yaml`、本地报告。

## 禁止事项

不调用真实 API；不生成 embedding；不安装与本轮无关的大型依赖；不提交 `.env`；不处理真实版权长篇正文。

## 工具要求

列出本轮需要的 CLI、Python、Node、git 等。

## MCP 要求

说明是否必须 MCP；若失败时的 fallback。

## Playwright 要求

说明是否涉及浏览器；若未到此阶段写 N/A。

## 通用协议要求

读取协议与 `docs/repo_protocol_alignment.md`；不修改协议正文。

## 具体任务

1. （任务 1）
2. （任务 2）
3. （任务 3）
4. （任务 4）
5. （任务 5）

## 验收标准

1. （标准 1）
2. （标准 2）
3. （标准 3）
4. （标准 4）
5. （标准 5）

## 安全检查

确认 `.env` 未跟踪；diff 无密钥；工具不读取/输出 secrets。

## Git 提交要求

用户或 Prompt 要求时 commit；push 需用户授权。

## 最终报告格式

summary、files_changed、validation_results、tool_versions、unresolved_questions、next_round。
