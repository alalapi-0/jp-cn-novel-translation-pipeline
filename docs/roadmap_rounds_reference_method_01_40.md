# 参考仓库方法吸收后的 40 轮推进路线

本路线图用于把参考仓库中的成熟工程方法落到当前中日文小说互译项目。RM 代表 Reference Method Absorption，不替代既有 Round 00-50 路线。每轮都必须遵守原文只读、JSONL 中间态、provider adapter、Validator、exporter-only 和安全治理规则。

## Round RM-01：参考仓库方法迁移总览

### 轮次类型

governance

### 参考来源

AiNiee, GalTransl, TBL, SakuraLLM, LiteraryTranslation, oomol

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“参考仓库方法迁移总览”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

将参考仓库分析整理为当前项目自己的方法迁移总纲。

### 具体任务

1. 创建参考方法总纲。
2. 归纳 P0/P1/P2 方法。
3. 标记不迁移内容。
4. 映射到当前项目模块。
5. 更新 README。
6. 更新治理规则。
7. 说明只迁移方法不复制代码。

### 产出文件

与 RM-01 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 文档存在。
2. P0/P1/P2 分类清楚。
3. 每个方法有项目落点。
4. 不迁移内容明确。
5. 后续路线能引用。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-02，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-02：核心数据链路设计

### 轮次类型

schema design

### 参考来源

AiNiee CacheItem, GalTransl JSON, TBL checkpoint_chunks, oomol InlineSegment

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“核心数据链路设计”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

设计 SourceFile → Chapter → Paragraph → Segment → TranslationDraft → RefinedTranslation → ExportedDocument 的主链路。

### 具体任务

1. 定义 SourceFile。
2. 定义 Chapter。
3. 定义 Paragraph。
4. 定义 Segment。
5. 定义 TranslationDraft。
6. 定义 RefinedTranslation。
7. 定义 ReviewIssue。
8. 定义 ExportedDocument。
9. 说明对象关系。
10. 更新 data schema。

### 产出文件

与 RM-02 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 每个对象职责明确。
2. 每个对象核心字段明确。
3. 原文只读原则明确。
4. Exporter-only 原则明确。
5. 可支撑 JSONL 实现。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-03，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-03：稳定 ID 规则

### 轮次类型

schema design

### 参考来源

AiNiee text_index, GalTransl index, oomol segment id

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“稳定 ID 规则”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

设计 paragraph_id / segment_id / chapter_id / source_file_id。

### 具体任务

1. 定义 source_file_id。
2. 定义 chapter_id。
3. 定义 paragraph_id。
4. 定义 segment_id。
5. 设计 ID 生成规则。
6. 设计重解析迁移报告。
7. 设计 ID 与 ReviewIssue 的绑定。
8. 设计 ID 与 Exporter 的绑定。
9. 设计 ID 与 TranslationMemory 的绑定。
10. 写入稳定 ID 文档。

### 产出文件

与 RM-03 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. ID 规则稳定。
2. ID 不只依赖数组下标。
3. 支持段落拆分。
4. 支持重解析报告。
5. 支持双向翻译。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-04，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-04：JSONL 中间态 Schema

### 轮次类型

schema design

### 参考来源

GalTransl JSON cache, AiNiee status cache

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“JSONL 中间态 Schema”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

建立 MVP 可用的一行一段 JSONL。

### 具体任务

1. 设计 JSONL 字段。
2. 设计 status 状态机。
3. 设计 locked。
4. 设计 human_reviewed。
5. 设计 prompt_version。
6. 设计 glossary_version。
7. 设计 model metadata。
8. 设计 validation_errors。
9. 设计 review_issues。
10. 创建样例 JSONL。

### 产出文件

与 RM-04 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. schema 可读。
2. schema 可机读。
3. 支持 JP_TO_CN。
4. 支持 CN_TO_JP。
5. 支持断点续跑。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-05，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-05：Parser MVP

### 轮次类型

implementation

### 参考来源

AiNiee Reader/Writer 插件边界, TBL 文本解析

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“Parser MVP”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

