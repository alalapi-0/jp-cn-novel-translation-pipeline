# Cache、Checkpoint 与 Translation Memory 设计

本项目必须严格区分 Checkpoint、LLM Response Cache 和 Translation Memory。三者解决的问题不同，不得混用。

## 11.1 Checkpoint

Checkpoint 解决：

任务中断后从哪里继续。

典型字段：

```yaml
checkpoint_id:
project_id:
language_direction:
pipeline_stage:
chapter_id:
segment_id:
status:
retry_count:
last_error:
updated_at:
```

Checkpoint 关注任务状态，不保证译文质量，不用于复用译法。

## 11.2 LLM Response Cache

LLM Response Cache 解决：

相同请求是否避免重复调用 API。

典型字段：

```yaml
cache_key:
request_hash:
provider_id:
model_id:
prompt_version:
raw_response_ref:
created_at:
expires_at:
```

LLM cache 保存模型响应，不代表译文已通过校验，也不代表推荐译法。

## 11.3 Translation Memory

Translation Memory 解决：

历史译法如何复用。

典型字段：

```yaml
tm_id:
project_id:
language_direction:
source_text:
target_text:
source_text_hash:
segment_id:
speaker_character_id:
term_ids:
quality_status:
review_status:
prompt_version:
created_at:
updated_at:
```

TM 只有在译文通过校验或人工确认后才应进入可推荐状态。

## 11.4 MVP

MVP 使用 JSONL status 实现轻量断点：

1. JSONL status。
2. progress summary。
3. failed list。
4. skip translated。
5. skip locked。
6. skip human_reviewed。

MVP 不要求 SQLite、hash cache 或向量检索。

## 11.5 Phase 2

1. SQLite checkpoint。
2. failed 优先重试。
3. `retry_count`。
4. `last_error`。
5. model_run record。

SQLite 作为可选增强，不取代 JSONL 的可读中间态。可设计 JSONL -> SQLite 与 SQLite -> JSONL 的同步/导出能力。

## 11.6 Phase 3

1. LLM response hash cache。
2. cache key 包含：
   - `source_text_hash`
   - `prompt_version`
   - `glossary_version`
   - `character_profile_version`
   - `style_profile_version`
   - `provider_id`
   - `model_id`
   - `postprocess_version`
3. cache invalidation。
4. prompt 变更触发重译计划。
5. glossary locked 变更触发重检计划。

## 三者对照

| 项目 | Checkpoint | LLM Response Cache | Translation Memory |
|------|------------|--------------------|--------------------|
| 解决问题 | 从哪里继续 | 是否重复调用 API | 历史译法如何复用 |
| 是否代表质量 | 否 | 否 | 取决于 review status |
| 典型键 | segment/status | request hash | source/target pair |
| 可否人工编辑 | 通常否 | 否 | 可以 |
| 是否进入上下文 | 否 | 否 | 可以 |
| 是否可清理 | 可以 | 可以 | 谨慎 |

## 失效规则

1. Prompt major/minor 变化：cache 失效，TM 需要重检。
2. locked glossary 变化：相关译文需要重检。
3. character profile locked 字段变化：相关角色台词需要重检。
4. style profile major 变化：可生成重润色计划。
5. provider/model 变化：cache key 不同，不自动复用 raw response。

## 验收标准

1. 文档和 schema 明确区分三者。
2. JSONL status 可独立支持 MVP 断点。
3. SQLite checkpoint 是增强，不是唯一存储。
4. LLM cache 不绕过 Validator。
5. TM 不把未审核失败输出当推荐译法。
