# Translation Recovery 20-Chapter Roadmap

> 主路线图：在现有仓库成果上恢复真实 API 初翻，按 **20 章/轮** 稳定推进至全书初翻完成 → 一致性检查 → 润色 → 最终候选质量检查。  
> 生成时间：2026-06-07（恢复 Agent 首轮）

## 当前快照（只读统计，不含正文）

| 指标 | 值 | 来源 |
| --- | --- | --- |
| 全书源文章节（`input_jp`） | ~612 | `ls input_jp/*.md` |
| 初翻完成章（全 run 合计） | **190** | `throughput_gate` / `segments.json`（T-001 完成后） |
| 可导出润色章 | **170** | `throughput_gate` |
| 当前阶段 | Phase A（恢复初翻） | `workspace/stage_state.json` |
| 活跃 worker | 无（已 heal stale） | `pipeline_worker_registry --heal` |
| 可恢复 run | `run_20260607_040204_draft_stage_b_50ch` | offset=170，checkpoint `in_progress` |
| API Key | 已配置 | `throughput_gate.has_api_key` |
| Cost guard | `MAX_TEST_COST_USD=5.0` | 环境变量 |

**权威初翻进度**：以各 Stage B run 的 `segments.json` 中「全段 `draft_text` 非空」计章，合计 **186 章**（第 1–186 章初翻完成）。  
**润色进度**：可导出 refined 章 **170**（第 1–170 章）。润色 backlog（151–170）保留状态，**本轮不优先推进润色**。

---

## Phase A：恢复初翻

**目标**：从第 187 章继续，以每轮最多 20 章完成全书初翻（~612 章）。

### 规则

1. 自动识别 `draft_completed_chapters`，从 **下一章** 起算。
2. 每轮默认 **20 章**；成本/失败率过高时可临时降为 10 章，须在轮次报告中说明。
3. 每轮使用真实 API（`REAL_API_TESTS_ENABLED` + `OPENROUTER_API_KEY` + `MAX_TEST_COST_USD>0`）。
4. 单阶段仅 **一个** authoritative translate worker；续跑优先 `--run-id` 已有 checkpoint。
5. 每轮必须有 checkpoint / `run_progress` / 本地 `draft/` 导出。
6. 每轮生成 `workspace/round_reports/<round_id>/translation_round_report.{md,json}`。
7. 每轮结束修复程序问题；代码/文档可提交 Git，**不得**提交真实译文。

### 轮次规划（Phase A）

| Round ID | 章节范围 | 状态 | run_id / 备注 |
| --- | --- | --- | --- |
| **T-001** | 171–190 | **已完成** | `run_20260607_040204`（3353 段，99 API calls） |
| **T-002** | 191–210 | **待执行** | 新 run，offset=190 |
| T-003 | 211–230 | 待执行 | offset=210 |
| … | +20 章/轮 | 待执行 | 直至 ~612 章 |
| T-FINAL | 剩余 <20 章 | 待执行 | 末批 |

### T-001 执行要点

- **不**从头重跑 171–186（checkpoint + `segments.json` 已有 16 章完整 draft）。
- 使用 `scripts/run_translation_recovery_round.py --round-id T-001` 或 `resume_production.py --target-new-chapters 20`。
- 本轮完成后初翻应达 **190 章**。

---

## Phase B：全书初翻一致性检查

**进入条件**：`draft_completed_chapters >= 全书章节数`（或用户确认末章已译）。

**目标**：术语 / 人名 / 技能名 / 地名 / 组织名 / 道具名 / 称号 / 特有名词一致性审计。

**工具**：`python3 scripts/audit_translation_consistency.py`

**输出**：

- `workspace/consistency_audit/full_draft_consistency_report.md`
- `workspace/consistency_audit/full_draft_consistency_report.json`
- `workspace/consistency_audit/terminology_fix_plan.md`
- `workspace/consistency_audit/entity_conflicts.json`

**原则**：先修 glossary / character_profile / validator / prompt，**不**手改全书译文；必要时局部 segment 重译。

---

## Phase C：一致性修复与 baseline draft 锁定

**目标**：根据 Phase B 修正结构化资产与程序逻辑，锁定可用于润色的 draft baseline。

**输出**：

- `draft_full_baseline_metadata.json`
- `draft_full_baseline_go_decision.md`

---

## Phase D：20 章一轮润色

**进入条件**：baseline draft 已锁定（Phase C go）。

**规则**：每轮 20 章；基于 source + draft baseline + glossary + consistency fix plan；生成 refined / diff / change_log / refinement_quality_report。

| Round ID | 章节范围 | 状态 |
| --- | --- | --- |
| R-001 | 001–020 | 待执行（当前 refined 已达 170，历史轮次已部分完成） |
| … | +20 章/轮 | 待执行 |
| R-FINAL | 剩余 <20 章 | 待执行 |

**本轮策略**：初翻完成前 **不启动** 新润色轮；已有润色进度仅保留。

---

## Phase E：全书润色质量检查

**进入条件**：全书 refined 完成。

**输出**：

- `workspace/final_review/full_refined_quality_report.md`
- `workspace/final_review/full_refined_quality_report.json`
- `refined_full_candidate_metadata.json`
- `refined_full_candidate_go_decision.md`

**注意**：生成 `production_candidate`，**不**自动 `final`；需用户确认。

---

## 每轮必答清单

每轮结束须能回答：

1. 本轮处理了哪 20 章？
2. 真实 API 调用多少次？成功/失败章数？
3. 有无重试 / 卡点 / validation_failed？
4. 质量与程序 / UI / 工具问题？
5. 修了什么？提交了什么？
6. 下一轮从哪里继续？

---

## 硬阻塞（暂停下一轮）

- API Key 缺失且必须真实 API
- cost guard 缺失
- active worker 冲突
- 无法确定已完成章节
- 续跑会覆盖已有译文
- Git 将纳入真实原文/译文

## 参考命令

```bash
# 状态与 gate
python3 scripts/throughput_gate.py --json
python3 scripts/pipeline_worker_registry.py --heal --json

# 执行一轮初翻（示例 T-001）
python3 scripts/run_translation_recovery_round.py --round-id T-001 --phase draft

# 生成轮次报告
python3 scripts/generate_translation_round_report.py --round-id T-001

# 一致性检查（Phase B）
python3 scripts/audit_translation_consistency.py
```
