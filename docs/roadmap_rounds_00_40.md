# 40 轮长期推进路线图

本路线图用于约束后续 Agent 连续推进。每一轮都必须先读取 README、项目愿景、架构总览、治理规则和本路线图，不得越级执行，不得重复造轮子，不得在未授权时处理真实小说正文或调用真实 API。

## Round 00：当前治理轮，项目定位升级

### 轮次类型

governance

### 背景

仓库原本偏向单本日文轻小说到中文翻译，已有 `input_jp/`、`output_cn/`、`notes/`、`docs/` 和 `prompts/`，但缺少双向流水线治理基础。

### 目标

将项目从单本日译中任务仓库升级为中日文小说互译生产流水线规划。

### 具体任务

1. 审计当前仓库结构和已有文档。
2. 更新 README，声明新定位和安全边界。
3. 创建项目愿景文档。
4. 创建总体架构文档。
5. 创建共享核心与方向专属模块设计。
6. 创建 40 轮路线图。
7. 创建治理规则、迁移说明和后续 Prompt 模板。

### 产出文件

`README.md`、`docs/current_repository_audit.md`、`docs/project_vision.md`、`docs/architecture_overview.md`、`docs/shared_core_design.md`、`docs/roadmap_rounds_00_40.md`、`docs/governance_rules.md`、`docs/migration_notes.md`。

### 验收标准

1. `docs/current_repository_audit.md` 存在。
2. `docs/project_vision.md` 存在。
3. `docs/architecture_overview.md` 存在。
4. `docs/roadmap_rounds_00_40.md` 存在。
5. README 已体现新定位。
6. 没有翻译真实小说。
7. 没有调用真实 API。

### 不做事项

不读取正文、不翻译、不调用 API、不生成 embedding、不实现前端、不删除旧结构。

### 下一轮衔接

进入 Round 01，补齐轻量目录并标准化仓库结构。

## Round 01：仓库结构标准化

### 轮次类型

governance / light implementation

### 背景

双向流水线需要 `input_cn/`、`output_jp/`、`shared/`、`directions/`、`workspace/`、`data/`、`src/`、`frontend/` 和 `tests/`。

### 目标

整理目录结构，补齐未来需要但不填充重代码的目录。

### 具体任务

1. 创建 `input_cn/`。
2. 创建 `output_jp/translated/`、`output_jp/bilingual/`、`output_jp/review/`。
3. 创建 `shared/` 与 `directions/jp_to_cn/`、`directions/cn_to_jp/`。
4. 创建 `workspace/` 子目录。
5. 创建 `data/projects/`、`data/schemas/`、`data/examples/`。
6. 创建 `src/`、`frontend/`、`tests/`。
7. 每个目录添加 README 或 `.gitkeep`。
8. 更新 `.gitignore`。
9. 检查不提交真实原文和真实译文。
10. 记录目录变化。

### 产出文件

新增目录 README、`.gitkeep`、更新后的 `.gitignore`、可选目录审计报告。

### 验收标准

1. 新目录存在。
2. README 说明清楚。
3. 不提交真实原文。
4. 不提交真实译文。
5. Git 状态可说明。
6. `.gitignore` 覆盖新输入、输出和 workspace 大文件。
7. 旧 `input_jp/` 和 `output_cn/` 未被破坏。

### 不做事项

不写复杂代码，不迁移真实正文，不改已有译文，不调用 API，不生成向量。

### 下一轮衔接

进入 Round 02，细化 shared core 模块边界。

## Round 02：共享核心模块文档落地

### 轮次类型

governance

### 背景

双向翻译会共享大量基础能力，如果边界不清，后续容易复制两套扫描、解析、术语和向量库实现。

### 目标

细化 shared core 模块边界。

### 具体任务

1. 扩写 shared file scanner。
2. 扩写 chapter parser。
3. 扩写 segmenter。
4. 扩写 glossary manager。
5. 扩写 character manager。
6. 扩写 world bible manager。
7. 扩写 embedding adapter。
8. 扩写 vector store adapter。
9. 扩写 model provider adapter。
10. 扩写 exporter。

### 产出文件

`docs/shared_core_design.md`、`shared/README.md`、可选 shared module index。

### 验收标准

1. `docs/shared_core_design.md` 可指导后续实现。
2. 明确哪些模块共享。
3. 明确哪些模块方向专属。
4. 没有重复实现建议。
5. 后续 Round 03/04 可直接引用。
6. shared core 不包含方向 Prompt。
7. direction 模块不重复实现 shared core。

### 不做事项

不实现代码，不接模型，不创建空包式复杂结构，不移动旧资料。

### 下一轮衔接

进入 Round 03，设计 `JP_TO_CN` 方向规则。

## Round 03：JP_TO_CN 方向规则设计

### 轮次类型

governance

### 背景

日译中需要处理敬称、省略主语、假名、汉字名、片假名专名、日式表达和中文自然化。

### 目标

设计日文到中文的专属翻译规则。

### 具体任务

1. 创建或扩写 `directions/jp_to_cn/README.md`。
2. 创建日文敬称处理规则。
3. 创建日文姓名处理规则。
4. 创建片假名术语处理规则。
5. 创建轻小说中文风格规则。
6. 创建日文省略主语处理规则。
7. 创建日文拟声词处理规则。
8. 创建 `JP_TO_CN` 初翻 Prompt 草案。
9. 创建 `JP_TO_CN` 润色 Prompt 草案。
10. 创建 `JP_TO_CN` 审核 Prompt 草案。

### 产出文件

