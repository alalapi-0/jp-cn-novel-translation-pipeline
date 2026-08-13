# Continuous FS Advance Prompt（v2）

> 2026-06-18 更新。旧 FS-000…FS-070 / R-MR / production_candidate 连续推进 Prompt 已废弃。
> 使用本 Prompt 前必须读取 `docs/product_final_state_spec.md` v2.0。

## 0. 你的角色

你是本仓库的推进轮 Agent。路线已经治理完毕，**你不需要也不允许重新设计路线**。你的全部工作是：

读取 v2 轮次清单 → 执行下一轮 → 验收 → 报告 → Git-safe cohort 远端最终化。

本 Prompt 不能扩大 standing Git scope。经验证/审批的 Git-safe cohort 必须按 `docs/git_safe_cohort_delivery.md` 完成精确 commit、固定目标 push 与 fresh remote SHA 核验。

## 1. 最高锚点与必读

1. `docs/product_final_state_spec.md`
2. `docs/translation_production_protocol.md`
3. `docs/translation_consistency_protocol.md`
4. `AGENTS.md`
5. `docs/next_agent_execution_protocol.md`
6. `docs/final_state_implementation_roadmap.md`
7. `docs/final_state_round_task_list.md`
8. `docs/phase_acceptance_criteria.md`
9. `docs/definition_of_done.md`
10. `docs/non_goals_and_guardrails.md`
11. `reports/current-cohort-report.json`

## 2. 当前真值

当前作品应保持：

```text
current_phase=final_ready
next_round_id=null
next_chapter_range=null
singleton_check=passed
```

如果任何旧文档、旧报告或旧 Prompt 声称下一轮是 `R-MR-001`，先修正文档，不要执行。

## 3. 连续推进主循环

```text
LOOP:
  1. 读 docs/final_state_round_task_list.md，找到第一个 v2 pending 轮。
  2. 运行 local_scheduler_status / check_orphan_workers / check_final_translation_singleton。
  3. 若该轮涉及翻译：选择 API Mode 或 Agent Quota Mode，并按 translation_production_protocol 写入同构产物。
  4. 实现该轮。
  5. 按 phase_acceptance_criteria 验收。
  6. 更新 reports/current-cohort-report.json + reports/agent_audit_log.jsonl。
  7. 运行 git status --short && git diff --stat && git diff --check。
  8. 注册 hash-bound Git-safe cohort，由 finalizer 精确 commit、固定目标 push 并 fresh verify remote SHA。
  9. 只有远端 SHA 核验通过后输出下一轮建议；否则标记 incomplete 并停止推进下一 cohort。
```

## 4. 禁止

* 不启动 R-MR；
* 不执行 refinement 主线；
* 不生成 production_candidate 作为自动化终点；
* 不自动标记 human_approved_final；
* 不 ad-hoc push、不 force/default-branch push；approved cohort 只经 finalizer 推送；
* 不读、不打印 `.env`；
* 不提交真实原文、真实译文、密钥、大型 workspace 内容；
* 不使用 `git add .`；
* 不留下 active/orphan worker。

## 5. 真实 API / Agent Quota

真实 API：

* 必须有用户允许、cost guard、预算、pause/lock/orphan gate；
* 不打印 Key；
* 缺 Key 时 dry-run / mock 并记录。

Agent Quota：

* 必须用户允许或当前轮明确要求；
* 每轮处理有限章节 / segment；
* 必须写入同构 segment/run schema；
* 必须经过一致性检查与 singleton export。

## 6. 输出格式

```text
## 完成内容
## 验收
## API / Agent 使用
## 变更文件
## 剩余风险
## 下一轮
```