把 .txt / .md 原文解析为 JSONL 中间态。

### 具体任务

1. 扫描 input_jp。
2. 扫描 input_cn。
3. 解析章节。
4. 解析段落。
5. 生成 paragraph_id。
6. 生成 source_text_hash。
7. 输出 JSONL。
8. 输出 manifest。
9. 增加 sample。
10. 增加测试。

### 产出文件

与 RM-05 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. .txt 可解析。
2. .md 可解析。
3. 原文不被修改。
4. JSONL 符合 schema。
5. 测试通过。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-06，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-06：语义分块与 TokenChunker

### 轮次类型

implementation

### 参考来源

TBL TokenChunker, oomol incision 权重

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“语义分块与 TokenChunker”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

实现语义边界优先的 chunker。

### 具体任务

1. 设计 token estimator。
2. 实现 paragraph-level chunk。
3. 实现 long paragraph split。
4. 优先句号边界。
5. 优先对话边界。
6. 不硬切字符串。
7. 输出 chunk metadata。
8. 支持 max token 配置。
9. 支持 failed chunk 拆小重试。
10. 增加测试。

### 产出文件

与 RM-06 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 长段可拆。
2. 短段不乱拆。
3. 对话不破坏。
4. chunk 可追溯 segment。
5. context pack 可使用。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-07，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-07：Context Pack MVP

### 轮次类型

implementation

### 参考来源

TBL context_before/context_after/previous_translation, GalTransl history_result, AiNiee pre_line_counts

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“Context Pack MVP”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

为每次翻译构建上下文包。

### 具体任务

1. 定义 context pack schema。
2. 注入前文原文。
3. 注入上一段译文。
4. 注入章节标题。
5. 注入章节摘要占位。
6. 注入 matched glossary。
7. 注入 matched character。
8. 注入 matched world bible。
9. 输出 context pack JSON/Markdown。
10. 增加测试。

### 产出文件

与 RM-07 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. context pack 可生成。
2. 不塞全书。
3. 可按 segment 定位。
4. 支持两个方向。
5. 可供 PromptBuilder 使用。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-08，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-08：动态术语匹配器

### 轮次类型

implementation

### 参考来源

GalTransl GPT 字典动态注入, AiNiee GlossaryHelper

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“动态术语匹配器”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

实现当前 batch 命中的术语动态注入。

### 具体任务

1. 读取 glossary。
2. 支持 approved。
3. 支持 locked。
4. 支持 candidate。
5. 扫描 source_text。
6. 输出 matched_term_ids。
7. 输出 prompt glossary block。
8. 支持 deprecated 检测。
9. 支持 conflict warning。
10. 增加测试。

### 产出文件

与 RM-08 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 不全量塞表。
2. 命中词条可注入。
3. locked 优先。
4. deprecated 可检测。
5. prompt block 可用。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-09，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-09：角色注入与说话人识别

### 轮次类型

implementation

### 参考来源

GalTransl dialogue/name handling, AiNiee AnalysisTask

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“角色注入与说话人识别”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

为 dialogue / narration 动态注入角色设定。

### 具体任务

1. 读取 character profiles。
2. 识别 speaker 字段。
3. 区分 narration/dialogue/thought。
4. 注入当前角色语气。
5. 注入称呼规则。
6. 注入口癖。
7. 注入 voice examples。
8. 输出 character block。
9. 增加测试。
10. 更新文档。

### 产出文件

与 RM-09 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. speaker 命中时注入相关角色。
2. narration 不全量注入角色。
3. 角色语气进入 prompt。
4. CN_TO_JP 敬语重建可用。
5. JP_TO_CN 敬称处理可用。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-10，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-10：World Bible 动态注入

### 轮次类型

implementation

### 参考来源

AiNiee AnalysisTask, GalTransl 字典分层

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“World Bible 动态注入”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

将当前段落相关世界观设定注入 context。

### 具体任务

