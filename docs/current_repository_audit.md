# 当前仓库审计

## 扫描时间

2026-06-01，Asia/Shanghai。

## 当前仓库定位

当前仓库原始定位是单本日文轻小说到中文的本地翻译任务仓库。后续应升级为面向长篇小说与轻小说的中日文互译生产流水线，支持 `JP_TO_CN` 和 `CN_TO_JP` 两个方向。

## 已存在目录

- `input_jp/`：已有日文原文输入文件，视为版权敏感内容。
- `output_cn/`：已有中文译文、双语对照、审核资料，视为受保护输出。
- `notes/`：已有术语、人物、概览、风格、规则、进度和不确定术语记录。
- `docs/`：已有项目定位、翻译流水线、术语系统、embedding memory、OpenRouter 测试和路线图文档。
- `prompts/`：已有早期翻译流水线 Prompt。
- `logs/`：已有日志目录。
- `scripts/`：已有格式化和润色相关脚本。
- `config/`、`governance/`、`round_state/`：已有配置和治理状态文件。

## 已存在文档

- `README.md`
- `.gitignore`
- `docs/index.md`
- `docs/translation_project_positioning.md`
- `docs/translation_pipeline_design.md`
- `docs/terminology_system_design.md`
- `docs/embedding_memory_design.md`
- `docs/openrouter_api_test_plan.md`
- `docs/roadmap_translation_pipeline.md`
- `docs/reports/translation_project_scan_report.md`

未发现但旧 prompt 中提到的文档：

- `docs/workflow.md`
- `docs/file_naming_rules.md`
- `docs/translation_quality_rules.md`
- `docs/next_round_prompt_guide.md`

## 已存在 Prompt

- `prompts/openclaw_translation_governance.md`
- `prompts/cursor_translation_pipeline_round.md`
- `prompts/codex_translation_pipeline_round.md`

未发现但旧 README 中提到的 Prompt：

- `prompts/01_prepare_after_source_added.md`
- `prompts/02_translate_batch.md`
- `prompts/03_consistency_review.md`

## 已存在 notes 文件

- `notes/source_file_manifest.md`
- `notes/novel_overview.md`
- `notes/glossary.md`
- `notes/character_names.md`
- `notes/style_guide.md`
- `notes/translation_rules.md`
- `notes/uncertain_terms.md`
- `notes/translation_progress.md`

## 当前结构优点

1. 已经形成输入、输出、notes、docs、prompts 的基本分层。
2. 已有术语表、人物表、风格指南和翻译规则，便于继续治理一致性。
3. 已有双语对照、审核和翻译进度目录，说明早期日译中流程具备可追踪意识。
4. 已有 `.gitignore` 对 `.env`、缓存、原文和译文输出做了初步保护。
5. 已有 OpenRouter、embedding memory、翻译流水线等方向性文档，可作为新架构的历史参考。

## 当前结构不足

1. 仓库定位仍偏向单本 `JP_TO_CN` 翻译任务。
2. 缺少 `input_cn/`、`output_jp/` 和 `CN_TO_JP` 方向目录。
3. 缺少明确的 shared core 与方向专属模块边界。
4. 缺少 project-level data schema、workspace 规划和 model run 记录规范。
5. 缺少 provider adapter、embedding adapter、vector store adapter 的统一抽象。
6. 缺少长期 40+ 轮路线图和不同轮次 Prompt 模板。
7. 缺少前端工作台的信息架构与页面规划。

## 需要保留的内容

- 旧目录：`input_jp/`、`output_cn/`、`notes/`、`docs/`、`prompts/`、`logs/`、`scripts/`。
- 旧 notes 文件与已有术语、人物、风格、规则、进度记录。
- 早期 docs 和 prompts，它们可作为 `JP_TO_CN` 历史资料。
- 已有真实原文和译文文件。治理轮不得删除、覆盖、迁移或提交这些内容。

## 需要扩展的内容

- 双向输入输出目录：`input_cn/`、`output_jp/`。
- 共享核心目录：`shared/`。
- 方向专属目录：`directions/jp_to_cn/`、`directions/cn_to_jp/`。
- 中间数据目录：`workspace/`。
- 项目级结构化数据目录：`data/`。
- 未来代码、前端、测试目录：`src/`、`frontend/`、`tests/`。
- 项目愿景、总体架构、数据 schema、治理规则、迁移说明、路线图、Prompt 模板。

## 本轮不应修改或删除的内容

1. 不修改 `input_jp/` 中任何真实原文。
2. 不修改 `output_cn/translated/`、`output_cn/bilingual/`、`output_cn/review/` 中任何已有译文或审核成果。
3. 不删除旧 docs、notes、prompts、scripts。
4. 不调用真实 API，不生成真实 embedding，不建立真实向量库。
5. 不提交 `.env`、API Key、真实原文或真实译文。
