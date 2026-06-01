# 世界观设定系统设计

世界观设定系统用于保存从原文中抽取的设定信息，帮助翻译模型理解上下文，避免术语和设定冲突。

## 设定类型

至少支持：

- `location`
- `country`
- `city`
- `organization`
- `family`
- `rank_system`
- `magic_system`
- `battle_system`
- `technology_system`
- `school_system`
- `religion`
- `economy`
- `species`
- `race`
- `history`
- `myth`
- `law`
- `custom`
- `item_system`
- `skill_system`
- `unknown_or_foreshadowing`

## 设定字段

```yaml
world_entry_id:
project_id:
entry_type:
source_name:
target_name_cn:
target_name_jp:
description:
source_evidence:
first_seen_chapter:
related_chapters:
related_terms:
related_characters:
confidence:
status:
is_spoiler_sensitive:
is_inferred:
notes:
version:
```

## 设定来源规则

1. 设定必须来自原文。
2. 模型推测必须标记为 `is_inferred: true`。
3. 不确定设定必须标记 `needs_review`。
4. 伏笔不能提前解释到正文译文中。
5. 世界观设定可以帮助翻译，但不能替代原文。
6. 世界观条目必须保存原文证据或章节位置，不能只有模型概括。
7. 涉及剧透的设定必须标记 `is_spoiler_sensitive`，避免过早进入前文 context pack。

## 审核状态

建议状态：

- `candidate`
- `approved`
- `needs_review`
- `conflict`
- `deprecated`
- `locked`

## 与其他系统关系

- 与 glossary 共享地点、组织、制度、技能、物品等标准译名。
- 与 character profile 关联角色阵营、家族、身份和关系。
- 与 embedding/vector store 关联原文证据片段。
- 与 quality review 关联世界观冲突 issue。