1. 读取 world bible。
2. 匹配地名。
3. 匹配组织。
4. 匹配技能名。
5. 匹配制度名。
6. 排除 spoiler-sensitive。
7. 标记 inferred。
8. 输出 world bible block。
9. 增加测试。
10. 更新文档。

### 产出文件

与 RM-10 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 只注入相关设定。
2. spoiler 不提前注入。
3. inferred 明确标记。
4. 不改写原文含义。
5. context pack 可引用。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-11，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-11：PromptBuilder 分层架构

### 轮次类型

implementation

### 参考来源

AiNiee 分层 Prompt, SakuraLLM prompt version, GalTransl ForNovel

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“PromptBuilder 分层架构”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

实现可组合 PromptBuilder。

### 具体任务

1. 定义 prompt layers。
2. 支持 system_base。
3. 支持 direction_rules。
4. 支持 style_profile。
5. 支持 glossary_block。
6. 支持 character_block。
7. 支持 world_bible_block。
8. 支持 context_block。
9. 支持 source_block。
10. 支持 output_contract。
11. 记录 prompt_version。
12. 增加测试。

### 产出文件

与 RM-11 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. Prompt 可组合。
2. Prompt 有版本。
3. 支持 JP_TO_CN。
4. 支持 CN_TO_JP。
5. 输出可供 provider 使用。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-12，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-12：Prompt 版本矩阵

### 轮次类型

prompt governance

### 参考来源

SakuraLLM get_prompt(model_version)

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“Prompt 版本矩阵”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

建立 prompt version matrix。

### 具体任务

1. 创建 prompt registry。
2. 定义 initial translation prompt。
3. 定义 refinement prompt。
4. 定义 review prompt。
5. 定义 terminology extraction prompt。
6. 定义 character extraction prompt。
7. 定义 JP_TO_CN 版本。
8. 定义 CN_TO_JP 版本。
9. 写入 changelog。
10. 更新 docs。

### 产出文件

与 RM-12 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 每个 Prompt 有版本。
2. 修改有 changelog。
3. ModelRun 记录 prompt_version。
4. cache key 可引用。
5. 重译计划可判断版本变化。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-13，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-13：机器可解析输出契约

### 轮次类型

implementation

### 参考来源

AiNiee 序号 batch, BallonsTranslator JSON batch, SakuraLLM 行数对齐

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“机器可解析输出契约”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

实现 JSON 输出契约和编号 fallback。

### 具体任务

1. 定义 JSON contract。
2. 定义 numbered fallback。
3. Prompt 要求 segment_id。
4. 定义 missing item 行为。
5. 定义 extra item 行为。
6. 定义 parse error 行为。
7. 创建输出样例。
8. 增加测试。
9. 更新 docs。
10. 接入 PromptBuilder。

### 产出文件

与 RM-13 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 输出可解析。
2. segment_id 不丢。
3. fallback 可用。
4. 缺失可检测。
5. 不合格不写成功。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-14，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-14：ResponseExtractor MVP

### 轮次类型

implementation

### 参考来源

AiNiee ResponseExtractor

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“ResponseExtractor MVP”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

解析模型输出为结构化结果。

### 具体任务

1. 解析 JSON。
2. 解析编号文本。
3. 提取 segment_id。
4. 提取 translation。
5. 提取 notes。
6. 处理 parse_errors。
7. 保存 raw output。
8. 输出 parse result。
9. 增加测试。
10. 接入 fake provider。

### 产出文件

与 RM-14 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. JSON 可解析。
2. 编号文本可解析。
3. 错误可记录。
4. raw output 可追踪。
5. parse failed 不污染译文。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-15，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-15：Validator MVP

### 轮次类型

implementation

### 参考来源

AiNiee ResponseChecker, GalTransl Problem, SakuraLLM line count QA

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“Validator MVP”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

实现初步翻译结果校验。

### 具体任务

1. 检查非空。
2. 检查 segment_id 覆盖。
3. 检查多余 segment。
4. 检查 locked terms。
5. 检查 placeholder。
6. 检查源语言残留。
7. 检查长度比例。
8. 检查段落对齐。
9. 输出 ValidationResult。
10. 增加测试。

