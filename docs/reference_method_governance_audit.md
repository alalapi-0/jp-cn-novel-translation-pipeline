# Reference Method Governance Audit

## 扫描时间

2026-06-02 08:35 Asia/Shanghai。

## 当前 Git 分支

`main`。

## 当前仓库结构摘要

当前仓库是以治理、架构规划、路线图和 Prompt 交接为主的中日文小说互译生产流水线仓库。顶层已包含 `README.md`、`AGENTS.md`、`project.yaml`、`governance/`、`docs/`、`prompts/`、`input_jp/`、`input_cn/`、`output_cn/`、`output_jp/`、`shared/`、`directions/`、`workspace/`、`data/`、`src/`、`frontend/`、`scripts/`、`tests/` 和 `notes/`。

当前实现层仍很轻：`src/`、`frontend/`、`tests/` 基本是 README 占位；`scripts/` 里主要是历史脚本。项目事实与 `project.yaml` 的 `stage: governance_and_architecture` 一致。

## 已存在核心文档

- `README.md`
- `AGENTS.md`
- `project.yaml`
- `governance/repo_protocol_standard.yaml`
- `governance/agent_policy.yaml`
- `governance/round_state.yaml`
- `governance/file_role_map.yaml`
- `governance/model_policy.yaml`
- `governance/data_policy.yaml`
- `governance/novel_pipeline_contract.yaml`
- `docs/index.md`
- `docs/project_vision.md`
- `docs/architecture_overview.md`
- `docs/shared_core_design.md`
- `docs/governance_rules.md`
- `docs/repo_protocol_alignment.md`
- `docs/agent_operating_manual.md`
- `docs/agent_gate_and_protocol_check.md`

## 已存在路线图

- `docs/roadmap_rounds_00_40.md`：长期产品与流水线路线。
- `docs/roadmap_rounds_41_50_tooling_and_workbench.md`：工具链、Agent Gate、Playwright/MCP、受控 API 与 Workbench 路线。
- `docs/archive/legacy_roadmaps/roadmap_translation_pipeline.md`：早期日译中路线（已归档）。

本轮新增 RM 路线必须与既有 Round 00-50 不互相覆盖。RM 只表示 Reference Method Absorption，不替代原路线。

## 已存在 Prompt 模板

已存在治理轮、实现轮、翻译执行轮、审核轮、前端轮、API 接入轮、工具链轮、协议对齐轮、MCP 设置轮、Playwright 前端审核轮和 Agent Gate 轮模板。已存在 Round 01-12 与 Round 41-50 的 Prompt 草案。

## 已存在目录结构

- `input_jp/` 与 `input_cn/`：原文输入目录，真实版权文本默认不提交。
- `output_cn/` 与 `output_jp/`：译文、双语对照和审核输出目录，真实译文默认不提交。
- `shared/`：共享核心能力规划位置。
- `directions/jp_to_cn/` 与 `directions/cn_to_jp/`：方向专属规则位置。
- `workspace/`：中间态、model run、checkpoint、embedding、vector store 等本地工作区。
- `data/`：schema、样例和项目结构化数据位置。
- `src/`、`frontend/`、`tests/`：未来实现、前端与测试位置。

## 当前仓库优点

1. 已经从单本日译中任务升级为双向中日文小说互译生产流水线定位。
2. 已有通用协议、项目身份、Agent 策略、数据策略和流水线契约。
3. 输入输出目录、方向目录、shared core、workspace、data、frontend、tests 等骨架齐全。
4. `.gitignore` 已保护 `.env`、真实原文、真实译文、notes、workspace 运行产物和报告正文。
5. 已有术语、角色、世界观、翻译记忆、embedding、provider、batch、refinement、review、frontend 等设计文档雏形。
6. 已有 Round 00-50 路线和多类 Prompt 模板，适合后续 Agent 连续推进。

## 当前仓库不足

1. 参考仓库方法尚未沉淀为本项目自己的统一方法栈。
2. `paragraph_id`、`segment_id`、JSONL 中间态、状态机和 exporter-only 原则仍需更明确。
3. ResponseExtractor、Validator、Prompt 输出契约、校验失败不写入等质量门尚未形成独立设计。
4. Checkpoint、LLM response cache、Translation Memory 的边界需要明确区分。
5. Provider Adapter 已有策略，但 registry、model result、retry、cost guard 等接口需要进一步固化。
6. 质量错误 taxonomy 需要统一标签，避免 review issue 各轮自造字段。
7. Round 41-50 的工具链路线假设前 40 轮部分能力已存在，但当前实际仍以文档和占位为主，需要通过 RM 路线补充落地顺序。

## 本轮可直接扩写的文件

- `README.md`
- `docs/repo_protocol_alignment.md`
- `docs/architecture_overview.md`
- `docs/shared_core_design.md`
- `docs/batch_translation_workflow.md`
- `docs/refinement_workflow.md`
- `docs/quality_review_workflow.md`
- `docs/api_provider_strategy.md`
- `docs/data_schema_plan.md`
- `docs/governance_rules.md`
- `docs/agent_operating_manual.md`
- `docs/agent_gate_and_protocol_check.md`
- `docs/index.md`
- `governance/round_state.yaml`

## 本轮需要新增的文件

- `docs/reference_repo_methodology_integration.md`
- `docs/current_project_method_stack.md`
- `docs/reference_inspired_pipeline_design.md`
- `docs/stable_id_and_jsonl_design.md`
- `docs/chunking_context_strategy_reference_inspired.md`
- `docs/dynamic_injection_design.md`
- `docs/prompt_contract_reference_inspired.md`
- `docs/extractor_validator_reference_inspired.md`
- `docs/cache_checkpoint_translation_memory_design.md`
- `docs/provider_adapter_reference_inspired.md`
- `docs/exporter_reference_inspired_design.md`
- `docs/translation_quality_taxonomy_reference_inspired.md`
- `docs/roadmap_rounds_reference_method_01_40.md`
- `prompts/rm_01_reference_method_overview.md` 到 `prompts/rm_10_world_bible_injection.md`

## 建议归档或合并的文件

早期路线图（`docs/archive/legacy_roadmaps/`）已于 2026-06-12 归档。`docs/translation_pipeline_design.md`、`docs/embedding_memory_design.md` 等设计文档仍有历史价值，由 `docs/index.md` 标记为历史资料。

## 不应修改的文件

- `.env` 与任何密钥文件。
- `input_jp/`、`input_cn/` 内真实原文。
- `output_cn/`、`output_jp/` 内真实译文。
- `governance/repo_protocol_standard.yaml` 正文，除非同步通用协议本体。
- `docs/archive/governance/repo_protocol_standard_truncated_backup.yaml`。
- `docs/archive/legacy_roadmaps/translation_pipeline_governance_round.yaml`（已归档）。

## 本轮治理策略

本轮只迁移方法，不复制代码，不把当前项目改造成任何单一参考仓库的副本。吸收重点是稳定 ID、JSONL 中间态、语义分块、动态知识注入、Prompt 分层和版本化、机器可解析输出、ResponseExtractor、Validator、校验失败不写入、状态机断点、SQLite checkpoint、LLM response hash cache、Translation Memory、Provider Adapter Registry、Exporter、Quality Taxonomy 和 Review Workbench Data Contract。

本轮新增文档应进入 `docs/index.md` 导航，RM 路线与 Prompt 应清楚标注为参考方法吸收路线，不覆盖既有 Round 00-50。所有真实 API、真实翻译、embedding、向量库和复杂前端实现均留给后续明确轮次。
