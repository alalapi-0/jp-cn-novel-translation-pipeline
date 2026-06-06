# Asset Abstraction Safety Rules

## 目标

确保从翻译副产物提炼的资产 **可安全复用为创作灵感**，不构成对原作的复述、抄袭或未授权衍生。

## 强制字段

每条资产必须包含：

- `abstraction_level`
- `copyright_safety_level`
- `reuse_guidance`

缺少任一项 → **拦截**，不得进入 `assets_extracted/`。

## Validator 检查项

| 检查 ID | 条件 | 动作 |
|---|---|---|
| `missing_required_field:*` | 缺少安全字段 | 拦截 |
| `long_text:pattern_description` | 描述 > 500 字符 | 拦截 |
| `long_text:generated_examples[*]` | 单条示例 > 200 字符 | 拦截 |
| `long_text:generated_examples_total` | 示例总长 > 600 字符 | 拦截 |
| `too_many_source_specific_names` | 片假名/英文专名 > 3 | 拦截 |
| `example_from_source:*` | 示例与原文长公共子串 | 拦截 |
| `narrative_retelling_not_pattern` | 叙事资产像章节复述 | 拦截 |
| `copyright_safety_level:unsafe` | 标记为 unsafe | 拦截 |

## 版权安全等级

| 等级 | 含义 | 是否可入公共库 |
|---|---|---|
| `safe` | 高度抽象，无原作专名/情节 | 是（若配置允许） |
| `caution` | 需人工复核 | 默认否 |
| `unsafe` | 疑似侵权或复述 | **否** |

## generated_examples 规则

1. 必须是 **合成/泛化** 示例
2. 不得包含与 `segments.json` 源文本显著重叠的连续片段（≥12 字符且重叠比 ≥55%）
3. 不得使用原作角色名、地名、独创系统名

## 叙事资产特殊规则

`narrative` 类型资产应描述 **结构功能**（钩子、伏笔、节奏），而非「然后…接着…」式情节流水账。

## 公共库写入 gate

同时满足：

1. `asset_extraction.write_to_public_asset_library: true`
2. 资产通过全部 safety 检查
3. `copyright_safety_level` 为 `safe` 或 `caution`（MVP 仅 `safe` 计入 safe 分区）

默认 `write_to_public_asset_library: false` — **不写** `assets_extracted/`。

## 人工复核 Prompt

见 `prompts/asset_abstraction_safety_review_prompt_v0.1.0.md`。