### 产出文件

与 RM-15 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 校验失败不写 translated。
2. locked term violation 可发现。
3. 残留源语言可发现。
4. 缺段可发现。
5. ValidationResult 可进入 ReviewIssue。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-16，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-16：Problem Taxonomy 与 ReviewIssue

### 轮次类型

review design / implementation

### 参考来源

GalTransl Problem, LiteraryTranslation error taxonomy

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“Problem Taxonomy 与 ReviewIssue”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

建立错误分类和 ReviewIssue schema。

### 具体任务

1. 创建 taxonomy。
2. 定义 issue_type。
3. 定义 severity。
4. 定义 suggested_action。
5. 定义 auto_fixable。
6. 定义 requires_human_review。
7. 将 validator error 映射到 issue。
8. 输出 review issue JSONL。
9. 增加测试。
10. 更新 docs。

### 产出文件

与 RM-16 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 错误分类明确。
2. validator 可生成 issue。
3. issue 可定位 segment。
4. issue 可供前端展示。
5. 支持人工审核状态。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-17，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-17：状态机与断点续跑 MVP

### 轮次类型

implementation

### 参考来源

AiNiee status JSON, TBL checkpoint, GalTransl append cache

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“状态机与断点续跑 MVP”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

实现 JSONL status 驱动断点续跑。

### 具体任务

1. 实现 status transition。
2. untranslated → queued。
3. queued → translating。
4. translating → translated / failed。
5. failed → retry_pending。
6. locked 不覆盖。
7. human_reviewed 不覆盖。
8. progress summary。
9. failed list。
10. 增加测试。

### 产出文件

与 RM-17 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 已翻译段不重复翻。
2. failed 可重试。
3. locked 安全。
4. 进度可读。
5. 中断后可继续。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-18，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-18：SQLite Checkpoint 方案

### 轮次类型

implementation design / implementation

### 参考来源

TranslateBooksWithLLMs checkpoint_chunks

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“SQLite Checkpoint 方案”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

在 JSONL 基础上设计 SQLite checkpoint。

### 具体任务

1. 设计 SQLite schema。
2. 设计 checkpoint_chunks。
3. 设计 model_runs。
4. 设计 validation_results。
5. 设计 review_issues。
6. 设计 retry_queue。
7. 支持 JSONL → SQLite。
8. 支持 SQLite → JSONL。
9. 增加测试。
10. 更新 docs。

### 产出文件

与 RM-18 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. SQLite 可选。
2. JSONL 仍可用。
3. failed 优先重试。
4. 数据可导出。
5. 不绑定唯一存储。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-19，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-19：LLM Response Hash Cache

### 轮次类型

implementation

### 参考来源

epub-translator-oomol hash cache

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“LLM Response Hash Cache”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

避免相同请求重复调用 API。

### 具体任务

1. 定义 cache key。
2. 包含 source_text_hash。
3. 包含 prompt_version。
4. 包含 glossary_version。
5. 包含 character_profile_version。
6. 包含 style_profile_version。
7. 包含 provider_id/model_id。
8. 保存 raw response。
9. 支持 cache hit。
10. 支持 invalidation。
11. 增加测试。

### 产出文件

与 RM-19 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 相同请求可命中。
2. Prompt 变更失效。
3. glossary 变更失效。
4. cache 与 checkpoint 区分。
5. 不缓存敏感 key。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-20，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-20：Provider Adapter Registry MVP

### 轮次类型

implementation

### 参考来源

TBL factory, AiNiee LLMRequester, Luna/Ballons Registry

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“Provider Adapter Registry MVP”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

实现 provider 注册表。

### 具体任务

1. 定义 ModelAdapter。
2. 实现 FakeProvider。
3. 实现 DryRunProvider。
4. 设计 OpenAICompatibleProvider。
5. 设计 provider config。
6. 记录 model_run。
7. 实现 retry skeleton。
8. 实现 timeout skeleton。
9. 实现 cost estimate placeholder。
10. 增加测试。

### 产出文件

