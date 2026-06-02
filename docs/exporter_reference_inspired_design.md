# Exporter 设计：中间态到最终阅读文件

Exporter 是唯一负责生成最终阅读文件的模块。

## 输出类型

1. Markdown 纯译文。
2. Markdown 双语对照。
3. CSV review。
4. JSON review。
5. EPUB，后期。
6. Web review data。

## 基本原则

1. exporter 不调用模型。
2. exporter 不修改原文。
3. exporter 不导出 `validation_failed` 到 final。
4. exporter 可以导出 draft 供审核。
5. exporter 保留 `paragraph_id`。
6. exporter 支持章节声明和出处 URL。
7. exporter 支持后续 EPUB translate + fill。

## 输入

```yaml
project:
language_direction:
source_manifest:
jsonl_intermediate:
translation_drafts:
refined_translations:
review_issues:
export_options:
```

## 输出

```yaml
export_job_id:
export_type:
output_path:
included_statuses:
excluded_statuses:
source_segment_count:
exported_segment_count:
skipped_segment_count:
warnings:
created_at:
```

## Markdown 纯译文

用途：阅读和人工快速检查。

规则：

1. 默认使用 `final` 或 `human_reviewed`。
2. 可配置使用 `refined` 或 `translated` 生成 draft。
3. 不包含 `validation_failed`、`failed`、`retry_pending`。
4. 可在注释或 HTML comment 中保留 `paragraph_id`。

## Markdown 双语对照

用途：审核、校对和 diff。

规则：

1. 保留原文和译文并列。
2. 保留 `paragraph_id` / `segment_id`。
3. 标记 status、review issue 和 locked 状态。
4. 对 draft 输出必须明确标注“非最终稿”。

## CSV / JSON Review

用途：前端、表格工具、人工 issue 管理。

字段建议：

```yaml
project_id:
language_direction:
chapter_id:
paragraph_id:
segment_id:
source_text:
translation_draft:
refined_translation:
status:
validation_errors:
review_issues:
locked:
human_reviewed:
```

## EPUB 后期

EPUB 不作为 MVP 主线。后期采用 translate + fill：

1. 解析 EPUB，抽取文本 segment 与结构位置。
2. 用纯文本 pipeline 翻译。
3. 通过 ID 回填到 EPUB 结构。
4. Validator 检查 tag 和 ID 不丢。
5. Exporter 负责回填，不让模型接触 HTML tag。

## Web Review Data

Web Review Workbench 应读取 exporter 或 review data contract 产物，不直接读真实原文目录。前端写回应通过受控 action 更新中间态或 review issue。

## 验收标准

1. exporter-only 原则明确。
2. exporter 不调用 provider。
3. exporter 不修改 `input_jp/` 或 `input_cn/`。
4. `validation_failed` 不进入 final。
5. 输出保留 `paragraph_id` 和章节顺序。
