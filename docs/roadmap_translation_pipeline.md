# 翻译流水线路线图 (Roadmap)

本路线图按 **Round** 划分，覆盖项目从当前状态到完整自动化流水线的演进。每个 Round 包含目标、前置条件、关键输入/输出文件、任务、验收标准、风险点以及“不做什么”。

---

## Round T0：项目状态同步治理轮
**目标**
- 同步 README、docs、CHANGELOG、notes 与实际输出目录的状态。
**前置条件**
- 已完成全章节翻译（见 `output_cn/translated/`）。
**输入文件**
- `README.md`, `docs/`, `notes/`, `output_cn/` 等。
**输出文件**
- 更新的 `README.md`, `docs/index.md`, `CHANGELOG.md`, `docs/reports/translation_project_scan_report.md`。
**阶段任务**
1. 检查 README 是否过期。
2. 更新项目当前状态。
3. 补充目录说明。
4. 补充已有翻译成果说明。
5. 更新 CHANGELOG。
6. 更新 docs/index.md。
7. 生成状态同步报告。
**验收标准**
- README 不再声称项目停留在初始化阶段。
- docs/index.md 能导航到核心文档。
- CHANGELOG 有记录。
- 不修改原文和译文。
**风险点**
- 误删或覆盖已有译文。
- 忽略文档一致性导致误导。
**不做什么**
- 不进行全量翻译。
- 不修改 `output_cn/translated/` 内容。

---

## Round T1：术语库结构化治理轮
**目标**
- 强化 `glossary.md`、`character_names.md`、`uncertain_terms.md` 的结构与流程。
**前置条件**
- 完整的 `notes/` 目录已存在。
**输入文件**
- `notes/glossary.md`, `notes/character_names.md`, `notes/uncertain_terms.md`。
**输出文件**
- `docs/terminology_system_design.md`（已创建）。
**阶段任务**
1. 检查现有术语表字段。
2. 补充双向翻译字段（日文译名、中文译名）。
3. 明确人工确认状态字段。
4. 设计术语优先级。
5. 设计不确定术语进入人工确认流程。
6. 生成术语库规范文档。
**验收标准**
- 术语字段清楚。
- 人名字段清楚。
- 不确定术语处理流程清楚。
- 不直接批量改译文。
**风险点**
- 误删已确认条目。
- 术语冲突未及时记录。
**不做什么**
- 不自动更新已有译文。

---

## Round T2：初译脚本骨架轮
**目标**
- 新增 OpenRouter 初译脚本骨架，但不进行全量翻译。
**前置条件**
- 完成 T1，已有术语库。
**输入文件**
- `config/openrouter.example.yaml`, `.env.example`。
**输出文件**
- `scripts/translate_draft.py`（脚本骨架），`output_cn/experiments/`（实验目录）。
**阶段任务**
1. 创建 `config/openrouter.example.yaml`。
2. 创建 `.env.example`（已完成）。
3. 创建 `scripts/translate_draft.py`（占位脚本，支持 dry‑run）。
4. 支持指定单文件和字符范围。
5. 输出到 `output_cn/experiments/`，不覆盖正式译文。
**验收标准**
- dry‑run 能运行并生成计划日志。
- 不需要真实 API 也能显示计划。
- 真实 API 调用必须由用户显式开启。
- 不读取或打印完整 key。
**风险点**
- 脚本误写导致覆盖正式译文。
- 配置文件泄漏密钥。
**不做什么**
- 不执行真实翻译。
- 不修改 `output_cn/translated/` 内容。

---

## Round T3：润色脚本骨架轮
**目标**
- 新增润色流程骨架。
**前置条件**
- 完成 T2，已有初译脚本。
**输入文件**
- 原文 (`input_jp/`)、初译草稿 (`output_cn/experiments/draft_*.md`)、术语库、人物表、风格指南。
**输出文件**
- `scripts/polish_translation.py`（脚本骨架），`output_cn/experiments/polished_*.md`。
**阶段任务**
1. 创建 `scripts/polish_translation.py`。
2. 输入：原文 + 初译 + glossary + character_names + style_guide。
3. 输出：润色版本。
4. 输出路径限定到 experiments。
5. 生成 polish report。
6. 支持 dry‑run。
**验收标准**
- 能生成润色 Prompt。
- 能说明使用了哪些参考文件。
- 不覆盖正式译文。
**风险点**
- 脚本误写导致覆盖正式译文。
- 未正确加载术语库导致不一致。
**不做什么**
- 不自动写入 `output_cn/translated/`。

---

## Round T4：术语一致性检查轮
**目标**
- 创建术语检查脚本。
**前置条件**
- 完成 T3，已有润色脚本。
**输入文件**
- `notes/glossary.md`、`output_cn/translated/`（或 `output_cn/experiments/polished_*.md`）。
**输出文件**
- `scripts/check_terms.py`，`output_cn/experiments/term_consistency_report.md`。
**阶段任务**
1. 创建 `scripts/check_terms.py`。
2. 读取 glossary 和译文。
3. 检查术语是否统一。
4. 检查人物名是否统一。
5. 检查未确认术语是否出现。
6. 输出 consistency report。
**验收标准**
- 可检查指定章节。
- 可输出发现的问题。
- 不自动修改译文。
**风险点**
- 错误报告导致误判。
**不做什么**
- 不自动改译文。

