# ResponseExtractor 与 Validator 设计

## 10.1 ResponseExtractor

ResponseExtractor 的职责：

1. 解析 JSON。
2. 解析编号文本。
3. 提取 `segment_id`。
4. 提取 `translation`。
5. 提取 `notes`。
6. 保存 raw output。
7. 标记 parse error。
8. 生成 structured result。

输入：

```yaml
model_run_id:
raw_output:
expected_segment_ids:
output_contract:
prompt_version:
```

输出：

```yaml
parse_status:
items:
  - segment_id:
    translation:
    notes:
parse_errors:
raw_output_ref:
```

解析顺序：

1. 尝试 JSON parse。
2. 若失败，尝试 fenced JSON 提取。
3. 若仍失败，尝试编号文本 fallback。
4. 若仍失败，输出 `parse_status: failed`，仅保存 raw output。

## 10.2 Validator

必须检查：

| 检查项 | 目的 |
|--------|------|
| `non_empty` | 译文不能为空 |
| `segment_id_coverage` | 所有期望 segment 必须覆盖 |
| `no_extra_segment` | 不允许多余 segment |
| `locked_terms_preserved` | locked 术语必须遵守 |
| `placeholder_preserved` | 占位符必须保留并可还原 |
| `control_symbols_preserved` | 控制符、格式符不能丢 |
| `source_language_residual` | 目标译文中不应异常残留源语言 |
| `target_language_residual` | 方向检查，避免语言方向混乱 |
| `length_ratio` | 粗略检查异常过短/过长 |
| `line_break_consistency` | 保留必要换行 |
| `paragraph_alignment` | 段落/segment 对齐 |
| `character_name_consistency` | 角色姓名一致 |
| `honorific_consistency` | 敬语和称呼一致 |
| `style_profile_basic_check` | 基本文体约束 |
| `prompt_contract_compliance` | 输出契约合规 |

Validator 输入：

```yaml
structured_result:
context_pack:
glossary:
character_profiles:
world_bible:
validation_policy:
```

Validator 输出：

```yaml
validation_status:
errors:
  - error_type:
    severity:
    segment_id:
    message:
    suggested_action:
review_issues:
retry_recommended:
```

## 10.3 校验失败不写入

必须明确：

`validation_failed` 的结果不能写入 `translated` / `final`。

只能写入：

1. raw output。
2. validation_errors。
3. review_issues。
4. retry_pending。

落盘规则：

1. `parse_status: failed`：不写 `translation_draft`。
2. `validation_status: failed`：不写 `translation_draft` 作为成功译文。
3. 可选保存 `raw_output_ref`，供人工排查。
4. 若用户明确选择人工采用，需要进入 `human_reviewed` 流程，而不是自动标记成功。

## 10.4 单段回退

吸收 BallonsTranslator / SakuraLLM 思路：

1. batch 失败时可拆小。
2. 单段失败时可单段重译。
3. 重试次数有限。
4. 多次失败后进入 `human_review_needed`。

建议重试策略：

```yaml
max_retry_count: 3
retry_order:
  - same_prompt_same_batch
  - same_prompt_smaller_batch
  - single_segment_retry
  - human_review_needed
```

## ReviewIssue 映射

Validator error 必须映射到统一 taxonomy：

- 缺 segment -> `SEGMENT_ALIGNMENT_ERROR`
- locked 术语错误 -> `LOCKED_TERM_VIOLATION`
- 占位符丢失 -> `PLACEHOLDER_LOST`
- 输出契约错误 -> `PROMPT_CONTRACT_VIOLATION`
- 源语言残留 -> `SOURCE_LANGUAGE_RESIDUAL`

## 验收标准

1. JSON 和编号 fallback 都可解析。
2. raw output 可追踪。
3. 缺失、多余、空译文可发现。
4. 校验失败不会写入成功译文。
5. validation error 能生成 ReviewIssue。
