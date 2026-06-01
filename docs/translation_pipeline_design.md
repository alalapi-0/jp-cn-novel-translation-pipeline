# 翻译流水线设计

本项目采用 **三层模型分工架构**，将翻译任务拆解为 **初译层（Draft Translation）**、**润色层（Polish）** 与 **检索记忆层（Retrieval / Embedding）**。每层使用不同的模型，职责明确，能够在保持低成本的前提下逐步提升译文质量。

---

## 1. 初译层 – Draft Translation Layer

**目标**
- 低成本、快速批量处理。
- 保持基本语义准确，保留原文信息（如专有名词、数字、格式）。
- 生成的译文仅作为 **草稿**，不可直接作为最终稿。

**适配模型**（基于 OpenRouter 可用模型，可根据实际模型库调整）
- `deepseek/deepseek-v4-flash`
- `deepseek/deepseek-v4-pro`
- 其他低成本、批量友好的模型（如 `meta-llama/3.1-8b-instruct`）

**实现要点**
- 输入：`input_jp/<章节>.md`
- 输出：`output_cn/experiments/draft_<章节>.md`
- **强制 dry‑run**：除非用户显式启用真实 API，否则仅生成提示文件和计划日志。
- **不覆盖** `output_cn/translated/` 中已有正式译文。
- 通过 **术语库**（`notes/glossary.md`）提供可选提示，以提高一致性。

---

## 2. 润色层 – Polish Layer

**目标**
- 提升自然度，消除机器翻译腔。
- 统一轻小说风格、人物语气、术语翻译。
- 兼顾前后章节一致性，处理日文表达差异。

**适配模型**
- `google/gemini-3.5-flash`
- `google/gemini-3.5-pro`
- `openai/gpt-4o`
- `deepseek/deepseek-pro`

**实现要点**
- 输入：原文 (`input_jp/章节.md`)、初译草稿 (`output_cn/experiments/draft_章节.md`)、术语库、人物表、风格指南。
- 输出：`output_cn/experiments/polished_章节.md`（供人工审阅），或在人工确认后复制到 `output_cn/translated/`。
- **上下文包装**：在 Prompt 中嵌入 **术语表**、**人物名表** 与 **风格指南**，并提供**前后章节摘要**（通过检索层获取）。
- **不覆盖** 正式译文，所有更改需人工复核后手动合并。

---

## 3. 检索记忆层 – Retrieval / Embedding Layer

**目标**
- 为初译和润色提供 **术语、人物、前文段落** 的语义检索。
- 解决长篇小说中人名/称呼不统一、术语前后不一致、风格漂移等问题。

**适配模型**
- `google/gemini-embedding-2`
- 其他开源或 OpenRouter 上的嵌入模型（如 `sentence-transformers/all-MiniLM-L6-v2`）

**实现要点**
- **Embedding 只负责向量化**，不直接生成译文。
- **记忆库内容**：`notes/glossary.md`、`notes/character_names.md`、`notes/style_guide.md`、`notes/translation_rules.md`、已审核的译文块（双语对照段落）、一致性检查报告等。
- **切块规则**：按术语条目、人物条目、章节段落、双语段落分别切块，生成元数据（章节号、段落号、类型等）。
- **检索场景**：
  - 初译前检索统一术语 → 提示模型使用统一译名。
  - 润色前检索前文译法 → 保持人物称呼、风格连贯。
  - 一致性检查时对比相似片段 → 自动发现可能的译文不一致。

---

## 4. 流程概览

```mermaid
flowchart TD
    A[输入日文原文 (input_jp)] --> B[初译层 (Draft Model)] --> C[实验草稿 (output_cn/experiments)]
    C --> D[检索层 (Embedding)] --> E[润色层 (Polish Model)] --> F[实验润色稿]
    F --> G[人工审校 & 合并] --> H[正式译文 (output_cn/translated)]
    H --> I[双语对照生成] --> J[output_cn/bilingual]
    H --> K[全卷合并] --> L[output_cn/translated/full_volume_cn.md]
``` 

通过上述三层分工，项目能够在 **成本控制** 与 **质量保证** 之间实现平衡，并为后续的 **Embedding 检索** 与 **多模型协作** 提供坚实基础。
