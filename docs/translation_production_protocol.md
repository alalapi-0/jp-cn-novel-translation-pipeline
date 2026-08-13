# Translation Production Protocol

> v1.0（2026-06-18）。本协议配合 `docs/product_final_state_spec.md` v2.0 使用，是后续作品翻译执行的主路径说明。若旧 Roadmap / Round Report 要求 refinement、R-MR 或 production_candidate，以本协议和最终规格为准。

## 1. 生产终点

自动化生产终点是：

```text
output_cn/translated/full_volume_cn.md
output_cn/final_export_manifest.json
reports/final_translation_singleton_check.json
```

默认只保留一份最终译文。分章译文、双语导出、Workbench 临时导出均为可再生成辅助产物，不作为最终版本保留。

## 2. 标准流程

```text
Import Source
→ Build stable chapter / paragraph / segment ids
→ Translate by API mode or Agent quota mode
→ Run deterministic validation
→ Run consistency audit
→ Apply approved deterministic/local fixes
→ Lock baseline
→ Export singleton final translation
→ Run singleton check
→ Optional human_approved_final by user only
```

不再存在必经的 refinement / R-MR / production_candidate 阶段。

## 3. 执行模式

### API Mode

用于外部真实 API 生产翻译。

必须满足：

* 用户允许真实 API；
* cost guard 生效；
* `max-api-calls`、`max-segments` 或 wall-time budget 至少一个生效；
* pause / lock / orphan gates 全部通过；
* 不打印、不提交 API Key；
* 每批输出必须进入统一 segment schema；
* 失败 segment 不得污染 final export。

### Agent Quota Mode

用于直接使用当前 Agent 自身额度完成翻译。

必须满足：

* 用户明确允许或当前任务明确要求；
* 每轮只处理有限章节 / segment；
* 翻译结果必须写入与 API Mode 同构的 `segments.json` / run metadata；
* 必须记录 `execution_mode=agent_quota_translation`；
* 必须保留 stable ids；
* 必须经过一致性检查和 singleton export；
* 不得把聊天文本直接复制成最终交付文件。

### Mock / Dry Run Mode

用于测试、治理、UI 和门禁，不得伪装成真实翻译。

## 4. 统一产物契约

无论译文来自 API 还是 Agent，后续步骤只认结构化产物：

```yaml
chapter_id:
paragraph_id:
segment_id:
source_text:
draft_text:
status:
provider:
model:
execution_mode:
run_id:
created_at:
updated_at:
```

允许的 `execution_mode`：

```text
api_translation
agent_quota_translation
mock
dry_run
```

## 5. 一致性门禁

翻译完成后必须运行：

```bash
python3 scripts/run_consistency_fix_all.py --dry-run
python3 scripts/audit_actual_chapter_content.py --chapters 1 612 --output <report>.json
python3 scripts/build_term_variant_report.py --chapters 1 612 --output <report>.json
python3 scripts/export_consistency_final_volume.py --json
python3 scripts/check_final_translation_singleton.py --json
```

对新作品，章节范围按实际章节数替换。不得硬编码 612。

## 6. 局部修正规则

只允许以下自动修正：

* 已锁定且 source-guarded 的术语替换；
* 明确占位符恢复；
* 明确格式修复；
* 明确漏段补译；
* 用户确认过的局部重译。

禁止：

* 无证据全局替换；
* 改写 human_edited segment；
* 为追求“文采”做全书润色；
* 未经用户确认切换成更贵模型；
* 生成多份互相竞争的最终译文。

## 7. 调度语义

`local_scheduler_status.py --json` 的主线 phase：

```text
draft
consistency
final_export
final_ready
```

`baseline_lock`、`refinement`、`final_review`、`production_candidate` 为 legacy phase，不得作为下一轮主任务。

## 8. 新作品启动清单

1. 导入原文并生成 stable ids。
2. 建立或导入 glossary / character_profile / style_profile。
3. 选择 API Mode 或 Agent Quota Mode。
4. 设定每轮范围和预算。
5. 执行翻译。
6. 执行一致性检查。
7. 导出 singleton final translation。
8. 运行 singleton check。
9. 更新 current-cohort-report 和 round_state。

## 9. Done

生产翻译 Done：

* 全部章节 completed；
* failed / blocking validation_failed 为 0；
* consistency dry-run changed_segments 为 0；
* term variance 为 0；
* singleton check passed；
* no active worker；
* no orphan worker；
* 最终译文只有一份；
* 未标记 human_approved_final；
* 未对外发布。
