# 当前项目方法栈

本文把参考仓库经验转化为当前项目自己的技术方法栈。每项均标注来源参考、当前项目用途、实现优先级、后续轮次与不做事项。

## 4.1 MVP 方法栈

| 方法 | 来源参考 | 当前项目用途 | 实现优先级 | 后续轮次 | 不做事项 |
|------|----------|--------------|------------|----------|----------|
| `paragraph_id` 稳定标识 | AiNiee、GalTransl、oomol | 段落级追踪、审核定位、导出回链 | P0 | RM-03 | 不把数组下标当唯一真相 |
| JSONL 一行一段 | AiNiee、GalTransl | 中间态、断点续跑、人工审核 | P0 | RM-04 | 不直接改原文文件 |
| status 状态机 | AiNiee、TBL | 控制 queued / translated / failed / final | P0 | RM-04、RM-17 | 不用布尔字段替代状态机 |
| `glossary.yaml` | GalTransl、AiNiee | 术语一致性资产 | P0 | RM-08 | 不全量无差别塞进 Prompt |
| `character_profile.yaml` | AiNiee、GalTransl | 角色语气、称呼和敬语控制 | P0 | RM-09 | 不把角色百科全量塞入上下文 |
| `style_profile.yaml` | SakuraLLM、LiteraryTranslation | 文体目标和方向规则 | P0 | RM-11、RM-12 | 不和方向规则混成不可复用文本 |
| `prompt_version` | SakuraLLM | cache、TM、review、重译计划依据 | P0 | RM-12 | 不允许未版本化 Prompt 进入正式 run |
| OpenAI-compatible adapter + mock provider | TBL、AiNiee、Luna | fake/dry-run 先跑通，真实 API 后接 | P0 | RM-20 | 不在业务流程写死 provider |
| ResponseExtractor | AiNiee、BallonsTranslator | raw output -> structured result | P0 | RM-14 | 不让解析失败污染译文 |
| Validator | AiNiee、SakuraLLM、GalTransl | 结构与质量门控 | P0 | RM-15 | 不把 validation_failed 写入 final |
| Markdown 双语导出 | AiNiee、oomol | 初期阅读和审核输出 | P0 | RM-36 | 不让 exporter 调模型 |
| failed 段重试 | AiNiee、TBL | 单段回退、有限重试 | P0 | RM-17 | 不无限重试，不静默覆盖 locked |

## 4.2 稳定性方法栈

| 方法 | 来源参考 | 当前项目用途 | 实现优先级 | 后续轮次 | 不做事项 |
|------|----------|--------------|------------|----------|----------|
| TokenChunker | TranslateBooksWithLLMs、oomol | token soft limit 与语义边界分块 | P1 | RM-06 | 不硬切字符串 |
| `context_before` | TBL、AiNiee | 提供前 1-3 段上下文 | P1 | RM-07 | 不塞整章整书 |
| `previous_translation` | TBL、GalTransl | 保持译文承接与称呼一致 | P1 | RM-07 | 不把未校验译文当事实 |
| batch translation | AiNiee、GalTransl、BallonsTranslator | 成本与吞吐控制 | P1 | RM-22 | 不越过 Validator 直接落盘 |
| Problem taxonomy | GalTransl、LiteraryTranslation | 统一 ReviewIssue 标签 | P1 | RM-16 | 不让各 checker 自造冲突标签 |
| SQLite checkpoint | TBL | 可选任务状态库 | P1 | RM-18 | 不取代 JSONL 可读中间态 |
| LLM response hash cache | oomol | 避免重复 API 请求 | P1 | RM-19 | 不把 cache 当翻译记忆 |
| provider registry | Luna、BallonsTranslator、AiNiee | 多 provider 可替换 | P1 | RM-20 | 不把真实 API 放到治理轮 |
| translation memory | TBL、GalTransl | 复用已审核译法 | P1 | RM-28 | 不把未审核 draft 默认 preferred |
| term consistency checker | GalTransl、AiNiee | locked / deprecated / conflict 检查 | P1 | RM-25 | 不自动改 locked term |
| character voice checker | LiteraryTranslation、GalTransl | 第一人称、敬语、称呼一致性 | P1 | RM-26 | 不把所有角色润成同一种声音 |

## 4.3 质量增强方法栈

| 方法 | 来源参考 | 当前项目用途 | 实现优先级 | 后续轮次 | 不做事项 |
|------|----------|--------------|------------|----------|----------|
| AnalysisTask | AiNiee | 自动抽取术语、角色、世界观候选 | P2 | RM-31 | 不把候选直接 approved |
| 术语自动抽取 | AiNiee、GalTransl | 建立 candidate glossary | P2 | RM-31 | 不越过人工/审核确认 |
| 角色自动抽取 | AiNiee | 建立 character candidate | P2 | RM-31 | 不自动锁定角色设定 |
| 世界观自动抽取 | AiNiee | 建立 world bible candidate | P2 | RM-31 | 不提前解释剧透 |
| LiteraryTranslation-style taxonomy | LiteraryTranslation | 细粒度质量错误分类 | P1 | RM-16、RM-38 | 不把主观偏好当硬错误 |
| small benchmark | LiteraryTranslation | Prompt / provider 回归评估 | P2 | RM-38 | 不使用版权文本 |
| refinement pipeline | AiNiee、LiteraryTranslation | 初翻后强模型润色 | P2 | RM-33、RM-34 | 不覆盖初翻稿 |
| diff / change log | LiteraryTranslation | 润色可审计 | P2 | RM-35 | 不只保留最终稿 |
| over-refinement checker | LiteraryTranslation | 防止过度改写、增删信息 | P2 | RM-35 | 不鼓励模型擅自扩写剧情 |

## 4.4 未来扩展方法栈

| 方法 | 来源参考 | 当前项目用途 | 实现优先级 | 后续轮次 | 不做事项 |
|------|----------|--------------|------------|----------|----------|
| EPUB 双阶段 translate + fill | epub-translator-oomol、epub-translator-slyh | 先翻纯文本，再回填结构 | P2 | RM-37 | 不作为 Markdown MVP 前置条件 |
| Web Review Workbench | AiNiee、LiteraryTranslation | 原文译文对照、issue、diff、资产编辑 | P2 | RM-39 | 不提前实现复杂 UI |
| Playwright UI verification | 工具链路线、Workbench 参考 | 页面 smoke 与回归验证 | P2 | Round 44-46 / RM-39 | 不用于读取敏感文件 |
| MCP-assisted frontend review | Cursor MCP 工具链 | 辅助浏览器验证和前端反馈 | P2 | Round 45-46 | 不替代确定性测试 |
| multi-provider routing | Luna、BallonsTranslator | 不同阶段选择不同模型 | P2 | RM-20+ | 不无预算保护地自动路由真实 API |
| vector DB retrieval | TBL、当前 embedding 规划 | 相似片段、角色台词、TM 检索 | P2 | RM-29、RM-30 | 不让向量库替代结构化资产 |
| user correction feedback loop | AiNiee、Review Workbench | 人工修改反哺 TM / glossary / character | P2 | RM-39+ | 不静默覆盖人工锁定内容 |