与 RM-20 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. fake provider 可跑通。
2. dry-run 不调用 API。
3. provider 可配置。
4. model_run 可记录。
5. 后续可接真实 API。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-21，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-21：OpenAI-Compatible Provider 受控试跑

### 轮次类型

api integration

### 参考来源

TBL / AiNiee 多 API 适配逻辑

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“OpenAI-Compatible Provider 受控试跑”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

接入 OpenAI-compatible provider 的小规模受控测试。

### 具体任务

1. 读取 .env。
2. 不输出 key。
3. 支持 base_url。
4. 支持 model。
5. 支持 max cost。
6. 支持 dry-run。
7. 用 sample text 测试。
8. 记录 model_run。
9. 记录 usage。
10. 生成报告。

### 产出文件

与 RM-21 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 不泄露 key。
2. dry-run 可用。
3. controlled run 可用。
4. 成本有记录。
5. 不处理真实整本书。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-22，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-22：Batch Translation Pipeline with Fake Provider

### 轮次类型

implementation

### 参考来源

AiNiee batch, GalTransl batch, Ballons JSON batch

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“Batch Translation Pipeline with Fake Provider”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

用 fake provider 跑通批量翻译链路。

### 具体任务

1. 读取 untranslated segments。
2. 分 batch。
3. 构建 context pack。
4. 构建 prompt。
5. 调 fake provider。
6. ResponseExtractor 解析。
7. Validator 校验。
8. 写 JSONL status。
9. 输出 progress。
10. 增加测试。

### 产出文件

与 RM-22 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 批量链路跑通。
2. 不调用真实 API。
3. 校验失败不写成功。
4. status 更新正确。
5. 可进入真实小规模测试。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-23，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-23：真实批量初翻受控试跑

### 轮次类型

translation execution / controlled api

### 参考来源

AiNiee / TBL 长跑控制

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“真实批量初翻受控试跑”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

对 sample 或用户明确指定的小章节进行真实批量初翻试跑。

### 具体任务

1. 启用 cost guard。
2. 限制 batch 数。
3. 限制章节数。
4. 记录 provider。
5. 记录 prompt_version。
6. 记录 validation。
7. 输出 bilingual draft。
8. 输出 report。
9. 不覆盖 locked。
10. 不自动跑整本。

### 产出文件

与 RM-23 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 真实小规模跑通。
2. 输出可审计。
3. 成本可控。
4. 失败可重试。
5. 不泄露敏感信息。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-24，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-24：Pre/Post Replace Pipeline

### 轮次类型

implementation

### 参考来源

GalTransl 译前/译后字典, AiNiee 禁翻占位

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“Pre/Post Replace Pipeline”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

实现译前保护与译后还原。

### 具体任务

1. 设计 pre_replace。
2. 设计 post_replace。
3. 支持 non_translate。
4. 支持 placeholders。
5. 支持控制符保护。
6. 支持 URL 保护。
7. 支持人名硬替换。
8. Validator 检查占位符。
9. 增加测试。
10. 更新 docs。

### 产出文件

与 RM-24 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 禁翻内容不被模型改写。
2. 占位符可还原。
3. 控制符不丢。
4. URL 不丢。
5. 错误可报告。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-25，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-25：术语一致性 Checker

### 轮次类型

review implementation

### 参考来源

GalTransl Problem, AiNiee ProofreadTask

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“术语一致性 Checker”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

检查术语一致性。

### 具体任务

1. 读取 approved glossary。
2. 扫描译文。
3. 检查 locked term。
4. 检查 deprecated translation。
5. 检查同源多译。
6. 生成 ReviewIssue。
7. 支持 false positive。
8. 输出 report。
9. 增加测试。
10. 更新 docs。

### 产出文件

与 RM-25 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 能发现术语冲突。
2. 能定位 paragraph_id。
3. locked violation 阻止 final。
4. deprecated 可发现。
5. 报告可读。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-26，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-26：角色语气 Checker

### 轮次类型

review implementation

### 参考来源

LiteraryTranslation REGISTER, GalTransl dialogue handling

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“角色语气 Checker”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

