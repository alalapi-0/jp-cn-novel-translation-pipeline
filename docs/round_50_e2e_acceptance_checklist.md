# Round 50 端到端验收清单（概要）

受控试跑前须全部满足或已在 trial 报告中解释 WARN。

## 门禁与工具链

- [ ] `python3 scripts/agent_gate.py` → PASS 或 WARN 已记录
- [ ] `python3 scripts/check_protocol_standard.py` → 无 FAIL
- [ ] `npm run check:tooling`（或 gate + protocol + pytest）通过
- [ ] `npm run test:ui` Playwright smoke + issues spec 全绿
- [ ] 用户明确授权范围、预算、`MAX_TEST_COST_USD`（若启用真实 API）

## 流水线阶段

- [ ] Scan / 章节解析 checkpoint（fixture 或授权样章）
- [ ] Translate：dry-run 或受控 real API，cost guard 双开关
- [ ] Review：`run_quality_review.py` 生成 issue report，Workbench 可见
- [ ] Refine：不静默覆盖 `human_edited`
- [ ] Export：high issue 未人工确认时不标 final

## Workbench

- [ ] `/index.html` 项目入口
- [ ] `/issues.html` ≥3 类 issue 类型可筛选
- [ ] `/review.html` 对照 + segment 跳转
- [ ] 浏览器无 console error（Playwright 已覆盖）

## 向量与成本（若在本范围）

- [ ] `scripts/vector_db_inspect.py` 对试跑 index metadata
- [ ] cost 摘要 ≤ 批准上限

## 产物与 Git 安全

- [ ] 试跑输出仅在 gitignore workspace
- [ ] 无 `.env`/密钥/未授权原文进入 commit
- [ ] `docs/reports/round_50_controlled_trial_report.md` 含 go/no-go

## 字段更新

- [ ] `governance/round_state.yaml`：`real_api_called`、`full_translation_executed` 如实填写
