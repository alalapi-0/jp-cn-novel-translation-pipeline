# 翻译记忆系统设计

翻译记忆用于记录过去已经翻译过的原文片段和对应译文，帮助后续避免重复翻译、保持相似句表达一致、辅助一致性校对，并帮助中日互译之间建立可复用经验。

## Translation Memory 字段

```yaml
tm_id:
project_id:
language_direction:
source_text:
target_text:
source_language:
target_language:
chapter_id:
segment_id:
speaker_character_id:
term_ids:
quality_status:
created_by_model:
review_status:
version:
created_at:
updated_at:
```

## 使用场景

1. 翻译前检索相似句。
2. 一致性校对前检索历史译法。
3. 一致性检查时查找重复表达。
4. 用户修改译文后反向更新翻译记忆。
5. 后续同系列作品可复用部分翻译经验。

## 状态建议

- `draft`：机器初翻或未审核片段。
- `reviewed`：人工审核过的片段。
- `preferred`：可作为优先参考的片段。
- `deprecated`：不再推荐使用。
- `conflict`：相似原文存在冲突译法。

## 与 embedding 的关系

Translation Memory 是结构化资产，embedding 是检索索引。不能只保留向量而丢失原始 source/target、章节、segment、review status 和版本信息。
