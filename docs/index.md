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
- **Tool-aware Agent Layer 2.0：** `agent_layer.yaml`、`agent_tools.yaml`、`docs/AGENT_RUNBOOK.md`、`docs/TOOL_USAGE_POLICY.md`、`docs/AGENT_ROADMAP.md`、`reports/latest-agent-report.json`
- `docs/roadmap_rounds_00_40.md`
- `docs/roadmap_rounds_41_50_tooling_and_workbench.md`
- `docs/roadmap_phase2_rounds_51_plus.md`
- `docs/migration_notes.md`

## 设计输入层（Stitch）

- `docs/design/DESIGN.md`
- `docs/design/stitch/README.md`
- `docs/design/stitch/STITCH_MCP_SETUP.md`
- `docs/design/stitch/STITCH_WORKFLOW.md`
- `docs/design/stitch/UI_TASKS.md`
- `docs/design/stitch/PROMPT_TEMPLATES.md`
- `docs/design/stitch/EXPORT_GUIDE.md`

## 工具链与协议文档

- `docs/agent_tooling_strategy.md`
- `docs/mcp/README.md`
- `docs/mcp/WORKSPACE_MCP_SERVERS.md`
- `docs/mcp_playwright_setup_plan.md`
- `docs/mcp_verification_checklist.md`
- `docs/agent_skills/mcp_usage_skill.md`
- `docs/agent_skills/translation_qa_skill.md`（AL-010；Cursor skill: `.cursor/skills/translation-qa/`）
- `docs/testing/BROWSER_TESTING.md`
- `docs/testing/REAL_API_TESTING.md`
- `docs/testing/USER_PERSPECTIVE_TESTING.md`
- `docs/agent_gate_and_protocol_check.md`
- `docs/agent_workflow/runner_agent.md`
- `docs/agent_workflow/browser_inspector_agent.md`
- `docs/agent_workflow/bugfix_agent.md`
- `docs/agent_workflow/quality_optimizer_agent.md`
- `docs/agent_workflow/continuous_multi_agent_loop.md`
- `docs/agent_workflow/quality_gate.md`

## 核心设计文档

- `docs/reference_method_governance_audit.md`
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

## 参考方法吸收路线

- `docs/roadmap_rounds_reference_method_01_40.md`

RM 轮次表示 Reference Method Absorption，用于落地参考仓库方法，不替代 Round 00–50 总体路线。

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

## RM-01 到 RM-10 Prompt 草案

- `prompts/rm_01_reference_method_overview.md`
- `prompts/rm_02_core_data_flow.md`
- `prompts/rm_03_stable_id_rules.md`
- `prompts/rm_04_jsonl_schema.md`
- `prompts/rm_05_parser_mvp.md`
- `prompts/rm_06_semantic_chunker.md`
- `prompts/rm_07_context_pack.md`
- `prompts/rm_08_dynamic_glossary.md`
- `prompts/rm_09_character_injection.md`
- `prompts/rm_10_world_bible_injection.md`

## 其他资源

- `CHANGELOG.md`：项目变更记录。
- `round_state/translation_pipeline_governance_round.yaml`：历史治理状态文件。
- `config/openrouter.example.yaml`：历史 OpenRouter 示例配置。
- `.env.example`：仅包含环境变量名，不包含真实密钥。
