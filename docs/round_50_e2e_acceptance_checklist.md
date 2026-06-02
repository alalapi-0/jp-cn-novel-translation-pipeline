# Round 50 端到端验收清单（概要）

受控试跑前须全部满足或已在 trial 报告中解释 WARN。

> Round 50 完成于 2026-06-02：fake provider 受控试跑 PASS；详见本地 `docs/reports/round_50_controlled_trial_report.md`（gitignored）。

## 门禁与工具链

- [x] `python3 scripts/agent_gate.py` → PASS 或 WARN 已记录
- [x] `python3 scripts/check_protocol_standard.py` → 无 FAIL
- [x] `npm run check:tooling`（或 gate + protocol + pytest）通过
- [x] `npm run test:ui` Playwright smoke + issues spec 全绿
- [x] 用户明确授权范围、预算、`MAX_TEST_COST_USD`（若启用真实 API）— 本轮 fake only，cost=0

## 流水线阶段

- [x] Scan / 章节解析 checkpoint（fixture 或授权样章）
- [x] Translate：dry-run 或受控 real API，cost guard 双开关 — fake provider
- [x] Review：`run_quality_review.py` 生成 issue report，Workbench 可见
- [x] Refine：不静默覆盖 `human_edited`
- [x] Export：high issue 未人工确认时不标 final

## Workbench

- [x] `/index.html` 项目入口
- [x] `/issues.html` ≥3 类 issue 类型可筛选（fixture report）
- [x] `/review.html` 对照 + segment 跳转
- [x] 浏览器无 console error（Playwright 已覆盖）

## 向量与成本（若在本范围）

- [x] `scripts/vector_db_inspect.py` 对试跑 index metadata
- [x] cost 摘要 ≤ 批准上限（actual paid USD = 0）

## 产物与 Git 安全

- [x] 试跑输出仅在 gitignore workspace
- [x] 无 `.env`/密钥/未授权原文进入 commit
- [x] `docs/reports/round_50_controlled_trial_report.md` 含 go/no-go

## 字段更新

- [x] `governance/round_state.yaml`：`real_api_called`、`full_translation_executed` 如实填写