`directions/jp_to_cn/README.md`、方向规则文档、方向 Prompt 草案。

### 验收标准

1. `JP_TO_CN` 规则与 `CN_TO_JP` 分离。
2. Prompt 不写死模型。
3. 人名规则清晰。
4. 敬称规则清晰。
5. 输出中文风格目标清晰。
6. 规则能进入 context pack。
7. 不污染 shared core。

### 不做事项

不翻译真实章节，不批量替换译文，不调用 API。

### 下一轮衔接

进入 Round 04，设计 `CN_TO_JP` 方向规则。

## Round 04：CN_TO_JP 方向规则设计

### 轮次类型

governance

### 背景

中译日需要重建日文敬语、第一人称、称呼、小说文体、标点和自然表达。

### 目标

设计中文到日文的专属翻译规则。

### 具体任务

1. 创建或扩写 `directions/cn_to_jp/README.md`。
2. 创建中文姓名日文化规则。
3. 创建中文称呼转日文敬称规则。
4. 创建日文第一人称策略。
5. 创建日文文体规则。
6. 创建中文网络语日文化规则。
7. 创建 `CN_TO_JP` 初翻 Prompt 草案。
8. 创建 `CN_TO_JP` 润色 Prompt 草案。
9. 创建 `CN_TO_JP` 审核 Prompt 草案。
10. 说明中译日与日译中的共享与差异。

### 产出文件

`directions/cn_to_jp/README.md`、方向规则文档、方向 Prompt 草案。

### 验收标准

1. `CN_TO_JP` 规则独立。
2. 不污染 `JP_TO_CN`。
3. 日文自然度目标明确。
4. 敬语重建策略明确。
5. Prompt 可后续实现。
6. 第一人称和称呼规则可配置。
7. 不调用真实 API。

### 不做事项

不翻译真实中文小说，不生成日文译文，不实现 tokenizer。

### 下一轮衔接

进入 Round 05，设计项目配置与数据 schema。

## Round 05：项目配置与 Project Schema

### 轮次类型

implementation design

### 背景

双向流水线需要项目级配置来描述方向、输入输出、provider、预算和状态。

### 目标

设计项目级配置和数据 Schema。

### 具体任务

1. 设计 `project.yaml`。
2. 设计 `direction_config.yaml`。
3. 设计 Project schema。
4. 设计 SourceFile schema。
5. 设计 Chapter schema。
6. 设计 Segment schema。
7. 设计 ProjectState schema。
8. 增加 example config。
9. 更新数据 Schema 文档。
10. 不接 API。

### 产出文件

`docs/data_schema_plan.md` 更新、`data/schemas/` schema 草案、`data/examples/` 脱敏样例配置。

### 验收标准

1. schema 可描述单本小说项目。
2. schema 支持 `JP_TO_CN`。
3. schema 支持 `CN_TO_JP`。
4. schema 支持未来多项目。
5. 示例配置无敏感信息。
6. schema 不绑定具体数据库。
7. 配置不包含 API Key。

### 不做事项

不实现数据库，不迁移旧 notes，不调用 provider，不读取真实正文。

### 下一轮衔接

进入 Round 06，做原文导入与文件扫描最小实现。

## Round 06：原文导入与文件扫描最小实现

### 轮次类型

implementation

### 背景

后续 pipeline 需要可靠 manifest，但扫描器不应修改原文或读取不必要内容。

### 目标

实现最小文件扫描，不翻译。

### 具体任务

1. 创建最小 `src` 结构。
2. 实现文件扫描器。
3. 支持 `input_jp/` 和 `input_cn/`。
4. 支持 `.txt` 和 `.md`。
5. 生成 manifest。
6. 不读取大模型。
7. 不调用 API。
8. 增加测试样例。
9. 更新 README。
10. 增加命令行入口草案。

### 产出文件

扫描器代码、测试、manifest 样例、README 更新。

### 验收标准

1. 能扫描输入文件。
2. 能生成 manifest。
3. 不修改原文。
4. 不提交真实原文。
5. 测试通过。
6. 支持两个输入目录。
7. 扫描结果可复现。

### 不做事项

不解析章节正文，不翻译，不上传文件，不调用 API。

### 下一轮衔接

进入 Round 07，做章节解析与排序。

## Round 07：章节解析与排序

### 轮次类型

implementation

### 背景

文件名和正文标题可能不一致，章节顺序需要稳定可复查。

### 目标

识别章节标题、顺序和特殊章节。

### 具体任务

1. 识别序章。
2. 识别第 X 章。
3. 识别番外。
4. 识别后记。
5. 识别卷标题。
6. 支持文件名排序。
7. 支持标题排序。
8. 生成 chapters metadata。
9. 增加异常报告。
10. 增加测试。

### 产出文件

章节解析器、chapters metadata、异常报告、测试。

### 验收标准

1. 章节顺序稳定。
2. 缺失章节可报告。
3. 重复章节可报告。
4. 特殊章节可标记。
5. 不启动翻译。
6. 不修改原文。
7. 支持两个方向。

### 不做事项

不进行段落切分，不做术语抽取，不调用 API。

### 下一轮衔接

进入 Round 08，做文本清洗与段落切分。

## Round 08：文本清洗与段落切分

### 轮次类型

implementation

### 背景

初翻、embedding 和审核都依赖稳定 segment id 和原始偏移。

### 目标

清洗文本并切分成段落/segment。

### 具体任务

