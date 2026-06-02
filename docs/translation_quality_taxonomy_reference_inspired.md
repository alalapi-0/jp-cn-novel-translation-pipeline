# 翻译质量错误分类 Taxonomy

本 taxonomy 参考 LiteraryTranslation 和 GalTransl Problem 思路，用于 Validator、Checker、ReviewIssue、Workbench 和 benchmark。标签必须稳定、可机读、可映射到具体 `paragraph_id` / `segment_id`。

## 标签总览

| 标签 | 定义 | 示例 | 检测方式 | 严重程度 | 可自动修复 | 需人工审核 | 后续 checker |
|------|------|------|----------|----------|------------|------------|--------------|
| `MISTRANSLATION` | 语义误译 | 把“没有去”译成“去了” | 对照审核、强模型 review、人工 | high | 否 | 是 | semantic checker |
| `OMISSION` | 漏译原文信息 | 原文一句未出现在译文 | 长度/对齐/语义 review | high | 否 | 是 | alignment checker |
| `ADDITION` | 增加原文不存在信息 | 擅自解释角色动机 | diff / semantic review | medium-high | 否 | 是 | over-refinement checker |
| `INCONSISTENT_TERM` | 术语译名不一致 | 同一技能两种译名 | glossary scan | medium | 部分 | 是 | term checker |
| `INCONSISTENT_NAME` | 人名/地名不一致 | 同一角色译名变化 | glossary / character scan | high | 部分 | 是 | name checker |
| `INCONSISTENT_CHARACTER_VOICE` | 角色语气漂移 | 粗鲁角色突然敬语化 | character profile + review | medium-high | 否 | 是 | voice checker |
| `REGISTER_ERROR` | 语域错误 | 正式叙述变网络口语 | style profile review | medium | 否 | 是 | style checker |
| `HONORIFIC_ERROR` | 敬语/称呼错误 | `様` 被漏掉或乱加 | character profile scan | medium-high | 部分 | 是 | honorific checker |
| `STYLE_DRIFT` | 文体偏离目标 | 轻小说被润成论文腔 | style review / benchmark | medium | 否 | 是 | style checker |
| `WORLD_BIBLE_CONFLICT` | 世界观设定冲突 | 组织名或制度解释矛盾 | world bible scan | high | 否 | 是 | world checker |
| `FORMAT_ERROR` | 格式错误 | 换行、列表、标题损坏 | deterministic validator | medium | 是 | 否 | format checker |
| `SEGMENT_ALIGNMENT_ERROR` | segment 覆盖或顺序错误 | 缺一个 `segment_id` | ResponseExtractor / Validator | high | 部分 | 是 | alignment checker |
| `SOURCE_LANGUAGE_RESIDUAL` | 源语言异常残留 | 中译日输出仍大段中文 | language detector / regex | medium | 部分 | 是 | language checker |
| `TARGET_LANGUAGE_RESIDUAL` | 方向混乱或目标语言异常 | 日译中输出日文解释 | language detector / regex | medium | 部分 | 是 | language checker |
| `OVER_REFINEMENT` | 润色过度改写 | 增删剧情、改变语气 | draft/refined diff | high | 否 | 是 | over-refinement checker |
| `UNDER_TRANSLATION` | 翻译不足或过度直译 | 生硬保留源语序 | style / semantic review | medium | 否 | 是 | style checker |
| `PLACEHOLDER_LOST` | 占位符丢失 | URL 或控制符消失 | placeholder validator | high | 是 | 否 | placeholder checker |
| `LOCKED_TERM_VIOLATION` | locked 术语未遵守 | 用户锁定译名被改 | glossary validator | high | 部分 | 是 | term checker |
| `PROMPT_CONTRACT_VIOLATION` | 模型输出违反契约 | 非 JSON、缺 items | extractor / validator | high | 部分 | 否 | contract checker |

## 严重程度建议

- `critical`：会导致导出不可用、泄露敏感信息或大面积错位。
- `high`：影响语义、术语锁定、段落对齐或最终质量。
- `medium`：影响一致性、风格或人工阅读体验。
- `low`：轻微格式、措辞或可接受差异。

## ReviewIssue Schema 对齐

```yaml
issue_id:
project_id:
language_direction:
chapter_id:
paragraph_id:
segment_id:
issue_type:
severity:
source_text_ref:
target_text_ref:
description:
evidence:
suggested_action:
auto_fixable:
requires_human_review:
status:
created_by:
created_at:
resolved_at:
```

## 自动修复边界

可自动修复的通常仅限：

1. 占位符还原。
2. 明确格式错误。
3. 部分 locked term 替换。
4. 明确 deprecated 译名替换。

不可自动修复的通常包括：

1. 误译。
2. 漏译。
3. 世界观冲突。
4. 角色语气冲突。
5. 过度润色。

## 验收标准

1. 所有 checker 使用统一标签。
2. 每个 issue 可定位到 `segment_id`。
3. high 及以上 issue 默认阻止 final 导出。
4. 自动修复必须记录 change log。
5. 人工审核结果可回写 status。
