# 参考仓库启发的核心流水线设计

当前项目主链路：

```text
source import
→ parser
→ paragraph_id assignment
→ JSONL intermediate
→ segment/chunk
→ pre_replace / placeholder
→ glossary matcher
→ character matcher
→ world bible matcher
→ context pack
→ prompt builder
→ provider adapter
→ response extractor
→ validator
→ status update
→ translation memory update
→ review issue generation
→ refinement
→ diff / change log
→ exporter
```

## source import

- 职责：登记输入文件，确认方向、来源路径、格式和版权风险提示。
- 输入：`input_jp/`、`input_cn/`、Project、DirectionConfig。
- 输出：SourceFile manifest。
- 参考来源：AiNiee Reader/Writer 边界、TBL 文本导入。
- 当前阶段：文档规划。
- 后续实现轮次：RM-02、RM-05。
- 常见风险：误提交真实原文、方向选错、文件编码不明。
- 验收标准：不修改原文，manifest 可追踪，路径不泄露敏感信息。

## parser

- 职责：解析章节、标题、段落和基础文本类型。
- 输入：SourceFile manifest、raw text。
- 输出：Chapter、Paragraph candidate。
- 参考来源：TBL 文本解析、oomol EPUB segment extraction。
- 当前阶段：文档规划。
- 后续实现轮次：RM-05。
- 常见风险：章节误判、空行处理破坏对话、正文被直接改写。
- 验收标准：`.txt` / `.md` 可解析，原文只读，解析报告可复查。

## paragraph_id assignment

- 职责：为每个段落分配稳定 `paragraph_id`。
- 输入：Chapter、paragraph_index、source_text_hash。
- 输出：带 `paragraph_id` 的 Paragraph。
- 参考来源：AiNiee text_index、GalTransl index、oomol segment id。
- 当前阶段：待设计。
- 后续实现轮次：RM-03。
- 常见风险：只依赖数组下标导致重解析后错位。
- 验收标准：ID 规则稳定，支持重解析报告，支持 `JP_TO_CN` / `CN_TO_JP`。

## JSONL intermediate

- 职责：保存一行一段或一行一 segment 的中间态。
- 输入：Paragraph / Segment、metadata、status。
- 输出：JSONL segment records。
- 参考来源：AiNiee cache、GalTransl JSON cache。
- 当前阶段：待设计。
- 后续实现轮次：RM-04。
- 常见风险：字段漂移、状态不完整、译文直接覆盖原文。
- 验收标准：可机读、可人工审阅、支持断点续跑和校验失败记录。

## segment/chunk

- 职责：按语义边界和 token soft limit 将段落组合或拆分成翻译 batch。
- 输入：JSONL records、token limit、direction rules。
- 输出：chunk metadata、`segment_id` 列表。
- 参考来源：TranslateBooksWithLLMs TokenChunker、oomol incision 权重。
- 当前阶段：待实现。
- 后续实现轮次：RM-06。
- 常见风险：硬切字符串、破坏对话、chunk 太长导致模型失败。
- 验收标准：短段不乱拆，长段可拆，segment 可追溯。

## pre_replace / placeholder

- 职责：保护 URL、控制符、不可翻译词和格式占位符。
- 输入：source_text、non_translate rules、placeholder rules。
- 输出：protected_source_text、placeholder map。
- 参考来源：GalTransl 译前/译后字典、AiNiee 禁翻占位。
- 当前阶段：待实现。
- 后续实现轮次：RM-24。
- 常见风险：占位符丢失、模型翻译控制符、还原错位。
- 验收标准：占位符可还原，Validator 能发现丢失。

## glossary matcher

- 职责：从当前 batch 命中 approved / locked / candidate / conflict / deprecated 术语。
- 输入：source_text、glossary。
- 输出：matched_term_ids、glossary prompt block、risk warnings。
- 参考来源：GalTransl GPT 字典动态注入、AiNiee GlossaryHelper。
- 当前阶段：待实现。
- 后续实现轮次：RM-08。
- 常见风险：全表塞入 Prompt、locked 术语遗漏、deprecated 旧译名残留。
- 验收标准：只注入命中术语，locked 优先，conflict 可见。

## character matcher

- 职责：识别说话人、提及角色和相关称呼规则。
- 输入：source_text、speaker、character profiles。
- 输出：matched_character_ids、character prompt block。
- 参考来源：GalTransl dialogue/name handling、AiNiee AnalysisTask。
- 当前阶段：待实现。
- 后续实现轮次：RM-09。
- 常见风险：旁白过度注入角色、说话人误判、敬语规则遗漏。
- 验收标准：speaker 命中时注入相关角色，未命中时不全量塞表。

## world bible matcher

- 职责：识别当前段落相关地点、组织、技能、制度和设定。
- 输入：source_text、world bible entries。
- 输出：matched_world_bible_ids、world prompt block。
- 参考来源：AiNiee AnalysisTask、GalTransl 字典分层。
- 当前阶段：待实现。
- 后续实现轮次：RM-10。
- 常见风险：剧透提前注入、推测设定当事实、世界观改写原文。
- 验收标准：只注入相关设定，spoiler-sensitive 默认排除，inferred 标记清楚。

## context pack

- 职责：组合当前 source、前文、上一译文、章节信息、命中资产和输出契约。
- 输入：segments、context_before、previous_translation、matched assets。
- 输出：ContextPack。
- 参考来源：TBL context_before / previous_translation、AiNiee pre_line_counts、GalTransl history_result。
- 当前阶段：待实现。
- 后续实现轮次：RM-07。
- 常见风险：上下文过长、提前剧透、未校验译文误导模型。
- 验收标准：ContextPack 可序列化，可定位 segment，支持双方向。