1. 去除多余空行。
2. 保留对话结构。
3. 保留标题结构。
4. 提取 URL。
5. 提取注释。
6. 生成 segment id。
7. 保留原始偏移。
8. 支持段落对齐准备。
9. 生成清洗报告。
10. 增加测试。

### 产出文件

segmenter、cleaning report、segments metadata、测试。

### 验收标准

1. 不破坏正文。
2. 段落可追溯到原文。
3. URL 不丢失。
4. 对话不被错误合并。
5. 可供后续 embedding 使用。
6. segment id 稳定。
7. 支持 `JP_TO_CN` 和 `CN_TO_JP`。

### 不做事项

不翻译，不调用模型，不写入正式输出。

### 下一轮衔接

进入 Round 09，做术语候选抽取设计与离线规则。

## Round 09：术语候选抽取设计与离线规则

### 轮次类型

implementation design

### 背景

术语抽取先从规则和频率做起，避免过早依赖 LLM。

### 目标

先用规则和轻量逻辑抽取术语候选，为后续 LLM 抽取打基础。

### 具体任务

1. 设计术语候选 schema。
2. 实现基础频率统计。
3. 实现日文片假名候选抽取。
4. 实现中文专名候选抽取。
5. 实现标题/括号词抽取。
6. 实现重复出现词抽取。
7. 输出 candidates。
8. 不调用 LLM。
9. 更新术语文档。
10. 增加测试。

### 产出文件

术语候选 schema、候选抽取器、candidate 输出、测试。

### 验收标准

1. 候选词可导出。
2. 支持 `JP_TO_CN`。
3. 支持 `CN_TO_JP`。
4. 不误写 approved。
5. 可供后续 LLM 审核。
6. 候选有章节和 segment 来源。
7. locked 术语不被覆盖。

### 不做事项

不自动确认术语，不调用真实模型，不替换译文。

### 下一轮衔接

进入 Round 10，做角色候选抽取设计。

## Round 10：角色候选抽取设计

### 轮次类型

implementation design

### 背景

角色姓名、别名、称呼和台词关系影响长篇翻译一致性。

### 目标

建立角色候选抽取基础。

### 具体任务

1. 设计 CharacterCandidate schema。
2. 从对话和称呼中抽取候选。
3. 从人物名模式抽取候选。
4. 从敬称中推断候选。
5. 从章节首次出现记录候选。
6. 建立角色别名字段。
7. 输出 candidates。
8. 更新角色系统文档。
9. 增加样例。
10. 不调用 API。

### 产出文件

角色候选 schema、抽取规则、candidate 输出、样例、测试。

### 验收标准

1. 能生成角色候选。
2. 能记录首次出现。
3. 能记录别名。
4. 不强行确定角色设定。
5. 后续可交给 LLM 审核。
6. 支持日文敬称线索。
7. 支持中文称呼线索。

### 不做事项

不自动生成百科，不决定最终译名，不调用 API。

### 下一轮衔接

进入 Round 11，做世界观候选抽取设计。

## Round 11：世界观候选抽取设计

### 轮次类型

implementation design

### 背景

地点、组织、制度、技能、魔法、种族等设定需要可追踪证据。

### 目标

建立地点、组织、制度、技能等设定候选。

### 具体任务

1. 设计 WorldBibleCandidate schema。
2. 抽取地名候选。
3. 抽取组织候选。
4. 抽取技能/魔法候选。
5. 抽取制度和头衔候选。
6. 记录证据句。
7. 记录章节位置。
8. 输出 candidates。
9. 更新 world bible 文档。
10. 增加测试。

### 产出文件

世界观候选 schema、抽取规则、candidate 输出、测试。

### 验收标准

1. 候选有原文证据。
2. 不把推测写成事实。
3. 能标记不确定。
4. 支持两个方向。
5. 可供 LLM 审核。
6. 伏笔候选可标记。
7. 候选可关联术语和角色。

### 不做事项

不自动补全设定，不提前解释伏笔，不调用 API。

### 下一轮衔接

进入 Round 12，设计 LLM Provider Adapter。

## Round 12：LLM Provider Adapter 设计

### 轮次类型

implementation design

### 背景

未来会接入多个模型供应商，必须通过统一 adapter 隔离差异和安全风险。

### 目标

设计但不真实调用 provider adapter。

### 具体任务

1. 设计 provider interface。
2. 设计 request schema。
3. 设计 response schema。
4. 设计 error schema。
5. 设计 model run metadata。
6. 设计 `.env.example`。
7. 设计 provider config。
8. 加入 fake provider 测试。
9. 不调用真实 API。
10. 更新 API 文档。

### 产出文件

provider adapter 设计、fake provider、配置样例、测试、文档更新。

### 验收标准

1. 不写死供应商。
2. 不泄露 Key。
3. fake provider 可测试流程。
4. metadata 结构清晰。
5. 后续可接 DeepSeek/Grok/OpenAI/OpenRouter。
6. 错误结构可审计。
7. 支持 dry-run。

### 不做事项

不真实调用 API，不读 `.env` 真值，不发送正文。

### 下一轮衔接

进入 Round 13，设计 Embedding Adapter。

## Round 13：Embedding Adapter 设计

### 轮次类型

implementation design

### 背景

Embedding 需要支持本地和云端模型，并和 provider、vector store 解耦。

### 目标

设计 embedding adapter 和 embedding record。

### 具体任务

1. 设计 embedding interface。
2. 设计 embedding input。
3. 设计 embedding output。
4. 设计 metadata。
5. 设计批量 embedding 入口。
6. 设计失败重试。
7. 设计缓存策略。
8. 加 fake embedding。
9. 不调用真实模型。
10. 更新文档。

