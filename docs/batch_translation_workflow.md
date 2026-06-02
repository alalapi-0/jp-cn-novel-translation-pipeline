# 批量初翻流程设计

## 完整流程

```text
导入原文
→ 扫描文件
→ 章节解析
→ 文本清洗
→ 段落切分
→ 分配 paragraph_id / segment_id
→ 写入 JSONL 中间态
→ 术语候选抽取
→ 人物候选抽取
→ 世界观候选抽取
→ 建立项目知识资产
→ embedding 入库
→ 构建章节 context pack
→ PromptBuilder 构建分层 Prompt
→ Provider Adapter 调用 fake / dry-run / 受控真实模型
→ ResponseExtractor 解析输出
→ Validator 校验输出
→ 更新 JSONL status
→ Exporter 生成双语对照
→ 更新术语库
→ 更新人物表
→ 更新世界观设定
→ 更新章节摘要
→ 更新翻译记忆
→ 初步质量检查
```

## 初翻目标

初翻阶段优先级：

1. 完整。
2. 忠实。
3. 不漏译。
4. 术语一致。
5. 人名一致。
6. 称呼一致。
7. 角色语气不要明显错位。
8. 中文或日文基本自然。
9. 不追求最终出版级润色。

## Context Pack 设计

每次翻译章节或段落前，构建 context pack。

```yaml
project_id:
language_direction:
chapter_id:
segment_id:
source_text:
previous_summary:
next_summary_if_available:
approved_glossary:
related_terms:
related_characters:
related_world_bible_entries:
similar_segments:
translation_memory_hits:
style_guide:
direction_specific_rules:
known_risks:
```

## 模型策略

未来可以使用成本相对可控的推理或翻译模型进行初翻，例如 DeepSeek 类模型、OpenRouter 聚合模型、OpenAI 中等成本模型、其他兼容 OpenAI API 格式的模型。

具体 provider 不应写死，必须通过 provider adapter 和配置文件选择。

## 安全与执行边界

- 初翻必须支持 dry-run。
- 批量初翻必须支持最大章节数、最大 token、预算限制和断点续跑。
- 不覆盖已完成译文。
- 不把真实原文和译文提交到公开仓库。
- 校验失败只写 raw output、validation_errors、review_issues 和 retry 状态，不写成功译文。
- `locked` 与 `human_reviewed` 片段默认跳过自动覆盖。
- 最终阅读文件只能由 exporter 从 JSONL 中间态生成。
