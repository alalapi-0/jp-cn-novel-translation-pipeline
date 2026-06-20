# 共享核心与方向专属模块设计

## 设计目标

项目需要同时支持 `JP_TO_CN` 和 `CN_TO_JP`，但不能复制两套相同基础设施。共享核心负责跨方向通用能力，方向模块只负责语言特定规则、Prompt 和审核标准。

参考仓库方法吸收后，shared core 还承担稳定 ID、JSONL 中间态、动态注入、PromptBuilder、ResponseExtractor、Validator、Provider Registry、Checkpoint、Translation Memory、ReviewIssue 和 Exporter 的统一边界。方向模块只提供语言方向规则、文体目标、敬称策略和方向 Prompt 片段，不重复实现 shared core。

## 共享核心模块

未来共享核心可以规划为：

```text
shared/
├── file_scanner/
├── chapter_parser/
├── text_cleaner/
├── segmenter/
├── alignment/
├── tokenizer/
├── glossary/
├── character_profiles/
├── world_bible/
├── translation_memory/
├── embedding/
├── vector_store/
├── context_retriever/
├── prompt_builder/
├── model_provider/
├── response_extractor/
├── validator/
├── quality_review/
├── exporter/
└── project_state/
```

### file_scanner

- 职责：扫描项目输入目录，生成 SourceFile manifest。
- 输入：`input_jp/`、`input_cn/`、project config。
- 输出：source file manifest。
- 语言无关：是。
- 方向适配：只需根据 direction 选择输入目录。
- 后续实现轮次：Round 06。
- 依赖关系：ProjectState、Directory Config。

### chapter_parser

- 职责：识别卷、章、序章、番外、后记等章节结构。
- 输入：source files、direction config。
- 输出：Chapter metadata。
- 语言无关：部分。
- 方向适配：章节标题正则和语言特征需要适配。
- 后续实现轮次：Round 07。
- 依赖关系：file_scanner、text_cleaner。

### text_cleaner

- 职责：规范空行、保留对话和标题、清理明显噪声。
- 输入：raw text。
- 输出：cleaned text、cleaning report。
- 语言无关：部分。
- 方向适配：标点、空格、全角半角规则需要适配。
- 后续实现轮次：Round 08。
- 依赖关系：chapter_parser。

### segmenter

- 职责：将章节切分为可追踪 segment。
- 输入：cleaned chapter text。
- 输出：segments、segment ids、offsets。
- 语言无关：部分。
- 方向适配：日文和中文断句策略不同。
- 后续实现轮次：Round 08。
- 依赖关系：text_cleaner、tokenizer。

### alignment

- 职责：维护原文、翻译中间态、最终译文之间的段落对齐。
- 输入：segments、draft translation、final translation。
- 输出：ParagraphAlignment。
- 语言无关：是。
- 方向适配：不直接适配，只使用 direction metadata。
- 后续实现轮次：Round 25、Round 32。
- 依赖关系：segmenter、translation memory。

### tokenizer

- 职责：提供语言相关分词、候选术语和 NER 前处理。
- 输入：text segments。
- 输出：tokens、candidate spans。
- 语言无关：否。
- 方向适配：需要日文 tokenizer 与中文 tokenizer。
- 后续实现轮次：Round 09 到 Round 11。
- 依赖关系：segmenter、direction rules。

### glossary

- 职责：管理术语、译名、状态、冲突和锁定规则。
- 输入：term candidates、人工修改、审核反馈。
- 输出：approved glossary、conflict report。
- 语言无关：是。
- 方向适配：字段包含 source/target language 与 direction。
- 后续实现轮次：Round 16。
- 依赖关系：character_profiles、world_bible、translation_memory。

### character_profiles

- 职责：管理角色姓名、别名、称呼关系、语气和发言样例。
- 输入：角色候选、人工修改、台词样例。
- 输出：CharacterProfile、CharacterRelation。
- 语言无关：是。
- 方向适配：敬称、第一人称、称呼策略需要方向规则。
- 后续实现轮次：Round 17。
- 依赖关系：glossary、embedding、context_retriever。

### world_bible

- 职责：管理地点、组织、制度、技能、历史、伏笔等设定。
- 输入：世界观候选、原文证据、人工确认。
- 输出：WorldBibleEntry。
- 语言无关：是。
- 方向适配：名称和表述存在双方向字段。
- 后续实现轮次：Round 18。
- 依赖关系：glossary、character_profiles。

### translation_memory

- 职责：记录已翻译片段和对应译文，支持复用和一致性检查。
- 输入：source segment、target segment、review status。
- 输出：TranslationMemoryEntry。
- 语言无关：是。
- 方向适配：按 `language_direction` 隔离。
- 后续实现轮次：Round 15、Round 24。
- 依赖关系：alignment、embedding。

### embedding

