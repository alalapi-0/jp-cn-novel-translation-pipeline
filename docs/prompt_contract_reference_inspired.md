# Prompt 分层、版本化与输出契约

## 9.1 Prompt Layer

参考 SakuraLLM / AiNiee / GalTransl，本项目 Prompt 必须分层组合，而不是把所有规则拼成不可维护的长文本。

推荐层：

1. `system_base`
2. `direction_rules`
3. `style_profile`
4. `glossary_block`
5. `character_block`
6. `world_bible_block`
7. `context_block`
8. `source_block`
9. `output_contract`
10. `validation_reminder`

每一层应有清晰来源、版本和是否可选的规则。方向差异只放在 direction rules，不复制 shared core。

## 9.2 Prompt Version

格式：

```text
prompt_{direction}_{stage}_v{major}.{minor}.{patch}
```

示例：

```text
prompt_cn_to_jp_initial_v0.1.0
prompt_jp_to_cn_initial_v0.1.0
prompt_cn_to_jp_refine_v0.1.0
prompt_jp_to_cn_refine_v0.1.0
```

Prompt Version 必须写入：

1. JSONL。
2. ModelRun。
3. Cache key。
4. Translation Memory。
5. Review report。

版本规则：

1. patch：措辞小修，不改变输出契约。
2. minor：新增规则或检查提醒，可能影响译文。
3. major：输出契约、方向规则或质量目标改变。
4. Prompt 版本变化必须触发重检或重译计划评估。

## 9.3 输出契约

MVP 优先 JSON：

```json
{
  "items": [
    {
      "segment_id": "seg_001_0001_01",
      "translation": "訳文",
      "notes": []
    }
  ]
}
```

Fallback 编号文本：

```text
[seg_001_0001_01]
訳文
```

必须说明：

1. 输出缺 `segment_id` 则 `validation_failed`。
2. 输出多 `segment_id` 则 `validation_failed`。
3. JSON 解析失败可尝试 fallback。
4. 全部失败则保存 raw output，不写成功译文。
5. Prompt 版本变化必须触发重检或重译计划。

## PromptBuilder 输入

```yaml
prompt_version:
language_direction:
stage:
context_pack:
provider_capabilities:
output_contract:
validation_policy:
```

## PromptBuilder 输出

```yaml
messages:
prompt_version:
prompt_hash:
source_segment_ids:
expected_output_contract:
known_risks:
```

## 校验提醒层

`validation_reminder` 应提醒模型：

1. 不得漏掉任何 `segment_id`。
2. 不得新增未请求的 `segment_id`。
3. 不得输出解释性长文，除非写入 `notes`。
4. locked 术语必须遵守。
5. 占位符必须保留。
6. 输出语言必须是目标语言。

## 验收标准

1. 每个 Prompt 有版本。
2. 每次 ModelRun 记录 `prompt_version`。
3. JSON 输出可由 ResponseExtractor 解析。
4. fallback 文本有明确格式。
5. Prompt 变化可追踪到 cache、TM 和 review report。
