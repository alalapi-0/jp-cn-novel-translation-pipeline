# 二次润色流程设计

润色不是重新翻译。润色是基于原文、初翻、术语库、角色设定、世界观设定、翻译记忆的对照式改进。

## 润色输入

```yaml
source_text:
initial_translation:
approved_glossary:
character_profiles:
world_bible_entries:
translation_memory_hits:
style_guide:
direction_specific_rules:
known_issues:
```

## 润色输出

```yaml
refined_translation:
change_log:
term_changes:
voice_adjustments:
world_bible_consistency_notes:
risk_notes:
requires_human_review:
```

## 润色原则

1. 修正机翻腔。
2. 保持原文信息。
3. 不擅自改剧情。
4. 不擅自删减。
5. 不擅自扩写。
6. 不破坏术语一致性。
7. 不破坏角色语气。
8. 保留轻小说节奏。
9. 修正不自然表达。
10. 修正误译、漏译、多译。
11. 保留伏笔和暧昧表达。
12. 不把所有角色润成同一种文风。

## 强模型策略

未来可使用能力更强的推理模型做润色，例如 Grok 类强推理模型、OpenAI 高能力模型、Anthropic 高能力模型、其他强推理模型。

不得写死供应商。必须通过 provider adapter 配置。

## 审核要求

- 润色输出必须保存 change log。
- 润色稿不能覆盖初翻稿。
- 术语变更必须记录。
- 角色语气调整必须记录。
- 疑似过度润色必须进入 review issue。