检查角色称呼和语气一致性。

### 具体任务

1. 读取 character profiles。
2. 检查称呼规则。
3. 检查 first_person。
4. 检查敬语等级。
5. 检查口癖。
6. 检查 speaker consistency。
7. 生成 voice conflict。
8. 输出 report。
9. 增加测试。
10. 更新 docs。

### 产出文件

与 RM-26 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 称呼冲突可发现。
2. 第一人称不一致可发现。
3. 敬语异常可发现。
4. 可定位 segment。
5. 可供前端展示。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-27，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-27：世界观设定 Checker

### 轮次类型

review implementation

### 参考来源

AiNiee AnalysisTask + LiteraryTranslation consistency labels

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“世界观设定 Checker”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

检查地名、组织、技能、制度等设定冲突。

### 具体任务

1. 读取 world bible。
2. 扫描译文。
3. 检查地名译法。
4. 检查组织译法。
5. 检查技能名译法。
6. 检查称号体系。
7. 生成 world conflict issue。
8. 输出 report。
9. 增加测试。
10. 更新 docs。

### 产出文件

与 RM-27 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 设定冲突可发现。
2. 可追溯原文证据。
3. inferred 不当事实可标记。
4. issue 可定位。
5. 支持润色阶段使用。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-28，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-28：Translation Memory MVP

### 轮次类型

implementation

### 参考来源

TBL checkpoint, GalTransl cache, 翻译记忆思想

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“Translation Memory MVP”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

保存已翻译片段并支持检索。

### 具体任务

1. 设计 TM schema。
2. 写入 source/target。
3. 记录 segment_id。
4. 记录 speaker。
5. 记录 term_ids。
6. 支持 exact match。
7. 支持 hash match。
8. 支持导出。
9. 增加测试。
10. 更新 docs。

### 产出文件

与 RM-28 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 翻译完成后可写入 TM。
2. 相同原文可命中。
3. TM 与 LLM cache 区分。
4. 可供 context pack 使用。
5. 支持两个方向。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-29，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-29：Embedding Similar Segment Retrieval

### 轮次类型

implementation / retrieval

### 参考来源

TBL context, 当前项目 embedding 规划

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“Embedding Similar Segment Retrieval”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

为相似段落检索接入 embedding 流程。

### 具体任务

1. 读取 segments。
2. 生成 fake embedding。
3. 接入 fake vector store。
4. 支持 metadata。
5. 支持 project filter。
6. 支持 direction filter。
7. 支持 chapter filter。
8. context pack 注入 similar segments。
9. 增加测试。
10. 不调用真实 embedding API。

### 产出文件

与 RM-29 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. fake embedding 跑通。
2. metadata 完整。
3. 检索结果可过滤。
4. context pack 可使用。
5. 后续可接真实 embedding。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-30，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-30：真实 Embedding 受控试跑

### 轮次类型

api integration / retrieval

### 参考来源

向量检索方案

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“真实 Embedding 受控试跑”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

用小样例执行真实 embedding 受控试跑。

### 具体任务

1. 选择 provider。
2. 启用 cost guard。
3. 只处理 sample。
4. 生成 embedding。
5. 写入本地 vector store。
6. 检索相似段。
7. 输出报告。
8. 不处理真实长篇。
9. 不泄露 key。
10. 更新 docs。

### 产出文件

与 RM-30 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 真实 embedding 可用。
2. 成本可控。
3. 检索可用。
4. metadata 完整。
5. 可回滚。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-31，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-31：AnalysisTask 自动抽取

### 轮次类型

implementation / controlled LLM

### 参考来源

AiNiee AnalysisTask

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“AnalysisTask 自动抽取”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

实现术语、角色、世界观候选抽取。

### 具体任务

1. 设计 analysis task。
2. 抽术语候选。
3. 抽角色候选。
4. 抽世界观候选。
5. 支持 map-reduce。
6. 输出 candidates。
7. 写入 notes/data。
8. 支持 fake provider。
9. 支持 controlled real run。
10. 生成报告。