### 产出文件

embedding adapter 设计、fake embedding、metadata schema、测试。

### 验收标准

1. embedding 与 provider 解耦。
2. 支持本地和云端模型。
3. 支持 `project_id` 过滤。
4. 支持 direction 过滤。
5. 可供向量库使用。
6. fake embedding 不接真实模型。
7. metadata 不含敏感内容。

### 不做事项

不生成真实 embedding，不索引真实正文，不接远程向量库。

### 下一轮衔接

进入 Round 14，设计 Vector Store Adapter。

## Round 14：Vector Store Adapter 设计

### 轮次类型

implementation design

### 背景

向量库可能在 Chroma、FAISS、SQLite vector、LanceDB 或远程服务之间切换。

### 目标

设计向量库可替换接口。

### 具体任务

1. 设计 vector store interface。
2. 设计 add/search/delete/update。
3. 设计 metadata filter。
4. 设计 Chroma 方案。
5. 设计 FAISS 方案。
6. 设计 SQLite vector 方案。
7. 设计本地存储路径。
8. 加 fake vector store。
9. 不存真实 embedding。
10. 更新文档。

### 产出文件

vector store adapter 设计、fake store、metadata filter 文档、测试。

### 验收标准

1. 检索接口稳定。
2. 支持 project filter。
3. 支持 direction filter。
4. 支持 chapter filter。
5. 不绑定唯一向量库。
6. fake store 可用于测试。
7. 不写入真实向量索引。

### 不做事项

不部署数据库，不索引真实文本，不引入复杂服务端。

### 下一轮衔接

进入 Round 15，构建 Context Pack。

## Round 15：Context Pack 构建器设计

### 轮次类型

implementation

### 背景

初翻和润色需要可复现、可审计、不过载的上下文包。

### 目标

为翻译和润色构建上下文包。

### 具体任务

1. 设计 context pack schema。
2. 读取术语库。
3. 读取角色表。
4. 读取世界观设定。
5. 读取章节摘要。
6. 读取相似段落结果。
7. 读取翻译记忆。
8. 组合成上下文包。
9. 输出 JSON/Markdown。
10. 增加测试。

### 产出文件

context pack builder、JSON/Markdown 输出、测试。

### 验收标准

1. context pack 可复现。
2. 不包含无关大段信息。
3. 按章节生成。
4. 支持两个方向。
5. 可供 Prompt 使用。
6. 包含已批准术语。
7. 记录 known risks。

### 不做事项

不调用真实模型，不塞入整本小说，不绕过预算限制。

### 下一轮衔接

进入 Round 16，做术语库管理 MVP。

## Round 16：术语库管理 MVP

### 轮次类型

implementation

### 背景

术语状态、冲突和锁定必须可机读、可人工审核。

### 目标

实现术语库的读取、写入、状态更新。

### 具体任务

1. 读取 glossary 文件。
2. 写入 glossary JSON/YAML。
3. 支持 `candidate`。
4. 支持 `approved`。
5. 支持 `conflict`。
6. 支持 `locked`。
7. 支持译名变更记录。
8. 支持导出 Markdown。
9. 增加测试。
10. 不接前端。

### 产出文件

glossary manager、JSON/YAML 存储、Markdown 导出、测试。

### 验收标准

1. 术语状态可更新。
2. locked 不被覆盖。
3. 冲突可记录。
4. Markdown 可读。
5. JSON/YAML 可机读。
6. 更新有版本记录。
7. 支持两个方向。

### 不做事项

不自动替换译文，不确认真实术语，不调用 LLM。

### 下一轮衔接

进入 Round 17，做角色设定管理 MVP。

## Round 17：角色设定管理 MVP

### 轮次类型

implementation

### 背景

角色姓名、称呼、关系和语气需要结构化维护。

### 目标

实现角色表基础管理。

### 具体任务

1. 读取角色表。
2. 写入角色表。
3. 支持别名。
4. 支持称呼关系。
5. 支持说话风格字段。
6. 支持发言样例。
7. 支持版本记录。
8. 导出 Markdown。
9. 增加测试。
10. 不做复杂 UI。

### 产出文件

character manager、relation manager、Markdown 导出、测试。

### 验收标准

1. 角色信息可持久化。
2. 称呼关系可记录。
3. 角色语气字段存在。
4. 支持两个语言方向。
5. 可被 context pack 读取。
6. 版本更新可追踪。
7. locked 字段不被覆盖。

### 不做事项

不生成角色百科，不自动决定真实姓名译法，不接前端。

### 下一轮衔接

进入 Round 18，做世界观设定管理 MVP。

## Round 18：世界观设定管理 MVP

### 轮次类型

implementation

### 背景

世界观设定需要原文证据、推测标记和剧透控制。

### 目标

实现世界观设定基础管理。

### 具体任务

1. 读取 world bible。
2. 写入 world bible。
3. 支持设定类型。
4. 支持原文证据。
5. 支持 inferred。
6. 支持 spoiler sensitive。
7. 支持关联术语和角色。
8. 导出 Markdown。
9. 增加测试。
10. 不做自动脑补。

### 产出文件

world bible manager、Markdown 导出、测试。

### 验收标准

1. 设定可追溯到原文。
2. 推测被标记。
3. 不确定项可审核。
4. 可被 context pack 使用。
5. 可供润色参考。
6. 剧透标记生效。
7. 支持关联术语和角色。

### 不做事项