- 职责：生成文本向量或 fake embedding。
- 输入：可检索文本和 metadata。
- 输出：EmbeddingRecord。
- 语言无关：是。
- 方向适配：metadata 必须包含 direction。
- 后续实现轮次：Round 13。
- 依赖关系：model_provider、vector_store。

### vector_store

- 职责：提供 add/search/update/delete 和 metadata filter。
- 输入：EmbeddingRecord、query vector。
- 输出：search results。
- 语言无关：是。
- 方向适配：必须支持 project 和 direction filter。
- 后续实现轮次：Round 14。
- 依赖关系：embedding。

### context_retriever

- 职责：组合术语、角色、世界观、记忆和相似片段，生成 context pack 片段。
- 输入：segment、glossary、characters、world bible、vector search results。
- 输出：ContextPack。
- 语言无关：是。
- 方向适配：读取 direction-specific rules。
- 后续实现轮次：Round 15。
- 依赖关系：glossary、character_profiles、world_bible、translation_memory、vector_store。

### model_provider

- 职责：抽象真实 provider 和 fake provider。
- 输入：provider config、request。
- 输出：response、usage、error、model run metadata。
- 语言无关：是。
- 方向适配：不适配语言，只传递任务类型和 metadata。
- 后续实现轮次：Round 12、Round 21。
- 依赖关系：ProjectState、budget guard。

### response_extractor

- 职责：把 provider raw output 解析为结构化结果，支持 JSON 契约和编号 fallback。
- 输入：ModelResult.raw_output、expected segment ids、output contract。
- 输出：ParseResult、raw output ref、parse errors。
- 语言无关：是。
- 方向适配：不直接适配，只传递 `language_direction` metadata。
- 后续实现轮次：RM-14。
- 依赖关系：prompt_builder、model_provider、validator。

### validator

- 职责：检查 non_empty、segment_id 覆盖、locked terms、placeholder、语言残留、长度比例、段落对齐和 Prompt 契约。
- 输入：ParseResult、ContextPack、glossary、character profiles、world bible。
- 输出：ValidationResult、ReviewIssue。
- 语言无关：部分。
- 方向适配：源/目标语言残留、敬语和文体检查读取 direction rules。
- 后续实现轮次：RM-15。
- 依赖关系：response_extractor、quality_review、project_state。

### quality_review

- 职责：生成术语、角色、世界观、漏译、多译、风格等 review issue。
- 输入：source、target、alignment、knowledge assets。
- 输出：ReviewIssue。
- 语言无关：部分。
- 方向适配：目标语言残留、敬语和标点检查需要方向规则。
- 后续实现轮次：Round 26 到 Round 28。
- 依赖关系：glossary、character_profiles、world_bible、alignment。

### exporter

- 职责：导出纯译文、双语对照、审核报告和前端数据。
- 输入：draft/final translation、alignment、issues、project metadata。
- 输出：Markdown、JSON、archive。
- 语言无关：是。
- 方向适配：输出目录和标点格式可按 direction 配置。
- 后续实现轮次：Round 25、Round 35、Round 40。
- 依赖关系：project_state、alignment。

### project_state

- 职责：维护项目、章节、任务和 pipeline 状态。
- 输入：pipeline events、user edits、model runs。
- 输出：ProjectState、progress report。
- 语言无关：是。
- 方向适配：状态按 direction 分区。
- 后续实现轮次：Round 05、Round 33。
- 依赖关系：所有 pipeline。

## 方向专属模块

未来方向模块可以规划为：

```text
directions/
├── jp_to_cn/
│   ├── prompts/
│   ├── style_rules/
│   ├── honorific_rules/
│   ├── naming_rules/
│   ├── punctuation_rules/
│   └── review_rules/
└── cn_to_jp/
    ├── prompts/
    ├── style_rules/
    ├── honorific_rules/
    ├── naming_rules/
    ├── punctuation_rules/
    └── review_rules/
```

## JP_TO_CN 方向专属内容

1. 日文敬称处理。
2. 日文省略主语处理。
3. 日文汉字名保留规则。
4. 片假名人名音译规则。
5. 日式轻小说语气中文化。
6. 中文标点转换。
7. 中文自然化。
8. 中文读者可读性优化。

## CN_TO_JP 方向专属内容

1. 中文人名日文化策略。
2. 中文称呼转日语敬称策略。
3. 日文敬语重建。
4. 日文小说文体。
5. 日文标点规则。
6. 日文对话自然度。
7. 中文网络语或口语的日文化。
8. 中式表达转日式表达。

## 防止冗余与冲突的原则

1. 文件扫描不应在两个方向重复实现。
2. 章节解析不应在两个方向重复实现。
3. 术语库系统不应复制两套。
4. 角色设定系统不应复制两套。
5. 世界观系统不应复制两套。
6. embedding 与 vector store 不应复制两套。
7. Prompt 可以分方向维护。
8. 翻译规则可以分方向维护。
9. 输出格式可以分方向维护。
10. 方向模块只能覆盖语言特定规则，不能重复实现 shared core。