### 产出文件

与 RM-31 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 可生成候选术语。
2. 可生成角色候选。
3. 可生成世界观候选。
4. 不把候选直接 approved。
5. 可供人工或 AI 审核。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-32，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-32：知识资产审核工作流

### 轮次类型

review workflow

### 参考来源

AiNiee AnalysisTask + ProofreadTask

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“知识资产审核工作流”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

把候选术语、角色、世界观变成 approved 资产。

### 具体任务

1. candidate → approved。
2. candidate → rejected。
3. candidate → needs_review。
4. 支持 locked。
5. 支持人工备注。
6. 支持 AI 建议理由。
7. 支持冲突合并。
8. 输出 review table。
9. 更新 context pack。
10. 更新 docs。

### 产出文件

与 RM-32 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. approved 与 candidate 分离。
2. locked 生效。
3. 冲突可记录。
4. 审核结果可追踪。
5. 翻译阶段只强制 approved/locked。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-33，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-33：Refinement Pipeline with Change Log

### 轮次类型

implementation

### 参考来源

AiNiee polish/proofread, LiteraryTranslation pairwise/error labels

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“Refinement Pipeline with Change Log”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

实现基于初翻的二次润色流程。

### 具体任务

1. 读取原文。
2. 读取初翻。
3. 读取 glossary。
4. 读取 character。
5. 读取 world bible。
6. 构建 refine prompt。
7. 调 fake provider。
8. 输出 refined_translation。
9. 输出 change_log。
10. Validator 检查。

### 产出文件

与 RM-33 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 润色不覆盖初翻。
2. change log 存在。
3. 术语不被破坏。
4. 角色语气可检查。
5. 可接真实 provider。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-34，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-34：强模型润色受控试跑

### 轮次类型

translation execution / controlled api

### 参考来源

用户计划使用强推理模型进行二次润色

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“强模型润色受控试跑”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

使用小样例执行强模型润色试跑。

### 具体任务

1. 选择样例段。
2. 构建 refine context。
3. 启用 cost guard。
4. 调强模型。
5. 输出 refined。
6. 输出 change log。
7. 执行 validator。
8. 执行 diff。
9. 生成报告。
10. 不跑整本。

### 产出文件

与 RM-34 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 润色质量可比较。
2. change log 有效。
3. 没有过度改写。
4. 成本记录完整。
5. 可决定是否扩大。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-35，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-35：Diff 与 Over-refinement 检查

### 轮次类型

review implementation

### 参考来源

LiteraryTranslation pairwise preference, change log 思想

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“Diff 与 Over-refinement 检查”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

检测润色是否过度改写。

### 具体任务

1. 实现 draft vs refined diff。
2. 标记新增内容。
3. 标记删除内容。
4. 标记术语变化。
5. 标记角色语气变化。
6. 标记语义风险。
7. 生成 over_refinement issue。
8. 输出 Markdown diff。
9. 输出 JSON diff。
10. 增加测试。

### 产出文件

与 RM-35 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. diff 可读。
2. 风险可定位。
3. 术语变化可发现。
4. 过度润色可标记。
5. 可供前端展示。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-36，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-36：Exporter MVP

### 轮次类型

implementation

### 参考来源

AiNiee Writer, oomol SubmitKind

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“Exporter MVP”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

从中间态生成 Markdown 纯译文和双语对照。

### 具体任务

1. 读取 JSONL。
2. 过滤 final/draft。
3. 生成 pure translated Markdown。
4. 生成 bilingual Markdown。
5. 保留 paragraph_id。
6. 插入 source URL。
7. 插入小字说明。
8. 输出 review CSV。
9. 增加测试。
10. 更新 docs。

### 产出文件

与 RM-36 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. Markdown 可读。
2. 双语对照清晰。
3. paragraph_id 保留。
4. validation_failed 不进 final。
5. 不修改原文。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-37，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-37：EPUB 双阶段设计与 Prototype

### 轮次类型

implementation design / prototype

### 参考来源

