# Round 50：End-to-end Agent-assisted Controlled Translation Trial

## Agent 身份

你是 E2E Trial Agent，负责在 Agent 工具链辅助下用**短篇样例**完成受控闭环试跑，不是生产长篇翻译。

## 当前轮次

Round 50

## 本轮类型

`e2e validation` / `translation_execution`（受控）

## 背景

Round 41–49 应已交付 gate、protocol check、Playwright、cost guard、quality workbench。Round 50 用样例验证：导入 → 术语 → 初翻（fake/dry-run 或用户授权 controlled）→ 审核 → 润色 → 前端查看 → 导出。

## 必读文件

- `docs/roadmap_rounds_41_50_tooling_and_workbench.md`
- `docs/batch_translation_workflow.md`
- `docs/agent_operating_manual.md`
- `governance/novel_pipeline_contract.yaml`
- Round 41–49 产出与 Prompt

## 允许修改

workspace 试跑产物、manifest、checkpoint、本地报告、样例 data/examples 文本。

## 禁止修改

不提交真实版权长篇；无授权不调用真实 paid API；不 promote generated 为 fixed asset 无人工确认。

## 工具要求

agent_gate、protocol check、fake/dry-run provider、Playwright（可选）、frontend、export script。

## MCP / Playwright 要求

试跑结束后浏览器打开 Workbench 查看结果（若 UI 存在）；MCP 可选。

## 通用协议要求

full trial 前 agent_gate exit 0 或 documented WARNING；cost guard 启用。

## 具体任务

1. 准备 synthetic 短篇样例（`data/examples/`，非仓库内真实 copyright 长篇）。
2. 运行 ingest/manifest → parse（可用已有或最小脚本）。
3. 跑 terminology/character 候选（fake 或规则型）。
4. 初翻使用 fake provider 或用户授权的 controlled run。
5. 生成 review issues（Round 49 checker）。
6. 润色 diff 写入 workspace（不覆盖 git 跟踪译文）。
7. 前端或报告查看对照与 issues。
8. export 到 workspace 非 git 跟踪路径。
9. 全文 trial 报告：每步工具、exit code、成本（应为 0 若 fake）。
10. 更新 round_state 标记 Round 50 与 next phase。

## 验收标准

1. 样例从 import 到 export 链路有 documented 证据。
2. agent_gate 与 protocol check 已运行并附结果。
3. 无未授权 real API 费用（或 controlled 预算是 user approved）。
4. 无 `.env`/原文/译文误 commit。
5. Workbench 或报告可复查至少 1 章对照。
6. issue 列表非空或 documented empty reason。
7. 硬阻塞项为零或已全部报告。
8. 下一轮建议写入 roadmap 或 project.yaml。

## 安全检查

样例文本 synthetic；checkpoint 不含 secrets；export 路径 gitignored。

## Git 提交建议

`docs: record round 50 controlled e2e trial report`（代码改动与报告分离；敏感报告本地）

## 最终报告格式

trial_scope、pipeline_steps、tooling_used、gate_results、cost_summary、artifacts_paths、regressions、recommended_next_phase。
