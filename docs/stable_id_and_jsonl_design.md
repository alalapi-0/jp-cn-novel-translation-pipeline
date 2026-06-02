# 稳定 ID 与 JSONL 中间态设计

## 6.1 为什么不能直接改原文

参考仓库的共同经验是：原文保持只读，译文进入中间态，校对、重译、润色围绕中间态进行，最终文件由 exporter 生成。

这样做可以避免三类风险：

1. 原文被清洗、替换或模型输出污染。
2. 重译、润色、人工校对失去可追溯依据。
3. 导出格式变化时反复改正文源文件。

当前项目应把 `input_jp/` 与 `input_cn/` 视为 source of record，把 JSONL 中间态视为 pipeline 工作对象，把 `output_cn/` 与 `output_jp/` 视为 exporter 产物。

## 6.2 paragraph_id

建议格式：

```text
p_{chapter_index:03d}_{paragraph_index:04d}
```

示例：

```text
p_001_0001
p_001_0002
p_002_0001
```

规则：

1. `chapter_index` 来自解析后的章节顺序。
2. `paragraph_index` 来自章节内段落顺序。
3. ID 必须写入 JSONL、ReviewIssue、TranslationMemory 和 Exporter 输出。
4. 重解析导致段落增删时必须生成 migration report，不静默复用错误 ID。
5. `JP_TO_CN` 与 `CN_TO_JP` 使用同一 ID 规则，但必须记录 `language_direction`。

## 6.3 segment_id

建议格式：

```text
seg_{chapter_index:03d}_{paragraph_index:04d}_{segment_index:02d}
```

示例：

```text
seg_001_0001_01
seg_001_0001_02
```

规则：

1. 默认一段一个 segment，长段才拆分。
2. `segment_id` 必须能回到 `paragraph_id`。
3. batch 翻译输出必须带 `segment_id`。
4. segment 拆分不能改变原文语义顺序。
5. failed segment 可单段重试，不影响同段其他 segment。

## 6.4 JSONL 示例

```json
{
  "project_id": "sample_project",
  "language_direction": "CN_TO_JP",
  "source_language": "zh",
  "target_language": "ja",
  "source_file_id": "file_001",
  "chapter_id": "ch_001",
  "paragraph_id": "p_001_0001",
  "segment_id": "seg_001_0001_01",
  "source_text": "这里是原文。",
  "source_text_hash": "sha256:...",
  "speaker": null,
  "text_type": "narration",
  "context_before_ids": [],
  "context_after_ids": [],
  "matched_term_ids": [],
  "matched_character_ids": [],
  "matched_world_bible_ids": [],
  "status": "untranslated",
  "translation_draft": null,
  "refined_translation": null,
  "locked": false,
  "human_reviewed": false,
  "prompt_version": null,
  "glossary_version": null,
  "character_profile_version": null,
  "style_profile_version": null,
  "provider_id": null,
  "model_id": null,
  "model_run_id": null,
  "validation_errors": [],
  "review_issues": [],
  "created_at": "",
  "updated_at": ""
}
```

## 6.5 状态机

| 状态 | 进入条件 | 退出条件 |
|------|----------|----------|
| `untranslated` | 解析生成，尚未进入队列 | 被选入任务后进入 `queued` |
| `queued` | 等待翻译 | provider 开始调用进入 `translating` |
| `translating` | 正在调用模型或等待输出 | 成功解析校验后进入 `translated`，异常进入 `failed` |
| `translated` | 初翻通过 Validator | 进入 `review_needed`、`refining` 或 `final` |
| `validation_failed` | 模型输出解析成功但校验失败 | 进入 `retry_pending` 或 `review_needed` |
| `failed` | provider 错误、超时、解析失败 | 进入 `retry_pending` 或 `review_needed` |
| `retry_pending` | 需要重试 | 重试开始进入 `queued` 或 `translating` |
| `review_needed` | 需要人工或强模型审核 | 审核后进入 `human_reviewed`、`refining` 或 `skipped` |
| `human_reviewed` | 人工确认过 | 可进入 `final` 或 `locked` |
| `refining` | 正在润色 | 通过校验进入 `refined`，失败进入 `validation_failed` |
| `refined` | 润色稿通过校验 | 人工确认后进入 `final` |
| `final` | 可进入最终导出 | 锁定后进入 `locked`，否则仅由人工/明确轮次回退 |
| `locked` | 用户锁定，不得自动覆盖 | 只能人工解锁 |
| `skipped` | 用户或规则跳过 | 只能人工恢复 |

## 写入规则

1. `validation_failed`、`failed` 和 `retry_pending` 不得写入 `translation_draft` 作为成功译文。
2. 可写入 `raw_output`、`validation_errors`、`review_issues`、`last_error` 和 `retry_count`。
3. `locked: true` 与 `human_reviewed: true` 默认跳过自动覆盖。
4. exporter 生成 final 文件时只能读取 `translated`、`refined`、`human_reviewed`、`final` 等允许状态。
