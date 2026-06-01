# Round 45：Playwright MCP Integration

## Agent 身份

你是 MCP Integration Agent，负责配置并验证 Playwright MCP，或建立等价 fallback。

## 当前轮次

Round 45

## 本轮类型

`tooling`

## 背景

Round 44 应已安装 Playwright CLI。Cursor 等 Agent 环境可通过 MCP 直接操作浏览器；若 MCP 不可用必须有 fallback。

## 必读文件

- `docs/mcp_playwright_setup_plan.md`
- `docs/agent_tooling_strategy.md`
- `prompts/mcp_setup_round_template.md`
- Round 44 产出（playwright config、smoke tests）

## 允许修改

MCP 配置说明（文档化路径，不提交 secrets）、验证脚本、fallback 文档、`governance/round_state.yaml`。

## 禁止修改

MCP 不得输出 API Key；不得读取展示 `.env`；不得自动发布译文。

## 工具要求

Round 44 Playwright 安装、当前 Agent 环境的 MCP 支持。

## MCP / Playwright 要求

尝试 Option A（Cursor MCP）或 Option D（Playwright script fallback）；记录 Option B/C 供其他环境。

## 通用协议要求

遵守 MCP 安全 7 条（见 mcp_playwright_setup_plan.md）。

## 具体任务

1. 确认 Agent 环境是否支持 MCP browser/playwright。
2. 若支持：文档化最小 MCP 配置与验证步骤（snapshot 首页）。
3. 若不支持：文档化 Playwright CLI fallback 流程。
4. 编写 MCP 验证 checklist（10 项内）。
5. 与 Round 46 页面清单对齐（术语、对照、diff 页）。
6. 更新 `docs/mcp_playwright_setup_plan.md` 实测结果节。
7. 运行 agent_gate；记录 WARNING 若 MCP 缺失但 fallback OK。
8. 更新 round_state。

## 验收标准

1. MCP 或 fallback 至少一条路径 verified。
2. 安全规则已写入验证清单。
3. MCP 失败不标记为 Round 45 硬阻塞（若有 fallback）。
4. 文档含逐步验证命令。
5. 无 secrets 在报告或 commit 中。
6. 未绕过 Git 审查流程。
7. 下一步 Round 46 前置条件明确。

## 安全检查

MCP 权限最小化；禁止自动 external publish。

## Git 提交建议

`docs: validate playwright mcp integration and fallback`

## 最终报告格式

mcp_supported、option_used、verification_steps、fallback_path、blocked_warnings。
