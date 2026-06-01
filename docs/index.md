# 项目文档导航

本仓库正在从单本日译中任务仓库升级为中日文小说互译生产流水线。后续 Agent 应优先阅读治理入口文档，再进入具体实现或执行轮。

## 必读治理入口

- `README.md`
- `AGENTS.md`
- `project.yaml`
- `governance/repo_protocol_standard.yaml`
- `docs/current_repository_audit.md`
- `docs/governance_round_02_audit.md`
- `docs/repo_protocol_alignment.md`
- `docs/project_vision.md`
- `docs/architecture_overview.md`
- `docs/shared_core_design.md`
- `docs/governance_rules.md`
- `docs/agent_operating_manual.md`
- `docs/roadmap_rounds_00_40.md`
- `docs/roadmap_rounds_41_50_tooling_and_workbench.md`
- `docs/migration_notes.md`

## 工具链与协议文档

- `docs/agent_tooling_strategy.md`
- `docs/mcp_playwright_setup_plan.md`
- `docs/agent_gate_and_protocol_check.md`

## 核心设计文档

- `docs/terminology_system_design.md`
- `docs/character_profile_system.md`
- `docs/world_bible_system.md`
- `docs/translation_memory_design.md`
- `docs/embedding_vector_db_design.md`
- `docs/api_provider_strategy.md`
- `docs/data_schema_plan.md`
- `docs/directory_evolution_plan.md`
- `docs/batch_translation_workflow.md`
- `docs/refinement_workflow.md`
- `docs/quality_review_workflow.md`
- `docs/frontend_workbench_plan.md`

## 历史与早期文档

- `docs/translation_project_positioning.md`
- `docs/translation_pipeline_design.md`
- `docs/embedding_memory_design.md`
- `docs/openrouter_api_test_plan.md`
- `docs/roadmap_translation_pipeline.md`
- `docs/reports/`：本地报告目录，项目专有报告默认不提交公开仓库。

## Prompt 模板目录

- `prompts/governance_round_template.md`
- `prompts/implementation_round_template.md`
- `prompts/translation_execution_round_template.md`
- `prompts/review_round_template.md`
- `prompts/frontend_round_template.md`
- `prompts/api_integration_round_template.md`
- `prompts/tooling_round_template.md`
- `prompts/protocol_alignment_round_template.md`
- `prompts/mcp_setup_round_template.md`
- `prompts/playwright_frontend_review_round_template.md`
- `prompts/agent_gate_round_template.md`

## 前 12 轮 Prompt 草案

- `prompts/round_01_repository_normalization.md`
- `prompts/round_02_shared_core_design.md`
- `prompts/round_03_jp_to_cn_direction_design.md`
- `prompts/round_04_cn_to_jp_direction_design.md`
- `prompts/round_05_project_schema_design.md`
- `prompts/round_06_source_file_scanner.md`
- `prompts/round_07_chapter_parser.md`
- `prompts/round_08_text_cleaning_segmenter.md`
- `prompts/round_09_terminology_candidate_extraction.md`
- `prompts/round_10_character_candidate_extraction.md`
- `prompts/round_11_world_bible_candidate_extraction.md`
- `prompts/round_12_provider_adapter_design.md`

## Round 41–50 工具链 Prompt 草案

- `prompts/round_41_agent_gate_mvp.md`
- `prompts/round_42_repo_protocol_checker.md`
- `prompts/round_43_tooling_environment_audit.md`
- `prompts/round_44_playwright_smoke_test_setup.md`
- `prompts/round_45_playwright_mcp_integration.md`
- `prompts/round_46_frontend_review_workbench_visual_verification.md`
- `prompts/round_47_api_dry_run_cost_guard.md`
- `prompts/round_48_vector_db_inspection_tools.md`
- `prompts/round_49_translation_quality_auto_review_workbench.md`
- `prompts/round_50_e2e_agent_assisted_trial.md`

## 其他资源

- `CHANGELOG.md`：项目变更记录。
- `round_state/translation_pipeline_governance_round.yaml`：历史治理状态文件。
- `config/openrouter.example.yaml`：历史 OpenRouter 示例配置。
- `.env.example`：仅包含环境变量名，不包含真实密钥。