不自动补全设定，不提前解释伏笔，不写真实正文摘要。

### 下一轮衔接

进入 Round 19，设计初翻 Prompt 体系。

## Round 19：初翻 Prompt 体系

### 轮次类型

governance / prompt design

### 背景

初翻 Prompt 必须同时支持双方向、context pack、术语强制使用和输出格式。

### 目标

设计双方向初翻 Prompt。

### 具体任务

1. 创建 `JP_TO_CN` 初翻 Prompt。
2. 创建 `CN_TO_JP` 初翻 Prompt。
3. 引入 context pack。
4. 引入术语库。
5. 引入角色表。
6. 引入世界观设定。
7. 引入输出格式。
8. 引入禁止事项。
9. 引入 JSON/Markdown 输出规范。
10. 增加 Prompt 测试样例。

### 产出文件

方向初翻 Prompt、Prompt 测试样例、文档更新。

### 验收标准

1. Prompt 不写死模型。
2. Prompt 明确初翻目标。
3. Prompt 支持术语强制使用。
4. Prompt 支持角色语气。
5. Prompt 支持两个方向。
6. 输出格式可被 pipeline 解析。
7. 禁止过度润色。

### 不做事项

不调用 API，不翻译真实章节，不把 Prompt 当最终系统提示固化。

### 下一轮衔接

进入 Round 20，用 Fake Provider 跑通初翻 pipeline。

## Round 20：初翻 Pipeline MVP，Fake Provider

### 轮次类型

implementation

### 背景

真实 API 前必须用 fake provider 跑通数据流、输出结构和状态更新。

### 目标

用 fake provider 跑通初翻 pipeline，不调用真实 API。

### 具体任务

1. 读取章节。
2. 构建 context pack。
3. 调用 fake provider。
4. 生成译文占位。
5. 生成双语对照结构。
6. 更新 progress。
7. 记录 model run。
8. 支持失败状态。
9. 增加测试。
10. 更新 README。

### 产出文件

initial translation pipeline、fake provider 输出、progress、model run、测试。

### 验收标准

1. pipeline 可跑通。
2. 不调用真实 API。
3. 输出结构正确。
4. progress 更新。
5. 后续可替换真实 provider。
6. 不覆盖正式译文。
7. 失败状态可记录。

### 不做事项

不生成真实译文，不处理整本真实小说，不消耗 token。

### 下一轮衔接

进入 Round 21，准备真实 API 小规模接入。

## Round 21：真实 API 小规模接入准备

### 轮次类型

api integration preparation

### 背景

真实 API 接入必须先具备 dry-run、预算、范围限制和安全日志。

### 目标

准备真实 API 接入，但不默认大规模调用。

### 具体任务

1. 完善 `.env.example`。
2. 完善 provider config。
3. 增加 dry-run。
4. 增加 cost guard。
5. 增加 max chapters 限制。
6. 增加 max tokens 估算。
7. 增加 metadata。
8. 增加错误处理。
9. 增加安全检查。
10. 不自动跑整本小说。

### 产出文件

provider config、budget guard、dry-run、错误处理、文档。

### 验收标准

1. Key 不泄露。
2. 有 dry-run。
3. 有预算限制。
4. 有调用记录。
5. 有失败恢复。
6. 默认不真实调用。
7. 默认不跑整本。

### 不做事项

不默认启用真实 provider，不处理真实长篇，不提交 `.env`。

### 下一轮衔接

进入 Round 22，用样例文本做真实 API 小规模测试。

## Round 22：DeepSeek 类模型初翻试跑

### 轮次类型

translation_execution / controlled api

### 背景

需要验证真实 provider adapter、metadata 和输出格式，但必须限制范围和成本。

### 目标

用真实 API 小规模测试初翻能力。

### 具体任务

1. 只用样例文本。
2. 读取 provider config。
3. 调真实 API。
4. 记录 model run。
5. 输出初翻样例。
6. 检查术语使用。
7. 检查格式。
8. 检查成本。
9. 写测试报告。
10. 不处理真实整本书。

### 产出文件

小样本输出、model run、成本记录、测试报告。

### 验收标准

1. 真实 API 调用成功。
2. 没有泄露 Key。
3. 输出可复查。
4. metadata 完整。
5. 成本可控。
6. 样例范围明确。
7. 失败时可解释。

### 不做事项

不跑真实长篇，不提交 API Key，不覆盖正式译文。

### 下一轮衔接

进入 Round 23，受控执行单章初翻。

## Round 23：整章初翻执行

### 轮次类型

translation_execution

### 背景

小样本成功后，可以在用户授权范围内验证单章完整流程。

### 目标

对单章进行真实初翻。

### 具体任务

1. 读取一个测试章节。
2. 构建 context pack。
3. 调初翻模型。
4. 输出译文。
5. 输出双语对照。
6. 更新术语库。
7. 更新角色表。
8. 记录问题。
9. 记录成本。
10. 生成报告。

### 产出文件

单章初翻、双语对照、知识资产更新、成本报告。

### 验收标准

1. 单章完整翻译。
2. 术语一致。
3. 输出格式正确。
4. 成本记录。
5. 可回滚。
6. 不覆盖旧正式译文。
7. 只处理授权章节。

### 不做事项

不批量执行，不越权读取章节，不公开发布译文。

### 下一轮衔接

进入 Round 24，支持批量初翻。

## Round 24：批量初翻执行

### 轮次类型

translation_execution

### 背景

单章流程稳定后，需要按状态筛选、断点续跑和失败重试。

### 目标

支持多章批量初翻。

