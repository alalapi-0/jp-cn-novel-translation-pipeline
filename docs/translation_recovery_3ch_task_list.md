# Translation Recovery 3-Chapter Task List

> 配套主路线图：`docs/translation_recovery_3ch_roadmap.md`  
> 旧 20 章任务清单（deprecated）：`docs/translation_recovery_task_list.md`  
> 生成时间：2026-06-07（治理轮，未执行真实 API）
>
> **2026-06-11 live override**：D-MR-001…051 已完成；当前连续完成 355/613 章。下一任务固定为 **D-MR-052（356–358）**，除非 `local_scheduler_status.py --json` 给出更新结果。下方 D-MR-001 内容仅作历史定义。

## Current State

- **total chapters**: 613（`input_jp/*.md`）
- **draft completed chapters**: **355**（第 1–355 章连续完成）
- **current partial run**: 无
- **refinement completed chapters**: **170**（可导出 refined）
- **active worker**: 0
- **orphan worker**: 0（`check_orphan_workers.py` → CLEAN）
- **stale lock**: 0
- **default model**: `deepseek/deepseek-v4-pro`（Nemotron 暂不启用）
- **next draft micro round**: **D-MR-052**（第 356–358 章）
- **remaining draft MRs**: 86（D-MR-052 … D-MR-137）
- **state source**: `local_scheduler_status.py --json`（当前唯一执行真值）

### Legacy T-002 映射

| 旧 ID | 章节 | 新体系状态 |
| --- | --- | --- |
| T-001 | 171–190 | ✅ 完成（计入 draft 1–190） |
| T-002 | 191–210 | 部分完成 → 191–202 已并入 draft；203+ 由 D-MR-001 起接续 |

---

## Phase A：Draft Micro Rounds

> 完整 137 项列表见 `docs/translation_recovery_3ch_roadmap.md` §3.2。

### D-MR-001（COMPLETED；历史定义）

- **chapter range**: 203–205
- **resume**: `run_20260607_095821_draft_stage_b_50ch`（ch203 partial）
- **execution**: supervised tick loop, `--round-size 3`
- **pre-flight**: `pipeline_worker_registry --heal` 清理 stale lock
- **report**: `workspace/round_reports/D-MR-001/`

### D-MR-052（NEXT）

- **chapter range**: 356–358
- **execution**: `python3 scripts/local_scheduler_tick.py --dry-run` 先规划；真实执行按 FS-008 cost guard / pause / lock / orphan 规则
- **pre-flight**: `python3 scripts/check_orphan_workers.py --json` + `python3 scripts/throughput_gate.py --json`
- **report**: `workspace/round_reports/D-MR-052/`

### D-MR-002

- **chapter range**: 206–208

### D-MR-003

- **chapter range**: 209–211

### D-MR-004 … D-MR-137

- 每 3 章一轮，直至第 613 章
- 末批 D-MR-137：第 611–613 章（不足 3 章时收缩）

---

## Phase B：Progressive Consistency Audit

> Phase A 全书 draft 完成后执行。不全文硬扫。

### C-IDX-001：索引构建

- **phase**: consistency_audit
- **level**: 0–1
- **action**: 构建 chapter manifest + segment index
- **script**: `scripts/build_translation_indexes.py`（待实现）
- **output**: `workspace/consistency_audit/indexes/`

### C-TERM-001：术语冲突检查

- **level**: 2
- **action**: source→target / target→source 映射冲突统计
- **script**: `scripts/audit_translation_consistency.py`

### C-NAME-001：人名/角色名检查

- **level**: 2
- **action**: character name index 冲突

### C-SKILL-001：技能名检查

- **level**: 2
- **action**: skill name index 冲突

### C-LOCAL-001：局部冲突展开

- **level**: 3–4
- **action**: 仅展开冲突 segment；规则不足时调模型
- **script**: `scripts/select_conflict_segments.py`

### C-FIX-001：Fix Plan 生成

- **level**: 5
- **output**: `terminology_fix_plan.md`, `entity_conflicts.json`
- **script**: `scripts/generate_local_fix_plan.py`

---

## Phase C：Baseline Lock

### B-LOCK-001

- **enter when**: Phase B 无 blocking issue
- **action**: 生成 `draft_full_baseline_metadata.json`
- **user confirm**: 不需要

### B-LOCK-002

- **action**: 生成 `draft_full_baseline_go_decision.md`
- **gates**: failed/validation_failed 已清；术语可接受；无错位/漏段

---

## Phase D：Refinement Micro Rounds

> **冻结至 Phase C go**；当前 refined 170 章；新 MR 从 171 追平至 613。

共 **148** 个 micro round（R-MR-001 … R-MR-148）。完整列表见 roadmap §3.5。

### R-MR-001

- **chapter range**: 171–173
- **input**: draft baseline + glossary + consistency fix plan
- **execution**: supervised tick loop, `--round-size 3`

### R-MR-002 … R-MR-148

- 每 3 章一轮；末批可能不足 3 章

---

## Phase E：Progressive Refined Quality Audit

> Phase D 完成后执行。

### F-IDX-001

- **level**: 0–1
- **action**: refined metadata + diff/change_log index
- **output**: `workspace/final_review/indexes/`

### F-STAT-001

- **level**: 2
- **action**: 修改比例异常、过度润色候选

### F-LOCAL-001

- **level**: 3–4
- **action**: 原文/draft/refined 三方局部对比

### F-MODEL-001

- **level**: 4
- **action**: 规则无法判断时模型审查

### F-GO-001

- **output**: `refined_full_candidate_metadata.json`, `refined_full_candidate_go_decision.md`
- **note**: `production_candidate` 自动；`human_approved_final` 需用户确认

---

## Execution Rules

1. **执行单位 = 3 章 micro round**（`--round-size 3`），不再是 20 章。
2. **长 foreground worker 已废弃**；使用 supervised tick loop，每 tick 归还 Agent 控制权。
3. **detached background worker 禁止**用于真实 API（禁止 `nohup` / 裸 `&`）。
4. 每个 micro round：执行 → 报告 → gate 检查 → 修复 →（授权时）commit → 下一 MR。
5. 续跑优先 `--run-id` 已有 checkpoint（D-MR-001 续 `run_20260607_095821_draft_stage_b_50ch`）。
6. 启动前：`throughput_gate --json` + `check_orphan_workers.py` + lock heal。
7. 无硬阻塞时 **D-MR-001 → D-MR-002 → …** 自动衔接，无需人工确认。
8. Nemotron A/B 本轮不执行；保持 DeepSeek。

---

## Hard Blockers

1. API Key 缺失（真实 API 必须）
2. `MAX_TEST_COST_USD <= 0`
3. orphan worker 或 stale lock 未清理
4. checkpoint 与 `segments.json` 严重冲突
5. 无法推断 draft 进度
6. 续跑会覆盖已有完整 draft
7. `git diff` 含真实原文/译文
8. 连续 3 次同类修复失败
9. `human_approved_final` 未授权

---

## Git Policy

**可提交**：

- 本 Roadmap / Task List / 治理文档更新
- 检查脚本与 dry-run 统计摘要
- 程序修复（不含译文）

**不得提交**：

- 真实原文 / 译文
- `workspace/runs/` 大型内容
- `output_draft` / `output_refined` / `output_final`
- `.env` / token / cookie / API Key

**禁止** `git add .`；只 add 本轮相关文档与脚本。
