# 动态术语、角色与世界观注入设计

## 8.1 为什么不全量塞表

参考 GalTransl / AiNiee 的可迁移经验是：当前 batch 命中什么，就注入什么；不要把全量术语、角色和世界观设定直接塞进 Prompt。

原因：

1. 全表过长。
2. 成本高。
3. 模型注意力稀释。
4. 术语冲突风险增加。
5. 当前 batch 命中更有效。

## 8.2 Glossary 动态注入

流程：

```text
source batch
→ term matcher
→ matched approved / locked terms
→ prompt glossary block
→ validator locked term check
```

规则：

1. `approved` 必须注入。
2. `locked` 必须强制。
3. `candidate` 仅参考，不得强制。
4. `conflict` 作为风险提示。
5. `deprecated` 用于检查旧译名残留。

Prompt block 建议字段：

```yaml
glossary_version:
matched_terms:
  - term_id:
    source_text:
    target_text:
    status:
    term_type:
    rule:
    severity:
known_conflicts:
deprecated_translations:
```

## 8.3 Character Profile 动态注入

流程：

```text
speaker / mention detection
→ matched character profile
→ prompt character block
→ voice checker
```

字段：

```yaml
character_id:
source_name:
target_name:
speaker_style:
honorific_level:
first_person:
second_person_patterns:
catchphrases:
addressing_rules:
voice_examples:
```

规则：

1. speaker 命中时注入该角色的语气和称呼规则。
2. 角色被提及时注入姓名、别名和称呼关系。
3. narration 默认不注入全量角色表。
4. `CN_TO_JP` 重点注入第一人称、敬语等级和称呼后缀。
5. `JP_TO_CN` 重点注入敬称保留/转换规则和中文角色声线。

## 8.4 World Bible 动态注入

规则：

1. 只注入当前段落命中的设定。
2. `spoiler-sensitive` 不提前注入。
3. `inferred` 必须标记推测。
4. 不允许 world bible 改写原文。
5. 世界观设定只能辅助理解，不是翻译时新增信息的理由。

Prompt block 建议字段：

```yaml
world_bible_version:
matched_entries:
  - world_entry_id:
    entry_type:
    source_name:
    target_name:
    description:
    source_evidence_ref:
    is_spoiler_sensitive:
    is_inferred:
```

## 8.5 Pre/Post Replace

吸收 GalTransl 和 AiNiee：

1. 译前保护 URL。
2. 译前保护控制符。
3. 译前保护不可翻译词。
4. 译后还原。
5. Validator 检查占位符不丢。

占位符原则：

```text
source_text
→ pre_replace
→ protected_source_text + placeholder_map
→ model translation
→ response extractor
→ post_replace
→ validator placeholder_preserved
```

占位符必须稳定、唯一、可还原，不应与目标语言自然文本混淆。

## 验收标准

1. 当前 batch 只注入命中知识资产。
2. locked / approved 术语优先级明确。
3. candidate 不会被当作强制译名。
4. spoiler-sensitive world bible 不提前进入上下文。
5. placeholder 丢失会进入 `validation_failed`。