### 具体任务

1. 按章节状态筛选。
2. 批量构建 context pack。
3. 批量调用 provider。
4. 支持断点续跑。
5. 支持失败重试。
6. 更新 progress。
7. 更新 translation memory。
8. 生成批次报告。
9. 成本汇总。
10. 不覆盖已完成译文。

### 产出文件

批量初翻输出、progress、translation memory、批次报告、成本汇总。

### 验收标准

1. 可批量翻译。
2. 可断点续跑。
3. 失败可恢复。
4. 成本可控。
5. 不重复消耗。
6. 不覆盖完成项。
7. 范围由用户授权。

### 不做事项

不无上限调用 API，不忽略预算，不覆盖 locked 资产。

### 下一轮衔接

进入 Round 25，完善双语对照和段落对齐。

## Round 25：双语对照与段落对齐

### 轮次类型

implementation

### 背景

审核、润色和导出都需要稳定的原文译文对照结构。

### 目标

完善原文译文对照结构。

### 具体任务

1. 实现 paragraph alignment。
2. 输出 bilingual Markdown。
3. 支持 segment id。
4. 支持跳转引用。
5. 支持 review issue 绑定段落。
6. 支持 diff 准备。
7. 检查段落数量。
8. 标记错位风险。
9. 增加测试。
10. 更新文档。

### 产出文件

alignment 工具、bilingual Markdown、alignment JSON、测试。

### 验收标准

1. 双语对照清晰。
2. 段落可追踪。
3. 问题可定位。
4. 支持审核。
5. 支持润色对比。
6. 错位风险可报告。
7. 不修改原文。

### 不做事项

不重翻译，不自动修正全部错位，不覆盖人工结果。

### 下一轮衔接

进入 Round 26，做术语一致性检查。

## Round 26：术语一致性检查

### 轮次类型

review implementation

### 背景

同一术语多译、漏用 approved 译名和 locked 术语被改动会破坏整本一致性。

### 目标

检查同一术语多译和错译。

### 具体任务

1. 读取 approved glossary。
2. 扫描译文。
3. 找出未使用指定译名。
4. 找出多个译名。
5. 生成 review issues。
6. 生成修正建议。
7. 支持 locked term。
8. 支持 false positive 标记。
9. 增加测试。
10. 更新报告模板。

### 产出文件

术语检查器、review issue、报告模板、测试。

### 验收标准

1. 能发现术语冲突。
2. 能定位章节段落。
3. 不误改 locked 术语。
4. 有修正建议。
5. 可供前端展示。
6. 支持 false positive。
7. 不自动覆盖译文。

### 不做事项

不自动改译文，不忽略 locked，不调用润色模型。

### 下一轮衔接

进入 Round 27，做角色语气一致性检查。

## Round 27：角色语气一致性检查

### 轮次类型

review implementation

### 背景

角色口吻、称呼、敬语和口癖漂移会明显降低小说译文质量。

### 目标

检查角色台词是否语气漂移。

### 具体任务

1. 读取角色表。
2. 读取角色台词样例。
3. 检索同角色发言。
4. 检查称呼一致性。
5. 检查敬语等级。
6. 检查口癖。
7. 生成 voice conflict issue。
8. 支持人工标记。
9. 增加测试样例。
10. 更新文档。

### 产出文件

角色语气检查器、voice conflict issue、测试样例、文档。

### 验收标准

1. 能发现称呼冲突。
2. 能发现语气漂移。
3. 能定位段落。
4. 不强行修改。
5. 输出可审核。
6. 支持人工豁免。
7. 支持两个方向。

### 不做事项

不自动重写台词，不将所有角色统一文风，不忽略角色 locked 规则。

### 下一轮衔接

进入 Round 28，做世界观冲突检查。

## Round 28：世界观冲突检查

### 轮次类型

review implementation

### 背景

地点、组织、制度、技能、称号和设定译法冲突会影响全书可读性。

### 目标

检查设定翻译是否冲突。

### 具体任务

1. 读取 world bible。
2. 扫描译文设定词。
3. 检查地点/组织/制度译名。
4. 检查技能体系译名。
5. 检查称号等级。
6. 生成 conflict issue。
7. 标记推测设定。
8. 支持人工确认。
9. 增加测试。
10. 更新文档。

### 产出文件

世界观冲突检查器、conflict issue、报告、测试。

### 验收标准

1. 设定冲突可发现。
2. 可定位原文证据。
3. 不把推测当事实。
4. 可输出报告。
5. 可进入润色 context。
6. 剧透标记不被忽略。
7. 支持人工确认。

### 不做事项

不自动改设定，不提前解释伏笔，不用模型脑补事实。

### 下一轮衔接

进入 Round 29，设计润色 Prompt 体系。

## Round 29：润色 Prompt 体系

### 轮次类型

prompt design

### 背景

润色必须对照原文和初翻，不能变成重翻或自由改写。

### 目标

设计二次润色 Prompt。

### 具体任务

1. 创建 `JP_TO_CN` 润色 Prompt。
2. 创建 `CN_TO_JP` 润色 Prompt。
3. 要求对照原文。
4. 要求保留术语。
5. 要求保留角色语气。
6. 要求输出 change log。
7. 要求标记风险。
8. 防止过度润色。
9. 增加样例。
10. 更新文档。

### 产出文件

双方向润色 Prompt、样例、文档更新。

### 验收标准

1. 润色不是重翻。
2. 有 change log。
3. 有风险标记。
4. 支持两个方向。
5. 可接强模型。
6. 明确禁止删改剧情。
7. 明确保留术语和角色语气。

