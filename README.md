# 中日文小说互译生产流水线

本仓库用于规划和逐步建设一个面向长篇小说与轻小说的中日文互译生产流水线。它不再只是一次性的“日文小说翻译成中文”任务目录，而是面向长期项目管理、双向翻译、术语一致性、角色语气控制、世界观设定管理、检索增强、批量初翻、二次润色和人工审核工作台的治理仓库。

当前仓库仍处于治理与架构准备阶段，不是生产级公开翻译发布工具。

## 当前阶段

当前阶段是仓库治理、架构规划与路线扩写阶段。本阶段可以补充目录、文档、Prompt 模板、路线图和轻量占位文件，但不启动真实小说翻译、不调用真实 API、不生成 embedding、不建立真实向量库、不实现复杂前端。

## 支持方向

- `JP_TO_CN`：日文小说到中文小说翻译。
- `CN_TO_JP`：中文小说到日文小说翻译。

两个方向共享文件扫描、章节解析、术语库、角色设定、世界观设定、翻译记忆、embedding、向量库、模型 provider 抽象和审核框架；方向专属规则放在 `directions/jp_to_cn/` 与 `directions/cn_to_jp/`。

## 当前已完成内容

- 已存在早期日译中项目结构：`input_jp/`、`output_cn/`、`notes/`、`docs/`、`prompts/`。
- 已存在术语、人物、风格、翻译规则和进度类 notes。
- 已存在早期翻译流水线、术语系统和 embedding memory 相关文档。
- 本轮治理将保留旧结构，并在其上补齐双向流水线规划。

## 未来路线

项目按 Round 推进，核心路线见 `docs/roadmap_rounds_00_40.md`：

1. 仓库结构标准化。
2. shared core 与方向专属模块设计。
3. 日译中与中译日方向规则。
4. 项目配置与数据 schema。
5. 文件扫描、章节解析、文本清洗、段落切分。
6. 术语、角色、世界观候选抽取。
7. Provider、embedding、vector store adapter。
8. Context Pack、初翻、润色、审核、导出。
9. CLI、前端工作台和短篇闭环验证。

## 目录说明

- `input_jp/`：日文原文输入目录。真实版权文本默认不提交。
- `output_cn/`：中文译文输出目录，包含 translated、bilingual、review 等子目录。真实译文默认不提交。
- `input_cn/`：中文原文输入目录。真实版权文本默认不提交。
- `output_jp/`：日文译文输出目录，包含 translated、bilingual、review 等子目录。
- `notes/`：早期项目级术语、人名、风格、规则、进度记录。
- `docs/`：架构、治理、路线图、数据 schema、流程设计文档。
- `prompts/`：后续治理轮、实现轮、翻译执行轮、审核轮、前端轮、API 接入轮 Prompt。
- `shared/`：未来共享核心能力说明与实现位置。
- `directions/`：不同语言方向的规则和 Prompt。
- `workspace/`：中间数据、解析结果、context pack、model run、embedding 和向量索引的本地工作区。
- `data/`：项目级结构化数据、schema 和样例。
- `src/`：未来代码实现位置。
- `frontend/`：未来前端工作台位置。
- `scripts/`：已有脚本与后续轻量工具脚本。
- `tests/`：未来测试用例。

## 如何放入日文原文

将日文原文放入 `input_jp/`，并优先使用 `.md` 或 `.txt`。真实原文默认不提交到仓库。后续执行轮应先生成 manifest，再进行章节解析和段落切分；治理轮不得读取或处理正文。

## 如何放入中文原文

将中文原文放入 `input_cn/`，并优先使用 `.md` 或 `.txt`。真实原文默认不提交到仓库。中译日流程必须使用 `CN_TO_JP` 方向规则，不得混用 `JP_TO_CN` Prompt。

## 为什么需要术语库

长篇小说会反复出现人物、地点、组织、技能、制度、称号和口头禅。术语库用于记录 source text、target text、状态、首次出现位置、例句、冲突和锁定规则，保证全书译名一致。

## 为什么需要角色设定