## prompt builder

- 职责：按层组合 system、direction、style、glossary、character、world、context、source、output contract。
- 输入：ContextPack、PromptVersion、direction rules。
- 输出：messages、prompt metadata。
- 参考来源：AiNiee 分层 Prompt、SakuraLLM prompt version、GalTransl ForNovel。
- 当前阶段：待实现。
- 后续实现轮次：RM-11、RM-12。
- 常见风险：Prompt 无版本、输出契约不稳定、方向规则混用。
- 验收标准：Prompt 可组合、有版本、支持 `JP_TO_CN` / `CN_TO_JP`。

## provider adapter

- 职责：统一 fake、dry-run、OpenAI-compatible、DeepSeek、Grok、OpenRouter、Anthropic、Gemini 等 provider 调用。
- 输入：messages、model options、provider config。
- 输出：ModelResult。
- 参考来源：TBL factory、AiNiee LLMRequester、Luna / Ballons registry。
- 当前阶段：策略文档存在，接口需固化。
- 后续实现轮次：RM-20、RM-21。
- 常见风险：泄露 key、无 cost guard、业务层写死 provider。
- 验收标准：fake provider 可跑通，真实 provider 受控，model_run 可记录。

## response extractor

- 职责：解析 JSON 或编号文本，提取 `segment_id`、translation、notes，保存 raw output。
- 输入：ModelResult.raw_output。
- 输出：structured parse result。
- 参考来源：AiNiee ResponseExtractor、BallonsTranslator JSON batch。
- 当前阶段：待实现。
- 后续实现轮次：RM-14。
- 常见风险：JSON 解析失败仍写入译文、segment_id 丢失。
- 验收标准：parse failed 可记录，raw output 可追踪，不污染译文。

## validator

- 职责：检查输出契约、segment 覆盖、locked terms、placeholder、语言残留、长度比例和对齐。
- 输入：structured parse result、ContextPack、knowledge assets。
- 输出：ValidationResult。
- 参考来源：AiNiee ResponseChecker、GalTransl Problem、SakuraLLM line count QA。
- 当前阶段：待实现。
- 后续实现轮次：RM-15。
- 常见风险：校验失败仍进入 final、检查项过度主观。
- 验收标准：validation_failed 不写入 translated/final，错误映射到 ReviewIssue。

## status update

- 职责：根据翻译、解析、校验和重试结果推进状态机。
- 输入：ValidationResult、retry policy、lock flags。
- 输出：updated JSONL / checkpoint。
- 参考来源：AiNiee status JSON、TBL checkpoint、GalTransl append cache。
- 当前阶段：待设计。
- 后续实现轮次：RM-17。
- 常见风险：中断后重复翻译、locked/human_reviewed 被覆盖。
- 验收标准：已翻译可跳过，failed 可重试，locked 安全。

## translation memory update

- 职责：把通过校验或人工确认的 source/target 写入 TM。
- 输入：validated translation、review status、segment metadata。
- 输出：TranslationMemoryEntry。
- 参考来源：TBL checkpoint、GalTransl cache、通用 TM 思路。
- 当前阶段：设计雏形存在。
- 后续实现轮次：RM-28。
- 常见风险：未审核 draft 进入 preferred、与 LLM cache 混淆。
- 验收标准：TM 与 cache 区分，按 project / direction 隔离。

## review issue generation

- 职责：把 validation error、checker error、人工问题统一成 ReviewIssue。
- 输入：ValidationResult、checker reports。
- 输出：ReviewIssue JSONL / report。
- 参考来源：GalTransl Problem、LiteraryTranslation taxonomy。
- 当前阶段：设计雏形存在。
- 后续实现轮次：RM-16、RM-25 到 RM-27。
- 常见风险：issue_type 不统一、无法定位 segment。
- 验收标准：issue 可定位 paragraph/segment，可供前端展示。

## refinement

- 职责：基于原文、初翻、知识资产、issue 和 style profile 生成润色稿。
- 输入：source_text、translation_draft、context pack、known issues。
- 输出：refined_translation、change_log。
- 参考来源：AiNiee polish/proofread、LiteraryTranslation pairwise/error labels。
- 当前阶段：设计雏形存在。
- 后续实现轮次：RM-33、RM-34。
- 常见风险：过度改写、术语被破坏、角色语气被抹平。
- 验收标准：不覆盖初翻，change log 存在，Validator 通过。

## diff / change log

- 职责：比较 draft 与 refined，标记新增、删除、术语变化、语气风险。
- 输入：translation_draft、refined_translation。
- 输出：Markdown diff、JSON diff、over_refinement issue。
- 参考来源：LiteraryTranslation pairwise preference、change log 思路。
- 当前阶段：待设计。
- 后续实现轮次：RM-35。
- 常见风险：只保存最终稿导致无法审计。
- 验收标准：diff 可读，风险可定位，术语变化可发现。

## exporter

- 职责：从中间态生成最终阅读文件和审核文件。
- 输入：JSONL、TranslationDraft、RefinedTranslation、ReviewIssue。
- 输出：Markdown 纯译文、Markdown 双语对照、CSV/JSON review、后期 EPUB。
- 参考来源：AiNiee Writer、oomol SubmitKind / translate + fill。
- 当前阶段：待设计。
- 后续实现轮次：RM-36、RM-37。
- 常见风险：导出 validation_failed、修改原文、导出丢失 ID。
- 验收标准：exporter 不调用模型、不修改原文、不导出 failed 到 final、保留 paragraph_id。
