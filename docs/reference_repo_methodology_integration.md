# 参考仓库方法论迁移总纲

## 1. 本文目标

本文把 AiNiee、GalTransl、TranslateBooksWithLLMs、epub-translator-oomol、SakuraLLM、LiteraryTranslation、LunaTranslator、BallonsTranslator、epub-translator-slyh 的工程经验转化为当前中日文小说互译项目自己的方法论与推进顺序。

本项目只吸收参考仓库中可迁移的工程逻辑、架构逻辑和实现方法，不直接复制参考仓库代码，不将当前项目变成任何单一参考仓库的副本。

## 2. 参考仓库来源

- AiNiee：批量翻译工程、缓存状态、术语辅助、分析任务、ResponseExtractor / Checker 思路。
- GalTransl：游戏与小说文本 JSON 化、动态字典注入、前后处理、Problem 记录。
- TranslateBooksWithLLMs：TokenChunker、上下文窗口、SQLite checkpoint、长文本批处理。
- epub-translator-oomol：EPUB translate + fill、hash cache、结构回填。
- SakuraLLM：Prompt 约束、结构保真、版本化与质量检查。
- LiteraryTranslation：错误 taxonomy、pairwise review、span-level 质量分析。
- LunaTranslator：多引擎 registry、轻量配置与可替换 provider。
- BallonsTranslator：批量结构化输出、失败回退、OCR/漫画旁路启发。
- epub-translator-slyh：EPUB 与阅读输出方向的补充参考。

## 3. 总体吸收原则

1. 只迁移方法，不复制代码。
2. 优先吸收低成本高收益方法。
3. 原文保持只读，译文和审核状态进入中间态。
4. 共享能力沉淀到 shared core，方向差异保留在 `JP_TO_CN` / `CN_TO_JP` 规则层。
5. 真实 API、真实 embedding、真实长篇翻译必须由后续授权轮次执行。
6. 任何最终阅读文件只能由 exporter 从中间态生成。
7. 校验失败的模型输出不能写入 `translated` / `final`。

## 4. 三类参考价值

### 流水线工程

代表仓库：AiNiee、GalTransl、TranslateBooksWithLLMs、epub-translator-oomol。

吸收为：parser -> segment -> translate -> validate -> export 的主链路，以及 JSONL / checkpoint / status / retry / exporter-only 等工程边界。

### 质量与契约

代表仓库：SakuraLLM、LiteraryTranslation。

吸收为：Prompt 分层、Prompt 版本化、机器可解析输出、结构保真、Validator、Review Issue taxonomy、小型 benchmark 与人工校对工作流。

### 旁路扩展

代表仓库：LunaTranslator、BallonsTranslator、epub-translator-slyh。

吸收为：Provider Registry、多引擎抽象、轻量断点、未来阅读/EPUB/漫画/OCR 旁路。旁路不进入 MVP 主线。

## 5. P0 必须吸收的方法

| 方法 | 项目落点 | 后续轮次 |
|------|----------|----------|
| stable id | `paragraph_id` / `segment_id` | RM-03 |
| JSONL 中间态 | `workspace/segments/*.jsonl` | RM-04 |
| paragraph_id | 段落级追踪 | RM-03 |
| segment_id | 长段拆分和 batch 输出对齐 | RM-03 |
| semantic chunking | `shared/segmenter` | RM-06 |
| dynamic glossary injection | `shared/glossary` + context pack | RM-08 |
| dynamic character injection | `shared/character_profiles` + context pack | RM-09 |
| prompt layers | `PromptBuilder` | RM-11 |
| prompt_version | ModelRun、cache、TM、review report | RM-12 |
| machine-parseable output | JSON contract + numbered fallback | RM-13 |
| ResponseExtractor | provider raw output -> structured result | RM-14 |
| Validator | structured result -> validation result | RM-15 |
| 校验失败不写入 | status machine + writer guard | RM-15 |
| status machine | JSONL / checkpoint | RM-17 |
| failed retry | retry queue | RM-17 |
| provider adapter | `shared/model_provider` | RM-20 |
| Markdown bilingual exporter | `shared/exporter` | RM-36 |

## 6. P1 稳定性增强方法

| 方法 | 项目落点 | 后续轮次 |
|------|----------|----------|
| TokenChunker | 语义分块与 token soft limit | RM-06 |
| context_before | Context Pack | RM-07 |
| previous_translation | Context Pack | RM-07 |
| SQLite checkpoint | 可选进度数据库 | RM-18 |
| LLM response hash cache | API 成本控制 | RM-19 |
| Translation Memory | 复用历史译法 | RM-28 |
| Problem taxonomy | ReviewIssue schema | RM-16 |
| character voice checker | 角色语气一致性 | RM-26 |
| term conflict checker | 术语一致性 | RM-25 |
| small benchmark | 回归评估 | RM-38 |

## 7. P2 未来扩展方法

| 方法 | 项目落点 | 后续轮次 |
|------|----------|----------|
| EPUB translate + fill | EPUB 后期导出 | RM-37 |
| Web Review Workbench | 前端审核工作台 | RM-39 |
| Playwright 页面验证 | UI smoke / regression | Round 44-46 / RM-39 |
| multi-provider routing | provider registry 扩展 | RM-20+ |
| vector DB | 相似片段检索 | RM-29 / RM-30 |
| reading/review mode | 未来阅读器与校对界面 | RM-39+ |
| manga/OCR 旁路 | 远期旁路，不进主线 | backlog |

## 8. 不建议迁移的内容

1. 完整 GUI 或复杂桌面端。
2. OCR、漫画 inpaint、气泡检测等图像处理能力。
3. 实时阅读 hook。
4. 全量多格式 reader。
5. 复杂 EPUB 回填作为 MVP 主线。
6. 本地推理服务和重型模型部署。
7. 任一参考仓库的代码结构、命名习惯或实现细节照搬。

## 9. 当前项目的落地顺序

1. 先固化 stable ID、JSONL、状态机和数据链路。
2. 再实现 parser、semantic chunker、context pack。
3. 然后接入动态术语、角色与世界观注入。
4. 随后实现 PromptBuilder、输出契约、ResponseExtractor、Validator。
5. 用 fake/dry-run provider 跑通批量链路。
6. 再进入受控真实 API、Translation Memory、cache、checkpoint。
7. 最后扩展 exporter、review workbench、benchmark、EPUB 与向量检索。

## 10. 对现有路线图的影响

RM 路线已归档为历史参考，不取代 `docs/final_state_implementation_roadmap.md` 与 `docs/final_state_round_task_list.md`。后续吸收参考方法时，必须先映射到 v2 production / consistency / singleton export 协议。

后续 Agent 不再从 RM 或 Round 00-50 编号取下一轮任务；只从 FS-v2 任务列表取任务。

## 11. 与通用协议的关系

本轮遵守 `governance/repo_protocol_standard.yaml` 的权威层级、文件角色、安全边界和 Round 生命周期。参考仓库方法属于项目级业务方法，不应写入或覆盖通用协议正文。若项目方法与通用协议冲突，应在 `project.yaml` 或 `docs/repo_protocol_alignment.md` 中记录 override 或风险。

## 12. 后续推进轮建议

优先进入：

1. RM-02：核心数据链路设计。
2. RM-03：稳定 ID 规则。
3. RM-04：JSONL 中间态 Schema。
4. RM-05：Parser MVP。

若先补工具链，则可并行执行 Round 41 Agent Gate MVP，以确保后续 RM 实现轮有确定性安全门控。
