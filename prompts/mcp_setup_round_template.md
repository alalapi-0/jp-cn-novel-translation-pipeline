# MCP Setup Round Template

## Agent 身份

你是 MCP Setup Agent，负责 MCP 安装规划、验证与 fallback 文档，不负责业务翻译。

## 本轮类型

`tooling`

## 必读文件

- `docs/mcp_playwright_setup_plan.md`
- `docs/agent_tooling_strategy.md`
- `docs/roadmap_rounds_41_50_tooling_and_workbench.md`
- `governance/agent_policy.yaml`

## 本轮目标

（填写 MCP 安装/验证目标）

## 允许修改

MCP 配置说明、验证脚本、相关文档、本地测试配置（不含 secrets）。

## 禁止事项

MCP 不得输出 API Key；不得读取展示 `.env`；不得自动公开发布译文；不得绕过 Git 审查。

## 工具要求

当前 Agent 环境的 MCP 配置能力、Playwright fallback。

## MCP 要求

明确 Option A/B/C/D；每步验证命令。

## Playwright 要求

若与 Playwright MCP 联动，说明安装前提。

## 通用协议要求

遵守 `browser_automation_policy` 与 MCP 安全规则。

## 具体任务

1. 确认环境是否支持 MCP。
2. 安装最小必要 MCP。
3. 编写验证步骤。
4. 文档化 fallback。
5. 更新 round_state。

## 验收标准

1. 验证步骤可执行或 fallback 已文档化。
2. 安全规则已检查。
3. 失败不阻塞非 MCP 依赖轮次。
4. 文档已更新。
5. 无 secrets 泄露。

## 安全检查

MCP 工具权限最小化。

## Git 提交要求

用户或 Prompt 要求时 commit；不提交 MCP 本地 secrets。

## 最终报告格式

MCP 列表、验证结果、fallback、blocked/warnings。
