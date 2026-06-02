# 总体架构设计

## 架构原则

项目采用分层架构。共享能力放在 shared core，语言方向差异放在 direction layer，模型调用通过 provider adapter 抽象，真实翻译执行必须经过项目配置、预算保护和人工可复查记录。

参考仓库方法吸收后，架构还必须遵守以下补充原则：

1. 原文只读，所有翻译、校验、重试、润色和审核状态写入 JSONL 中间态。
2. `paragraph_id` 与 `segment_id` 是跨 parser、context、Prompt、Validator、ReviewIssue、TranslationMemory 和 Exporter 的稳定定位键。
3. Prompt 必须分层和版本化，`prompt_version` 写入 JSONL、ModelRun、cache、TM 和 review report。
4. 模型输出必须先经过 ResponseExtractor 与 Validator，校验失败不得进入 translated / final。
5. Checkpoint、LLM Response Cache、Translation Memory 分别解决断点、重复请求和译法复用，不得混用。
6. Exporter 是最终阅读文件唯一生成入口，不调用模型，不修改原文。

## User Interface Layer

### 职责

提供用户操作入口，包括命令行、Web 前端、审核工作台和项目仪表盘。

### 主要模块

- CLI
- Web Frontend
- Review Workbench
- Dashboard

### 输入

项目配置、章节列表、术语库、角色设定、世界观设定、翻译状态、审核 issue、provider 设置。

### 输出

用户操作指令、审核修改、术语锁定、角色设定更新、导出请求、批量任务请求。

### 与其他层的关系

早期通过文件和 CLI 调用 Project Management Layer；中期通过本地前端读取结构化数据；后期通过 API 调用 pipeline。

### 当前阶段是否实现

未实现。当前以文件夹和文档为主。

### 后续轮次如何推进

Round 35 建立 CLI MVP；Round 36 做前端信息架构；Round 37 做静态前端；Round 38 读取本地数据；Round 39 支持编辑。

## Project Management Layer

### 职责

管理每本小说项目的配置、元数据、方向、输入输出、进度和模型调用记录。

### 主要模块

- Project Config
- Project Metadata
- Direction Config
- File Manifest
- Progress State
- Model Run Records

### 输入

项目目录、原文文件、用户配置、provider 配置、预算策略。

### 输出

project metadata、manifest、chapter state、model run metadata、progress state。

### 与其他层的关系

为 Text Processing、Translation Pipeline、Review Pipeline 和 UI 提供统一状态来源。

### 当前阶段是否实现

未实现结构化 schema。已有 `notes/source_file_manifest.md` 和 `notes/translation_progress.md` 可作为历史参考。

### 后续轮次如何推进

Round 05 设计 project schema；Round 06 生成 manifest；Round 33 建立状态机；Round 34 管理成本和预算。

## Direction Layer

### 职责

隔离 `JP_TO_CN` 与 `CN_TO_JP` 的语言方向规则、Prompt、文体、标点、姓名和敬称策略。

### 主要模块

- `directions/jp_to_cn/`
- `directions/cn_to_jp/`
- direction-specific prompts
- style rules
- honorific rules
- naming rules
- punctuation rules
- review rules

### 输入

source language、target language、direction config、style guide、术语和角色规则。

### 输出

方向专属规则、Prompt 片段、审核标准、context pack 附加规则。

### 与其他层的关系

被 Text Processing、Translation Pipeline、Review Pipeline 和 Model Provider Layer 读取，不重复实现 shared core。

### 当前阶段是否实现

未实现。当前只有早期日译中文档和 Prompt。

### 后续轮次如何推进

Round 03 设计 `JP_TO_CN`；Round 04 设计 `CN_TO_JP`；Round 19 和 Round 29 建立双方向 Prompt。

### JP_TO_CN 方向职责

- 日文原文解析。
- 日文姓名、敬称、假名、汉字处理。
- 中文自然化。
- 轻小说中文译文风格。
- 日式表达的中文化或保留。

### CN_TO_JP 方向职责

- 中文原文解析。
- 中文姓名转日文策略。
- 日文自然表达。
- 敬语重建。
- 日文小说文体。
- 角色语气日文化。

## Text Processing Layer

### 职责

将原文文件转化为可追踪的章节、段落和 segment，为抽取、embedding、翻译和审核提供稳定输入。

### 主要模块

- File Scanner
- Chapter Parser
- Text Cleaner
- Segmenter
- Paragraph Aligner
- Tokenizer
- NER Candidate Extractor

### 输入

`input_jp/`、`input_cn/`、project config、direction config。

### 输出

manifest、chapter metadata、cleaned text、segments、paragraph alignment、候选实体。

### 与其他层的关系

为 Knowledge Asset、Retrieval、Translation Pipeline 和 Review Pipeline 提供基础文本结构。

### 当前阶段是否实现

未实现标准化 shared core。旧仓库有 source manifest 和输出结构可参考。

### 后续轮次如何推进

Round 06 文件扫描；Round 07 章节解析；Round 08 文本清洗与段落切分；Round 25 双语对照与段落对齐。

## Knowledge Asset Layer

### 职责

维护整本小说翻译一致性的核心资产。

### 主要模块

- Glossary
- Character Profiles
- World Bible
- Style Guide
- Translation Rules
- Translation Memory
- Chapter Summaries
- Term Usage Examples

### 输入

原文证据、译文、人工修改、模型候选、审核 issue、上下文检索结果。

### 输出

approved glossary、角色设定、世界观设定、翻译记忆、章节摘要、context pack 片段。

### 与其他层的关系

被初翻、润色、审核、前端、向量检索共同使用。

### 当前阶段是否实现

已有 notes 形式的术语和人物资料，但缺少结构化 schema、状态机和版本管理。

### 后续轮次如何推进