### 不做事项

不调用强模型，不润色真实章节，不覆盖初翻。

### 下一轮衔接

进入 Round 30，做强模型润色小规模试跑。

## Round 30：强模型润色小规模试跑

### 轮次类型

translation_execution / controlled api

### 背景

润色 Prompt 需要在小样例上验证强模型是否保留术语、角色语气和原文信息。

### 目标

用强模型对一小段初翻进行润色测试。

### 具体任务

1. 选择样例段落。
2. 构建润色 context。
3. 调用强模型 provider。
4. 输出 refined translation。
5. 输出 change log。
6. 检查术语是否保持。
7. 检查角色语气。
8. 记录成本。
9. 写报告。
10. 不跑整本。

### 产出文件

小样例润色输出、change log、成本报告、质量报告。

### 验收标准

1. 润色质量提升。
2. 没有过度改写。
3. change log 完整。
4. 成本记录。
5. 可决定是否扩展。
6. Key 未泄露。
7. 样例范围清晰。

### 不做事项

不跑整本，不批量调用强模型，不覆盖正式稿。

### 下一轮衔接

进入 Round 31，做润色 Pipeline MVP。

## Round 31：润色 Pipeline MVP

### 轮次类型

implementation

### 背景

润色需要独立于初翻保存，并记录 change log 和风险。

### 目标

实现润色 pipeline。

### 具体任务

1. 读取初翻。
2. 读取原文。
3. 读取知识资产。
4. 构建润色 context。
5. 调 provider。
6. 保存 refined。
7. 保存 change log。
8. 更新 review status。
9. 支持失败重试。
10. 增加测试。

### 产出文件

refinement pipeline、refined 输出、change log、状态更新、测试。

### 验收标准

1. pipeline 可运行。
2. refined 与 draft 分离。
3. change log 可追踪。
4. 不覆盖初翻。
5. 可批量扩展。
6. 失败可重试。
7. 支持 fake provider。

### 不做事项

不默认调用真实 API，不覆盖人工稿，不忽略 review issue。

### 下一轮衔接

进入 Round 32，做润色前后 diff 系统。

## Round 32：润色前后 diff 系统

### 轮次类型

implementation

### 背景

人工审核需要清晰看到初翻和润色的变更、删减、术语变化和风险。

### 目标

展示初翻和润色差异。

### 具体任务

1. 实现文本 diff。
2. 支持段落级 diff。
3. 支持词句级粗略 diff。
4. 标记术语变化。
5. 标记新增删减。
6. 标记风险。
7. 输出 Markdown。
8. 输出 JSON。
9. 增加测试。
10. 更新审核流程。

### 产出文件

diff 工具、Markdown diff、JSON diff、测试。

### 验收标准

1. diff 可读。
2. 风险可定位。
3. 支持人工审核。
4. 不误判全部文本。
5. 可给前端使用。
6. 标记术语变更。
7. 标记明显删减。

### 不做事项

不自动接受润色，不自动重写段落，不忽略 risk notes。

### 下一轮衔接

进入 Round 33，做批量任务调度与状态机。

## Round 33：批量任务调度与状态机

### 轮次类型

implementation

### 背景

批量初翻、审核和润色都需要章节级状态机和断点恢复。

### 目标

建立章节级任务状态机。

### 具体任务

1. 设计任务状态。
2. 支持 `pending`。
3. 支持 `processing`。
4. 支持 `translated`。
5. 支持 `reviewed`。
6. 支持 `refined`。
7. 支持 `failed`。
8. 支持 `retry`。
9. 支持 `skip`。
10. 更新 progress。

### 产出文件

task state schema、状态管理器、progress 更新、测试。

### 验收标准

1. 状态可追踪。
2. 失败可恢复。
3. 支持批次。
4. 不重复处理完成项。
5. 可供前端显示。
6. 状态变更有记录。
7. 支持 dry-run。

### 不做事项

不实现复杂队列服务，不默认并发调用真实 API，不覆盖完成项。

### 下一轮衔接

进入 Round 34，做成本记录与预算保护。

## Round 34：成本记录与预算保护

### 轮次类型

implementation

### 背景

多 provider 和批量调用必须有成本估算、实际 usage 和超限停止。

### 目标

记录模型调用和预算。

### 具体任务

1. 记录 provider。
2. 记录 model。
3. 记录 token 估算。
4. 记录实际返回。
5. 记录调用时间。
6. 记录章节。
7. 记录阶段。
8. 设计预算上限。
9. 超限停止。
10. 输出成本报告。

### 产出文件

budget guard、model run usage、cost report、测试。

### 验收标准

1. 成本可追踪。
2. 预算可配置。
3. 超限不继续调用。
4. 不泄露 Key。
5. 报告可读。
6. 支持 per-stage 统计。
7. 支持 dry-run 估算。

### 不做事项

不无预算调用，不把 Key 写入报告，不隐藏失败调用。

### 下一轮衔接

进入 Round 35，做 CLI MVP。

## Round 35：CLI MVP

### 轮次类型

implementation

### 背景

前端前需要稳定的本地命令入口串联核心 pipeline。

### 目标

建立最小命令行入口。

### 具体任务

1. `scan`
2. `prepare`
3. `extract-terms`
4. `build-context`
5. `translate-one`
6. `translate-batch`
7. `review`
8. `refine-one`
9. `export`
10. `status`

### 产出文件

CLI 入口、help 文档、dry-run 示例、测试。

### 验收标准

