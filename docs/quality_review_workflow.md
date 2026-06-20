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
17. 表达改写过度（仅用于用户修改稿或局部重译对比）。
18. 伏笔被提前解释。
19. 暧昧表达被强行明确化。
20. 敬语处理错误。
21. 标点问题。
22. 章节标题问题。
23. 版权声明或出处信息缺失。
24. 格式问题。

参考方法吸收后，审核 issue 应优先使用 `docs/translation_quality_taxonomy_reference_inspired.md` 中的稳定标签，例如 `MISTRANSLATION`、`OMISSION`、`INCONSISTENT_TERM`、`LOCKED_TERM_VIOLATION`、`PLACEHOLDER_LOST`、`PROMPT_CONTRACT_VIOLATION` 等。

## Review Issue Schema

权威 JSON Schema：`data/schemas/review_issue.schema.json`。样例报告：`data/examples/review_issue_report.example.json`（synthetic fixture 生成，可提交）。

报告顶层字段：

```yaml
schema_version:
project_id:
language_direction:
review_status:   # 对齐下方审核状态机
generated_at:
generated_by:
issues: []
summary: { total, by_type, by_severity }
```

单条 `ReviewIssue` 字段：

```yaml
issue_id:
project_id:
language_direction:
chapter_id:
paragraph_id:
segment_id:
issue_type:      # 稳定标签，见 translation_quality_taxonomy_reference_inspired.md
severity:
source_text_ref: # 短引用，非全文
target_text_ref:
description:
suggested_fix:
related_term_ids:
related_character_ids:
related_world_bible_ids:
status:          # open | acknowledged | resolved | wont_fix
created_by:
created_at:
resolved_at:
requires_human_review:
auto_fixable:
human_edited_segment:
```

## Round 49 机器审核维度（deterministic）

| 维度 | Checker | 标签示例 | 说明 |
|------|---------|----------|------|
| 术语一致性 | `checker.term_consistency` | `LOCKED_TERM_VIOLATION`, `INCONSISTENT_TERM` | 对照 glossary fixture；locked 禁止自动改译文 |
| 段落对齐 / 漏译启发 | `checker.segment_alignment` | `SEGMENT_ALIGNMENT_ERROR`, `OMISSION` | expected/orphan segment_id；词数比例启发式 |
| 改写 diff | `checker.refinement_diff`（legacy name） | `OVER_REFINEMENT` | draft vs revised/final 表面差异（不写入正文） |

CLI：`python3 scripts/run_quality_review.py --write-example`。Workbench：`frontend/issues.html` 读取 `frontend/assets/review-issue-report.json`；状态仅写 localStorage，**不覆盖** `human_edited` 段落。

留待 Round 50+：语义误译、角色语气、世界观、日文残留、机翻腔等（需模型或更厚规则）。

## 审核状态

- `draft`
- `machine_translated`
- `review_needed`
- `term_conflict`
- `voice_conflict`
- `world_conflict`
- `style_issue`
- `final_ready`
- `human_reviewed`
- `final`

## 审核原则

- 审核流程生成 issue，不自动覆盖译文。
- 所有 issue 必须可定位到 chapter 和 segment。
- 涉及 locked 术语时不得自动修改。
- 对伏笔、暧昧表达和角色语气保持保守。
- high 及以上 issue 默认阻止 final 导出，除非人工明确确认。
- Validator 与 checker 生成的 issue 必须写回 JSONL 或 review issue 数据，不散落在不可解析日志中。