Round 09 到 Round 11 设计候选抽取；Round 16 到 Round 18 实现 MVP。

## Retrieval Layer

### 职责

通过 embedding 和向量数据库检索相似段落、术语上下文、角色台词和世界观证据。

### 主要模块

- Embedding Generator
- Vector Store
- Context Retriever
- Similar Segment Retriever
- Term Usage Retriever
- Character Voice Retriever
- World Context Retriever

### 输入

segments、translation memory、术语例句、角色台词、世界观证据、query text、metadata filter。

### 输出

检索结果、相似片段、术语用例、角色语气样例、世界观证据。

### 与其他层的关系

为 context pack、初翻、润色和审核提供辅助信息。

### 当前阶段是否实现

未实现真实 embedding 和向量库。已有 `docs/embedding_memory_design.md` 作为早期设计。

### 后续轮次如何推进

Round 13 设计 embedding adapter；Round 14 设计 vector store adapter；Round 15 接入 context pack。

### 约束

Embedding 是为了提升上下文检索能力。向量库不能替代术语表、角色表或人工确认规则。检索结果必须受 `project_id` 和 `language_direction` 约束。

## Model Provider Layer

### 职责

抽象不同模型供应商和模型能力，避免业务逻辑写死 provider 或模型名。

### 主要模块

- Provider Adapter
- Embedding Model Adapter
- Reasoning Model Adapter
- Translation Model Adapter
- Refinement Model Adapter
- Review Model Adapter

### 输入

provider config、model config、request payload、context pack、预算限制。

### 输出

标准化 response、error、usage、model run metadata。

### 与其他层的关系

被 embedding、术语抽取、初翻、润色和审核 pipeline 调用。

### 当前阶段是否实现

未实现统一 adapter。已有 OpenRouter 示例配置和测试规划。

### 后续轮次如何推进

Round 12 设计 provider adapter；Round 21 准备真实 API；Round 22 小规模真实 API 验证。

### 未来可接入

DeepSeek、Grok、OpenAI、OpenRouter、Anthropic、Google、Local Embedding Models、Other Providers。

### 安全要求

Provider 应通过配置选择。API Key 只从 `.env` 或系统环境变量读取。日志不能输出 Key。

## Translation Pipeline Layer

### 职责

组织从准备、知识资产抽取、context pack、初翻、润色、一致性检查到导出的流水线。

### 主要模块

- Preparation Pipeline
- Terminology Extraction Pipeline
- Character Extraction Pipeline
- World Bible Extraction Pipeline
- Initial Translation Pipeline
- Refinement Pipeline
- Consistency Check Pipeline
- Export Pipeline

### 输入

project config、segments、knowledge assets、retrieval results、provider config。

### 输出

初翻草稿、润色稿、双语对照、审核 issue、translation memory、导出结果。

### 与其他层的关系

依赖 Text Processing、Knowledge Asset、Retrieval、Model Provider，并向 Review 与 Export 输出。

### 当前阶段是否实现

未实现标准化 pipeline。已有旧日译中输出可作为历史成果，不作为本轮执行对象。

### 后续轮次如何推进

Round 20 Fake Provider 跑通初翻；Round 23 单章初翻；Round 24 批量初翻；Round 31 润色 pipeline。

### 原则

初翻和润色必须分离。初翻优先忠实、完整、术语一致；润色优先自然、风格统一、保留信息。一致性检查贯穿两者之后。

## Review Pipeline Layer

### 职责

检查译文质量、术语冲突、角色语气、世界观设定和格式问题，并生成可定位的 review issue。

### 主要模块

- Term Conflict Review
- Character Voice Review
- World Bible Conflict Review
- Missing Translation Review
- Over-translation Review
- Style Drift Review
- Human Review Workbench

### 输入

source text、target text、alignment、glossary、character profiles、world bible、translation memory。

### 输出

review issues、suggested fixes、risk notes、human review status。

### 与其他层的关系

接收 Translation Pipeline 输出，反馈 Knowledge Asset 和 UI。

### 当前阶段是否实现

已有早期 review 文件，缺少统一 schema 和状态机。

### 后续轮次如何推进

Round 26 术语一致性；Round 27 角色语气；Round 28 世界观冲突；Round 32 diff。

## Export Layer

### 职责

把草稿、润色稿、双语对照、审核报告和项目数据导出为可复查文件。

### 主要模块

- Plain Text Exporter
- Markdown Exporter
- Bilingual Exporter
- Review Report Exporter
- Frontend Data Exporter
- Archive Exporter

### 输入

draft、refined translation、alignment、issues、metadata、project state。

### 输出

纯译文、双语对照、审核报告、前端 JSON、归档包。

### 与其他层的关系

依赖 Project Management 和 Translation/Review Pipeline。

### 当前阶段是否实现

已有 `output_cn/` 输出结构，缺少双方向统一 exporter。

### 后续轮次如何推进

Round 25 输出双语对照；Round 35 CLI export；Round 40 闭环验证。

## Governance Layer

### 职责

管理路线图、Prompt、规则、交接说明、迁移说明和验收标准，保证后续 Agent 不越级、不重复造轮子。

### 主要模块

- Roadmap
- Round Prompts
- Governance Rules
- Agent Handoff Notes
- Migration Notes
- Acceptance Criteria

### 输入

当前仓库状态、用户目标、路线图、审计结果、执行报告。

### 输出

治理文档、轮次 Prompt、下一轮建议、验收清单。

### 与其他层的关系

约束所有层的推进顺序和安全边界。

### 当前阶段是否实现

本轮建立。

### 后续轮次如何推进

每轮 Agent 必须先读治理文档和路线图，声明轮次、类型、目标、不做事项、修改范围、验收标准和下一轮建议。每轮不得越级乱做，不得重复造轮子。
