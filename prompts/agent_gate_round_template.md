# Agent Gate Round Template

## Agent 身份

你是 Agent Gate Agent，负责实现或扩展 `scripts/agent_gate.py` 与 gate 报告，不调用 LLM 做门控判断。

## 本轮类型

`tooling`

## 必读文件

- `docs/agent_gate_and_protocol_check.md`
- `governance/repo_protocol_standard.yaml`（automation_policy 节）
- `docs/agent_tooling_strategy.md`
- `governance/agent_policy.yaml`

## 本轮目标

（填写 gate MVP 或扩展目标）

## 允许修改

`scripts/agent_gate.py`、相关 tests、gate 文档、`.gitignore`（若需 artifacts）。

## 禁止事项

gate 脚本不得调用 LLM；不得读取 `.env` 内容；不得自动 push。

## 工具要求

Python 3、git、标准库优先。

## MCP 要求

N/A。

## Playwright 要求

N/A（gate 本身不跑浏览器；可检查 Playwright 是否安装）。

## 通用协议要求

exit code 0/1/2 对齐协议；报告路径 `docs/reports/agent_gate_report.md`。

## 具体任务

1. 实现/扩展检查项。
2. 输出 Markdown/JSON 报告。
3. 对齐 exit codes。
4. 文档化运行示例。
5. 自测 gate 在本仓库运行。

## 验收标准

1. `python3 scripts/agent_gate.py` 可运行。
2. BLOCKED 条件可触发（测试 .env tracked 检测逻辑）。
3. 报告写入正确路径。
4. 文档已同步。
5. 无 secrets 在 stdout。

## 安全检查

 suspected secrets 只报 path/line，不输出值。

## Git 提交要求

用户或 Prompt 要求时 commit。

## 最终报告格式

检查项列表、exit code 含义、样例输出、known warnings。