epub-translator-oomol translate + fill

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“EPUB 双阶段设计与 Prototype”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

规划 EPUB 后期导出能力。

### 具体任务

1. 设计 EPUB parse。
2. 设计 segment extraction。
3. 设计 pure text translation。
4. 设计 fill back。
5. 设计 id validation。
6. 设计 HTML tag preservation。
7. 设计 REPLACE / APPEND_BLOCK。
8. 做最小 prototype。
9. 不处理真实 EPUB。
10. 更新 docs。

### 产出文件

与 RM-37 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 双阶段思想清楚。
2. id 不丢。
3. 标签不被模型翻译。
4. prototype 可运行或文档足够。
5. 不影响 Markdown 主线。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-38，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-38：Small Benchmark 与质量样例集

### 轮次类型

evaluation design

### 参考来源

LiteraryTranslation benchmark

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“Small Benchmark 与质量样例集”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

建立小型翻译质量 benchmark。

### 具体任务

1. 选择无版权或自造样例。
2. 覆盖 narration。
3. 覆盖 dialogue。
4. 覆盖 honorific。
5. 覆盖 term consistency。
6. 覆盖 character voice。
7. 覆盖 world term。
8. 定义 expected behavior。
9. 定义 error labels。
10. 集成到 tests 或 reports。

### 产出文件

与 RM-38 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. benchmark 不含版权文本。
2. 覆盖关键错误类型。
3. 可用于回归测试。
4. 可比较不同 prompt。
5. 可比较不同 provider。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-39，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-39：Review Workbench Data Contract

### 轮次类型

frontend/data contract

### 参考来源

AiNiee EditView 思路, LiteraryTranslation span/error labels

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“Review Workbench Data Contract”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

为未来前端审核页面定义数据契约。

### 具体任务

1. 定义 review page input JSON。
2. 定义 glossary editor data。
3. 定义 character editor data。
4. 定义 bilingual viewer data。
5. 定义 issue list data。
6. 定义 diff viewer data。
7. 定义 status update action。
8. 定义 locked action。
9. 定义 human reviewed action。
10. 更新 frontend docs。

### 产出文件

与 RM-39 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 前端知道读什么数据。
2. 前端知道写什么数据。
3. issue 可定位段落。
4. locked 可回写。
5. 可进入 UI 实现。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 RM-40，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。

## Round RM-40：End-to-End Sample Pipeline

### 轮次类型

end-to-end validation

### 参考来源

AiNiee + GalTransl + TBL + SakuraLLM + LiteraryTranslation 综合方法栈

### 背景

当前项目需要把参考仓库方法转化为自身可执行能力。本轮聚焦“End-to-End Sample Pipeline”，并保持 `JP_TO_CN` / `CN_TO_JP` 方向分离、shared core 复用和治理轮安全边界。

### 目标

用无版权小样例跑通 parser → JSONL → context → fake/controlled translate → validate → export。

### 具体任务

1. 准备 sample。
2. parser。
3. JSONL。
4. glossary match。
5. context pack。
6. PromptBuilder。
7. fake provider。
8. extractor。
9. validator。
10. exporter。
11. report。

### 产出文件

与 RM-40 相关的 docs、data schema、src、tests、prompts 或 reports；具体路径由本轮 Prompt 进一步限定。

### 验收标准

1. 完整链路跑通。
2. 不调用真实 API，除非 controlled。
3. 输出可审计。
4. 错误可报告。
5. 可作为后续开发基线。

### 不做事项

不处理真实版权长篇，不提交 `.env`、真实原文或真实译文；除非本轮类型明确为受控 API / translation execution 且用户授权，否则不调用真实 API、不生成真实 embedding、不建立真实向量库。

### 风险与注意事项

必须避免把参考仓库代码或目录结构照搬进本项目；必须保持 JSONL 中间态、稳定 ID、Validator 和 exporter-only 原则；涉及用户数据时优先保守处理。

### 下一轮衔接

完成后进入 既有 Round 41 或下一阶段规划，并在 `governance/round_state.yaml` 或本轮报告中记录完成状态。