---

## Round T5：Embedding 记忆系统设计实现轮
**目标**
- 设计并实现小样本 embedding 索引。
**前置条件**
- 完成 T4，已有一致性检查报告。
**输入文件**
- `docs/embedding_memory_design.md`、`notes/*`、已审核译文块。
**输出文件**
- `scripts/build_translation_memory.py`（构建索引），`scripts/search_translation_memory.py`（检索 CLI），`output_cn/experiments/embedding_index_demo/`（示例向量文件）。
**阶段任务**
1. 创建 `scripts/build_translation_memory.py`。
2. 创建 `scripts/search_translation_memory.py`。
3. 更新 `docs/embedding_memory_design.md` 的实现说明。
4. 索引小样本（如前 5 章节）。
5. 支持 dry‑run。
6. 不读取 `.env`。
**验收标准**
- 能构建小样本索引。
- 能检索术语或片段。
- 能输出召回结果。
- 不进入全量生产状态。
**风险点**
- 大规模向量导致磁盘占用。
- 检索误召回影响后续润色。
**不做什么**
- 不索引全卷。

---

## Round T6：检索辅助润色轮
**目标**
- 让润色 Prompt 可以引用检索结果。
**前置条件**
- 完成 T5，已有 Embedding 检索能力。
**输入文件**
- 待润色段落、检索返回的上下文块。
**输出文件**
- `scripts/polish_with_retrieval.py`（示例脚本），`output_cn/experiments/polished_with_context_*.md`。
**阶段任务**
1. 输入待润色段落。
2. 检索相关术语、人物、前文译法。
3. 生成 context pack。
4. 把 context pack 加入润色 Prompt。
5. 输出润色结果和引用依据。
**验收标准**
- 润色结果可追溯参考片段。
- 能显示引用了哪些术语和章节。
- 不把检索结果当绝对真理。
**风险点**
- 检索噪声导致润色偏差。
**不做什么**
- 不自动接受检索结果。

---

## Round T7：审核报告与人工反馈轮
**目标**
- 设计人工审核机制。
**前置条件**
- 完成 T6，已有检索增强润色示例。
**输入文件**
- 润色稿、检索上下文、`notes/uncertain_terms.md`。
**输出文件**
- `output_cn/review/review_template.md`（审核模板），`output_cn/experiments/review_feedback_*.md`。
**阶段任务**
1. 生成 review template。
2. 允许人工标记：术语错误、人物错误、语气错误、风格不自然、忠实度问题、润色过度。
3. 将反馈回流到 `notes/` 或 `review/` 层。
4. 更新 `uncertain_terms.md`。
**验收标准**
- 有审核模板。
- 有反馈类型。
- 有回流机制。
- 不自动改正式译文。
**风险点**
- 人工遗漏导致不一致。
**不做什么**
- 不自动修改 `output_cn/translated/`。

---

## Round T8：中译日流程扩展轮
**目标**
- 在现有日译中结构上，规划中译日。
**前置条件**
- 完成 T7，已有双向术语机制。
**输入文件**
- 中文原文输入目录 `input_cn/`（待创建），`notes/glossary.md`（双向字段）。
**输出文件**
- 日文输出目录 `output_jp/`（待创建），对应的术语映射文件。
**阶段任务**
1. 设计中文原文输入目录。
2. 设计日文输出目录。
3. 设计中译日术语字段。
4. 设计日语自然度润色规则。
5. 设计敬体/常体/角色语气规则。
6. 设计中译日审核标准。
**验收标准**
- 日译中和中译日流程分离但可复用。
- 不混用输出目录。
- 术语库支持双向字段。
**风险点**
- 双向映射错误导致不自然日文。
**不做什么**
- 不直接生成日文译文。

---

## Round T9：OpenClaw / Cursor / Codex 协作轮
**目标**
- 明确三种 Agent 的分工。
**前置条件**
- 完成 T8，已有完整路线图。
**输入文件**
- `prompts/` 中的模板文件。
**输出文件**
- `prompts/openclaw_translation_governance.md`
- `prompts/cursor_translation_pipeline_round.md`
- `prompts/codex_translation_pipeline_round.md`
- 相关 Agent Prompt 配置（可选）。
**阶段任务**
1. OpenClaw 负责只读审计、生成计划、运行小脚本测试。
2. Cursor 负责本地开发、调试、UI/脚本修改。
3. Codex 负责自动推进、批量修改、提交 PR。
4. 设计 `prompts/openclaw_translation_governance.md`。
5. 设计 `prompts/cursor_translation_pipeline_round.md`。
6. 设计 `prompts/codex_translation_pipeline_round.md`。
**验收标准**
- 三者分工清楚。
- OpenClaw 不承担高风险全自动修改。
- Cursor/Codex 可根据 Prompt 接续执行。
**风险点**
- 权限误授导致误删或泄露密钥。
- 自动化修改冲突。
**不做什么**
- 不让 OpenClaw 执行批量改译文。
- 不让 Codex 在未审查的情况下提交 PR。

---

# 路线图使用说明

- 每个 Round 均可单独执行，也可在持续集成中按阶段触发。
- `round_state/` 将记录每轮的状态、已完成任务以及待办事项。
- 未来可依据实际进度在 `CHANGELOG.md` 中记录完成的里程碑。