角色设定用于维护姓名、别名、称呼关系、说话风格、第一人称、敬语等级和典型台词。它的目标不是写百科，而是防止初翻和润色阶段把不同角色处理成同一种声音。

## 为什么需要世界观设定

世界观设定用于保存地点、组织、制度、魔法、技能、历史、种族、伏笔等来自原文的证据化信息。它帮助模型理解上下文，但不能替代原文，也不能提前解释伏笔。

## 为什么需要 embedding

Embedding 用于检索相似段落、术语上下文、角色台词、世界观证据、翻译记忆和润色前后对比。向量库是检索辅助，不替代术语库、角色表、世界观设定或人工确认规则。

## 为什么初翻和润色要分开

初翻优先完整、忠实、不漏译、术语和人名一致；润色优先自然、风格统一、保留信息和修正机翻腔。二者分离可以降低成本、减少不可控重写，并保留可复查的 change log。

## 为什么未来需要前端

前端工作台用于让用户创建项目、选择方向、配置模型、查看章节、审核术语、维护角色和世界观、对照原文译文、处理冲突、启动润色和导出结果。前端目标是提升审核效率，不是炫酷展示。

## 安全与版权提醒

- 本项目不是盗版发布工具。
- 不鼓励未经授权公开发布受版权保护的原文或译文。
- 真实原文和真实译文默认不提交。
- `.env`、API Key、账号、用户隐私和敏感请求头不得提交。
- 日志和 metadata 不得输出完整 API Key。

## 后续 Agent 必读文档

每轮 Agent 应先读取：

- `governance/repo_protocol_standard.yaml`
- `project.yaml`
- `AGENTS.md`
- `README.md`
- `docs/project_vision.md`
- `docs/architecture_overview.md`
- `docs/roadmap_rounds_00_40.md`
- `docs/roadmap_rounds_41_50_tooling_and_workbench.md`
- `docs/governance_rules.md`
- `docs/repo_protocol_alignment.md`
- `docs/agent_operating_manual.md`
- `docs/current_repository_audit.md`

## Agent 工具链与推进方式

本项目是**中日文互译生产流水线**，不是单纯翻译脚本。后续 Agent 按 Round 推进，类型包括治理、实现、翻译执行、审核、前端、API 接入与工具链轮。工作方式见 `docs/agent_operating_manual.md` 与 `docs/agent_tooling_strategy.md`；每轮开始/结束 checklist 与硬软阻塞定义亦在该手册中。

Round 41 起将实现 `scripts/agent_gate.py` 作为统一门控入口。

## 通用协议对齐

仓库采用可移植治理标准 `governance/repo_protocol_standard.yaml`（v0.3.0）。对齐情况、冲突与迁移计划见 `docs/repo_protocol_alignment.md`。项目差异写入 `project.yaml` 与 `governance/novel_pipeline_contract.yaml`，不擅自改写协议正文。

## MCP / Playwright 路线

MCP 与 Playwright 是**增强工具**，不是当前强制依赖。安装时机、验证步骤、fallback 与安全规则见 `docs/mcp_playwright_setup_plan.md`。前端 Round 36–40 完成后，Round 44–46 引入 Playwright 与浏览器 Workbench 验证。

## 后续推进轮如何工作

1. 读取 `AGENTS.md` 与当前 Round Prompt。
2. 执行 `git status`，确认安全边界。
3. 只做当前 Round 范围内任务，不越级。
4. 更新 `governance/round_state.yaml` 与本地报告。
5. 用户或 Prompt 要求时再 commit；push 需用户授权。

## 当前不能做的事情

- 不启动真实长篇翻译（除非进入授权后的翻译执行轮）
- 不调用真实翻译 API（治理轮与未授权实现轮）
- 不生成 embedding、不建真实向量库（Round 48 之前）
- 不安装 Playwright/MCP（Round 44 之前，除非用户明确要求）
- 不提交 `.env`、真实原文、真实译文

## 下一轮建议

建议进入 **Round 41：Agent Gate MVP**（实现 `scripts/agent_gate.py`），或 **Round 42：Repo Protocol Checker**（实现协议合规检查脚本）。详见 `docs/roadmap_rounds_41_50_tooling_and_workbench.md`。
