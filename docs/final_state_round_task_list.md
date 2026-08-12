# Final State Round Task List

> v2.0（2026-06-18）。最高锚点：`docs/product_final_state_spec.md` v2.0。
> 旧版中 Phase D refinement / R-MR / Phase E / production_candidate 任务已废弃，不再作为下一轮来源。

## 0. 当前真值

2026-07-13 对齐当前编号源文后实测：

```text
current_phase = final_ready
next_task = paused
next_round_id = null
next_chapter_range = null
draft_progress = 609/609
final_translation_progress = 609/609
active_worker_count = 0
orphan_worker_count = 0
final_translation = output_cn/translated/full_volume_cn.md
singleton_check = passed
```

`next_task=paused` 只表示调度器 pause file 生效；它不是待翻译任务。当前作品没有 R-MR 下一轮。

## 1. 已完成主线

| 范围 | 状态 | 说明 |
| --- | --- | --- |
| FS-000 | completed | 治理与基线对齐 |
| FS-001…FS-007 | completed | 本地调度器、pause/lock/orphan/tick/status |
| FS-008…FS-010 | completed | 全书翻译完成，当前编号源文 609/609 |
| FS-011…FS-016 | completed | configs 资产层、术语库内核、prompt 资产注入 |
| FS-031…FS-037 | completed | 一致性检查工具链 |
| FS-038…FS-039 | completed | baseline lock、go decision |
| 2026-06-18 governance cleanup | completed | final singleton export、旧日志清理、旧路线废弃 |

## 2. 当前有效下一轮

### FS-v2-001：Agent Quota Translation Writer

**目标**：实现 `docs/translation_production_protocol.md` 中的 Agent Quota Mode 写入器，让后续新作品可以直接使用 Agent 自身额度翻译，并写入与 API Mode 同构的 segment/run schema。

**输入**：

* `docs/product_final_state_spec.md`
* `docs/translation_production_protocol.md`
* `src/translation/`
* `scripts/run_micro_round.py`
* 现有 run metadata / segments schema

**验收**：

* Agent quota 输出含 `execution_mode=agent_quota_translation`；
* 输出可被一致性检查脚本消费；
* 不读 `.env`；
* 不调用真实 API；
* 有 fixture 测试。

### FS-v2-002：UI Status Vocabulary v2.0

**目标**：把 Web UI 和后端状态文案从 old refinement/prod-candidate 口径改为 v2.0。

**验收**：

* Dashboard 显示 `final_ready`；
* 不显示 R-MR 作为下一任务；
* API / Agent 执行模式清楚区分；
* Playwright 浏览器检查通过。

### FS-v2-003：User Revision Sync MVP

**目标**：上传用户修改稿，生成 diff / sync plan，经确认后写入 TM / glossary / revised output。

**验收**：

* 确认前无副作用；
* 禁写原文、baseline、human_approved_final；
* sync plan schema 有测试；
* UI 有危险操作二次确认。

### FS-v2-004：Auxiliary Export Package

**目标**：在唯一最终译文之外，按需生成辅助导出包（TXT / EPUB / 双语对照 / glossary / character / world / TM / reports）。

**验收**：

* 辅助导出不改变 singleton final；
* `check_final_translation_singleton.py` 仍 PASS；
* 导出页显示文件清单和 final/non-final 区分。

## 3. Legacy 任务处理

以下旧任务不得作为下一轮：

```text
FS-040…FS-045 old Phase D refinement / R-MR
FS-046…FS-050 old Phase E / production_candidate
```

旧代码若仍保留，只能用于历史诊断或 fixture，不得由 scheduler planner 自动执行。

## 4. 每轮启动命令

```bash
python3 scripts/local_scheduler_status.py --json
python3 scripts/check_orphan_workers.py --json
python3 scripts/check_final_translation_singleton.py --json
```

期望当前作品状态：

```text
current_phase=final_ready
next_round_id=null
next_chapter_range=null
orphan_worker_count=0
singleton_check=passed
```

如果任何文档或报告声称下一轮是 `R-MR-001`，先修正文档，不要执行。

## 5. 禁止项

* 不启动 R-MR；
* 不生成 production_candidate 作为自动化终点；
* 不保留多份最终译文；
* 不覆盖 baseline；
* 不自动标记 human_approved_final；
* 不读、不打印 `.env`；
* 不提交真实正文或密钥；
* 不使用 `git add .`。