1. 命令可执行。
2. 有 help。
3. 不误调用真实 API。
4. 支持 dry-run。
5. README 更新。
6. 错误提示清晰。
7. 支持项目路径参数。

### 不做事项

不实现复杂后台服务，不绕过预算保护，不默认处理真实全书。

### 下一轮衔接

进入 Round 36，做前端信息架构落地。

## Round 36：前端信息架构落地

### 轮次类型

frontend design

### 背景

前端需要先明确页面路由、导航、数据流和组件关系，避免直接堆 UI。

### 目标

把前端页面从规划转为信息架构。

### 具体任务

1. 设计页面路由。
2. 设计导航。
3. 设计数据流。
4. 设计项目列表。
5. 设计章节列表。
6. 设计术语编辑。
7. 设计角色编辑。
8. 设计审核页面。
9. 设计设置页。
10. 生成 wireframe 文档。

### 产出文件

前端信息架构文档、wireframe 文档、数据流图。

### 验收标准

1. 页面关系清楚。
2. 数据来源清楚。
3. 不写复杂前端。
4. 可进入 MVP。
5. 与 pipeline 对齐。
6. 页面写入权限明确。
7. API/本地数据边界明确。

### 不做事项

不实现 React，不接后端，不写入真实项目数据。

### 下一轮衔接

进入 Round 37，做前端静态 MVP。

## Round 37：前端静态 MVP

### 轮次类型

frontend implementation

### 背景

静态前端可用 mock data 验证信息密度和审核流程，不依赖后端。

### 目标

实现静态前端页面。

### 具体任务

1. 建立 frontend skeleton。
2. 创建 dashboard。
3. 创建 project page。
4. 创建 glossary page。
5. 创建 character page。
6. 创建 review page。
7. 使用 mock data。
8. 不接真实 API。
9. 更新文档。
10. 增加截图说明，如适用。

### 产出文件

frontend skeleton、静态页面、mock data、文档。

### 验收标准

1. 页面可打开。
2. 结构清晰。
3. 不依赖后端。
4. mock data 可替换。
5. 不影响核心 pipeline。
6. 不读取真实正文。
7. 页面无明显重叠。

### 不做事项

不调用 API，不实现复杂编辑，不写入真实数据。

### 下一轮衔接

进入 Round 38，前端读取本地数据。

## Round 38：前端与本地数据连接

### 轮次类型

frontend implementation

### 背景

前端需要能读取 pipeline 生成的本地 JSON/Markdown 数据，用于只读审核。

### 目标

让前端读取本地生成的 JSON/Markdown 数据。

### 具体任务

1. 读取 project metadata。
2. 读取 chapters。
3. 读取 glossary。
4. 读取 characters。
5. 读取 review issues。
6. 显示 progress。
7. 显示译文对照。
8. 不写入真实数据。
9. 更新文档。
10. 增加测试。

### 产出文件

本地数据读取层、页面绑定、测试、文档。

### 验收标准

1. 前端能显示真实项目数据。
2. 不修改原文。
3. 数据路径可配置。
4. 页面可用于审核。
5. 后续可增加编辑。
6. 读取失败有提示。
7. 不暴露敏感信息。

### 不做事项

不编辑数据，不调用远程 API，不上传文件。

### 下一轮衔接

进入 Round 39，做前端编辑能力 MVP。

## Round 39：前端编辑能力 MVP

### 轮次类型

frontend implementation

### 背景

术语、角色、世界观和 issue 需要人工编辑能力，但必须有变更记录和锁定保护。

### 目标

支持编辑术语、角色和审核标记。

### 具体任务

1. 编辑 glossary。
2. 编辑 character profile。
3. 编辑 world bible entry。
4. 标记 review issue。
5. 保存到本地 JSON。
6. 保留变更记录。
7. 防止覆盖 locked term。
8. 增加确认提示。
9. 更新文档。
10. 增加测试。

### 产出文件

前端编辑页面、本地保存逻辑、变更记录、测试。

### 验收标准

1. 可编辑。
2. 可保存。
3. 有变更记录。
4. 不破坏数据结构。
5. 可供 pipeline 读取。
6. locked term 不被覆盖。
7. 高风险操作有确认。

### 不做事项

不公开发布数据，不绕过 schema 校验，不批量改正文。

### 下一轮衔接

进入 Round 40，做完整短篇闭环验证。

## Round 40：完整短篇闭环验证

### 轮次类型

end-to-end validation

### 背景

需要用短篇样例验证从导入、解析、抽取、初翻、审核、润色、导出到前端查看的完整闭环。

### 目标

用短篇样例完成完整流程验证。

### 具体任务

1. 导入短篇样例。
2. 扫描章节。
3. 抽取术语。
4. 抽取角色。
5. 建世界观。
6. 构建 context。
7. 初翻。
8. 审核。
9. 润色。
10. 导出。
11. 前端查看。
12. 成本记录。
13. 生成完整报告。

### 产出文件

短篇样例项目、完整 pipeline 输出、前端展示、成本报告、闭环验证报告。

### 验收标准

1. 端到端流程跑通。
2. 不使用真实版权长篇。
3. 输出结构完整。
4. 问题可追踪。
5. 可进入真实小说试跑阶段。
6. 成本和模型调用可审计。
7. 前端可查看核心数据。

### 不做事项

不直接进入生产级公开发布，不默认处理真实长篇，不跳过人工审核。

### 下一轮衔接

根据闭环报告决定进入真实小说受控试跑、性能优化、多项目管理或服务端化路线。
