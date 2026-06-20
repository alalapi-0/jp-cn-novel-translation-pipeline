# 术语库系统设计

术语库不是普通词典，而是一本小说项目的一致性资产。它记录专名、称号、技能、制度、口癖和固定表达的译法、状态、证据、冲突和锁定规则，并服务于翻译、一致性校对、审核和前端人工确认。

## 术语类型

至少支持：

- `person_name`
- `place_name`
- `organization`
- `country`
- `city`
- `school`
- `family`
- `title`
- `rank`
- `skill`
- `magic`
- `item`
- `weapon`
- `race`
- `species`
- `concept`
- `system_term`
- `idiom`
- `catchphrase`
- `honorific`
- `other`

## 术语状态机

- `candidate`：模型抽取但未确认。
- `approved`：可用于正式翻译。
- `rejected`：错误候选。
- `deprecated`：曾经使用但被替换。
- `conflict`：出现多个译名冲突。
- `needs_review`：需要人工或强模型判断。
- `locked`：禁止后续自动修改。

状态流转原则：

1. 新抽取术语默认进入 `candidate`。
2. 人工或审核模型确认后进入 `approved`。
3. 明确错误进入 `rejected`。
4. 已使用但被新译名替换的进入 `deprecated`。
5. 同一 source 出现多个 target 时进入 `conflict`。
6. 无法自动判断时进入 `needs_review`。
7. 用户确认不可自动变更时进入 `locked`。

## 术语字段

每个术语至少包含：

```yaml
term_id:
project_id:
language_direction:
source_language:
target_language:
source_text:
target_text:
term_type:
status:
confidence:
first_seen_chapter:
first_seen_segment:
occurrence_count:
alternative_translations:
deprecated_translations:
related_character_ids:
related_world_bible_ids:
example_source_sentences:
example_target_sentences:
translation_rule:
model_reason:
human_note:
created_by:
updated_by:
created_at:
updated_at:
version:
```

## 术语抽取流程

```text
原文导入
→ 文本清洗
→ 分词 / NER
→ LLM 候选术语抽取
→ 频率统计
→ 上下文聚合
→ 初步译名建议
→ 冲突检测
→ 写入候选术语库
→ AI 审核
→ 人工可选审核
→ approved glossary
→ 翻译阶段强制使用
→ 一致性校对阶段强制检查
→ 一致性检查反向更新
```

## 术语使用优先级

1. `locked` 术语。
2. 人工确认的 `approved` 术语。
3. 角色设定中的姓名和称呼规则。
4. 世界观设定中的正式名称。
5. 已审核译文中稳定使用的译法。
6. 模型建议候选。
7. 未确认候选术语。

## 术语冲突处理

1. 同一 `source_text` 出现多个 `target_text`，必须标记 `conflict`。
2. 同一角色名出现不同译名，要优先查 character profile。
3. 后文发现旧译名不合适，要生成替换计划。
4. 替换计划必须记录影响章节和段落。
5. `locked` 术语不能被自动覆盖。
6. 术语冲突不能被静默修正，必须进入 review issue 或一致性修复报告。
7. 中日双向术语必须记录 `language_direction`，避免反向翻译机械套用。

## 与其他系统关系

- 角色姓名、昵称和称呼优先与 `CharacterProfile` 对齐。
- 地名、组织、制度、技能体系优先与 `WorldBibleEntry` 对齐。
- 已确认例句可进入 translation memory 和 vector store。
- 前端 glossary editor 负责人工审核、锁定和废弃术语。
