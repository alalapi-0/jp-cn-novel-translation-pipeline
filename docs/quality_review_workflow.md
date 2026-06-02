# 质量审核流程设计

## 审核维度

至少包括：

1. 漏译。
2. 多译。
3. 误译。
4. 术语不一致。
5. 人名不一致。
6. 地名不一致。
7. 组织名不一致。
8. 技能名不一致。
9. 称呼不一致。
10. 角色语气漂移。
11. 世界观冲突。
12. 段落错位。
13. 日文残留。
14. 中文残留。
15. 目标语言不自然。
16. 机翻腔。
17. 润色过度。
18. 伏笔被提前解释。
19. 暧昧表达被强行明确化。
20. 敬语处理错误。
21. 标点问题。
22. 章节标题问题。
23. 版权声明或出处信息缺失。
24. 格式问题。

参考方法吸收后，审核 issue 应优先使用 `docs/translation_quality_taxonomy_reference_inspired.md` 中的稳定标签，例如 `MISTRANSLATION`、`OMISSION`、`INCONSISTENT_TERM`、`LOCKED_TERM_VIOLATION`、`PLACEHOLDER_LOST`、`PROMPT_CONTRACT_VIOLATION` 等。

## Review Issue Schema

```yaml
issue_id:
project_id:
language_direction:
chapter_id:
paragraph_id:
segment_id:
issue_type:
severity:
source_text:
target_text:
description:
suggested_fix:
related_term_ids:
related_character_ids:
related_world_bible_ids:
status:
created_by:
created_at:
resolved_at:
```

## 审核状态

- `draft`
- `machine_translated`
- `review_needed`
- `term_conflict`
- `voice_conflict`
- `world_conflict`
- `style_issue`
- `refined`
- `human_reviewed`
- `final`

## 审核原则

- 审核流程生成 issue，不自动覆盖译文。
- 所有 issue 必须可定位到 chapter 和 segment。
- 涉及 locked 术语时不得自动修改。
- 对伏笔、暧昧表达和角色语气保持保守。
- high 及以上 issue 默认阻止 final 导出，除非人工明确确认。
- Validator 与 checker 生成的 issue 必须写回 JSONL 或 review issue 数据，不散落在不可解析日志中。
