# 角色设定系统设计

角色设定系统的目的不是写百科，而是保证翻译中角色语气一致、称呼关系一致、口癖一致、敬语等级一致，并防止一致性修复或用户修改把所有人改成同一种声音。

## 角色字段

每个角色至少包含：

```yaml
character_id:
project_id:
source_name:
target_name_cn:
target_name_jp:
aliases:
nickname_list:
gender:
age_or_stage:
role:
faction:
relationship_to_protagonist:
first_seen_chapter:
important_chapters:
speaker_style:
speech_register:
honorific_level:
catchphrases:
first_person_pronoun:
second_person_patterns:
how_others_address_this_character:
how_this_character_addresses_others:
emotional_pattern:
personality_notes:
translation_notes:
voice_examples_source:
voice_examples_target:
status:
confidence:
version:
```

## 角色关系表

角色关系必须单独建模，避免把动态关系写死在单个角色条目里。

```yaml
relation_id:
project_id:
character_a:
character_b:
relationship_type:
addressing_rule_a_to_b:
addressing_rule_b_to_a:
relationship_change_chapters:
notes:
```

## 角色语气检索

未来可用 embedding / 向量库保存角色发言样例：

1. 每个角色的典型台词进入 voice example index。
2. 翻译该角色新台词时检索相似语气。
3. 一致性校对时检查是否偏离角色声音。
4. 不同角色的语气不能被自动修复统一掉。
5. 语气检索必须受 `project_id`、`language_direction`、`speaker_character_id` 约束。

## 日译中与中译日差异

### 日译中

- 要处理敬称、省略主语、角色口癖。
- 要在中文中保留必要的关系感。
- 要决定敬称是保留、意译还是转换为中文称呼。
- 要防止中文表达修订消除角色身份差异。

### 中译日

- 要重建敬语等级。
- 要决定 `私` / `僕` / `俺` / `あたし` 等第一人称。
- 要决定 `さん` / `くん` / `ちゃん` / `様` / `先生` / `先輩` 等称呼。
- 要防止中文直译导致日文不自然。

## 状态与审核

角色条目可以使用 `candidate`、`approved`、`needs_review`、`conflict`、`locked` 等状态。角色姓名和称呼一旦 locked，翻译、一致性校对和审核流程不得自动覆盖。

## 与其他系统关系

- 与 glossary 共享人物姓名、称号和固定称呼。
- 与 world bible 关联阵营、组织、家族和制度。
- 与 translation memory 关联角色台词历史译法。
- 与 review issue 关联称呼冲突和语气漂移。
