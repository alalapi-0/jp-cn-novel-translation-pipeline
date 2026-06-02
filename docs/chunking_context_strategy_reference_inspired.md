# 分块与上下文策略：TBL + AiNiee + GalTransl 融合方案

## 7.1 MVP

1. 段落级 unit 是默认翻译和审核单位。
2. 一段一条 JSONL，长段才拆 `segment_id`。
3. 长段落再拆 segment，但必须保持 `paragraph_id` 回链。
4. 不硬切字符串，优先自然语义边界。
5. 不破坏对话结构、引号、说话人和段落顺序。

MVP 不追求复杂 token 估算，只要求可追踪、可回退、可校验。

## 7.2 Phase 2

1. 引入 token soft limit。
2. 段落边界优先。
3. 句号边界优先。
4. 对话边界优先。
5. 前 1-3 段原文作为 `context_before`。
6. 上一 chunk 译文尾部作为 `previous_translation`。
7. 注入当前章节标题。
8. 注入当前说话人。
9. 注入命中术语。
10. 注入命中角色设定。

Phase 2 的目标是提升长篇一致性，同时避免把整章、整卷或全量知识表塞入 Prompt。

## 7.3 Phase 3

1. 根据 `narration` / `dialogue` / `thought` 使用不同策略。
2. failed chunk 可拆小重试。
3. 结合 token estimate 控制成本。
4. 支持 `context_after`，但默认谨慎使用，避免提前剧透。
5. 支持 vector retrieval 注入相似片段。

Phase 3 需要与 Translation Memory、vector DB、Review Workbench 和 checker 结合，不能提前成为 MVP 阻塞项。

## 7.4 Context Pack Schema

```yaml
context_pack_id:
project_id:
language_direction:
chapter_id:
segment_ids:
source_text:
context_before:
context_after:
previous_translation:
chapter_title:
chapter_summary:
matched_glossary:
matched_characters:
matched_world_bible:
style_profile:
direction_rules:
known_risks:
output_contract:
```

## 设计规则

1. `context_before` 默认只含前文原文，不含未经校验的模型分析。
2. `previous_translation` 只能来自通过校验或人工确认的译文；若来自 draft，必须标记风险。
3. `matched_glossary` 只注入当前 batch 命中项，locked / approved 优先。
4. `matched_characters` 只注入 speaker、mentions、关系强相关角色。
5. `matched_world_bible` 不注入 spoiler-sensitive 条目，除非当前段落已经出现证据。
6. `output_contract` 必须与 Prompt Version 绑定，供 ResponseExtractor 与 Validator 使用。

## 常见风险

- 上下文过长导致模型忽略核心文本。
- `context_after` 泄露伏笔或诱导模型提前解释。
- previous translation 未校验，导致错误延续。
- 角色与术语全量注入导致注意力稀释。
- chunk 过大导致 JSON 输出缺项。

## 验收标准

1. Context Pack 可由 JSONL 记录稳定生成。
2. 每个 Context Pack 可追溯 `segment_ids`。
3. 支持 `JP_TO_CN` 与 `CN_TO_JP` 两个方向。
4. 不依赖真实 API 即可用 fake provider 测试。
5. 输出能直接供 PromptBuilder 使用。
