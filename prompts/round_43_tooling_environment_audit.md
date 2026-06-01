# Round 43：Tooling Environment Audit

## Agent 身份

你是 Tooling Environment Audit Agent，负责检测并文档化本地与 CI 工具链就绪情况。

## 当前轮次

Round 43

## 本轮类型

`tooling`

## 背景

Round 44–46 依赖 Playwright 与可选 MCP；Round 47 依赖 Python/Node 与 git/gh。需要先知道环境缺口，避免硬阻塞无 fallback。

## 必读文件

- `docs/agent_tooling_strategy.md`
- `docs/mcp_playwright_setup_plan.md`
- `docs/roadmap_rounds_41_50_tooling_and_workbench.md`
- `scripts/agent_gate.py`（Round 41 产出）

## 允许修改

`scripts/tooling_environment_audit.py` 或扩展 agent_gate、`docs/reports/tooling_environment_audit.md`（本地）、`governance/repo_inventory.generated.json`（可选生成）。

## 禁止修改

不安装大型依赖（除非用户明确要求）；不修改业务翻译代码。

## 工具要求

Python、shell、which/version 探测。

## MCP / Playwright 要求

检测 Playwright CLI、Chromium、Cursor MCP 配置是否存在（只检测不强制安装）。

## 通用协议要求

运行 gate 与 protocol check（若已实现）并纳入审计报告。

## 具体任务

1. 检测 Python、Node、npm、git、gh（可选）版本。
2. 检测 pytest、Playwright 是否安装。
3. 检测 MCP 配置文件是否存在（Cursor/Claude Desktop 路径说明）。
4. 检测 frontend/ 是否可启动（若 Round 36–40 已完成）。
5. 生成结构化审计 JSON + Markdown 报告。
6. 列出 Round 44–47 各轮工具 prerequisite 与当前 gap。
7. 可选：实现 `scripts/scan_repo_inventory.py` 生成 inventory。
8. 更新 round_state。

## 验收标准

1. 审计脚本或报告可重复运行。
2. 报告含每项工具 present/missing/version。
3. gap 与 roadmap 轮次对应。
4. 不安装 Playwright（除非用户要求）。
5. 不调用真实 API。
6. 与 agent_gate 结果交叉引用。
7. 软阻塞项明确标注 fallback。

## 安全检查

不读取 `.env`；不执行 network 调用除非检测 gh auth 状态。

## Git 提交建议

`feat: add tooling environment audit`

## 最终报告格式

tool_matrix、gaps_by_round、recommended_next_installs、validation_results。
