# Translation Recovery Task List

> 基于 2026-06-07 仓库只读诊断生成；章节数为统计值，不含正文。

## 当前状态

- **draft completed chapters**: **190**（第 1–190 章初翻完成，T-001 验收通过）
- **refinement completed chapters**: 170（全段 draft + refined，可导出）
- **current stage**: Phase A — 恢复初翻（T-001 完成，待启动 T-002）
- **active worker**: 无
- **latest run**: `run_20260607_040204_draft_stage_b_50ch`（171–190，3353/3353 段，`status=completed`）
- **known blockers**:
  - 润色落后初翻 20 章（171–190 新 draft）— **非阻塞**，初翻优先
  - 部分必读文档缺失：`docs/priority_matrix.md`、`docs/roadmap_converged_core_first.md`（已记录）
  - 轮次报告 `source_residual` 启发式含汉字误判 — 记入 Phase B 一致性检查

---

## Phase A：Draft Translation Recovery Tasks

### T-001（已完成）

- **chapter range**: 171–190（20 章）✅
- **input**: `input_jp/` offset=170，`limit-chapters=20`
- **output**: `workspace/runs/run_20260607_040204_draft_stage_b_50ch/`
- **API mode**: real；本轮 API calls=99，增量 cost≈$0.077，累计 checkpoint≈$0.51
- **report**: `workspace/round_reports/T-001/translation_round_report.{md,json}`
- **fixes**: `resume_production` 子进程 `CONTROLLED_RUN_ENABLED` 传递；新增恢复脚本 trio

### T-002（下一轮）

- **chapter range**: 191–210
- **input**: offset=190，新 `run_id`
- **output**: 新 run 目录 + 本地 draft 导出
- **API mode**: real
- **checks**: T-001 报告 `continue`；gate 非 BLOCK
- **report**: `workspace/round_reports/T-002/`
- **git policy**: 同上

### T-003 … T-FINAL

- 每轮 +20 章，直至 ~612 章源文全部初翻完成
- 末轮不足 20 章时范围收缩，须在报告中标注

---

## Phase B：Full Draft Consistency Audit Tasks

- **进入条件**: draft_completed ≥ 全书章节
- **执行**: `python3 scripts/audit_translation_consistency.py`
- **输出**: `workspace/consistency_audit/*`
- **git policy**: 可提交脚本与脱敏摘要；不提交审计中的真实译文片段

---

## Phase C：Consistency Fix And Baseline Lock Tasks

1. 根据 Phase B 修正 glossary / character_profile / validator / prompt
2. 局部 segment 重译（如需）
3. 重跑一致性检查直至通过
4. 生成 `draft_full_baseline_metadata.json` + go decision

---

## Phase D：Refinement Recovery Tasks

> **冻结至 Phase C 完成**；下列为规划占位。

### R-001

- **chapter range**: 001–020（历史已 refined，可能仅需验收）
- **input**: draft baseline + glossary
- **output**: `refined/` + diff + change_log
- **API mode**: real
- **diff**: `draft_vs_refined_diff.json`
- **report**: `workspace/round_reports/R-001/`
- **git policy**: 不提交 refined 正文

### R-002 … R-FINAL

- 每轮 20 章，从当前 refined 缺口（171+）追平至全书

---

## Phase E：Final Refined Quality Review Tasks

- 全书润色完成后执行
- 输出 `workspace/final_review/*` + `refined_full_candidate_*`
- **不**自动 final

---

## 自动继续规则

1. 轮次报告 `continue_decision=continue`
2. `throughput_gate.decision != BLOCK`
3. 无 active translate worker 冲突
4. API Key + cost guard 就绪
5. 下一轮章节范围已确定且不覆盖已有完整 draft

## 硬阻塞规则

1. API Key 缺失（真实 API 必须）
2. `MAX_TEST_COST_USD <= 0`
3. 并发 translate worker / 无法获取 lock
4. checkpoint 与 `segments.json` 严重冲突
5. 无法推断 `draft_completed_chapters`
6. `git diff` 含真实原文/译文
7. 连续 3 次同类修复失败
8. 需用户确认质量问题或 final 标记
