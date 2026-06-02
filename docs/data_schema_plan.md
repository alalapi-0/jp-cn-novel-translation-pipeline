# 数据 Schema 规划

## Project

### 用途

描述一本小说或一个翻译项目。

### 核心字段

`project_id`、`name`、`description`、`default_direction`、`root_path`、`created_at`、`updated_at`、`status`、`owner_note`。

### 关系

关联 DirectionConfig、SourceFile、Chapter、ProjectState、ModelRun。

### 是否进入向量库

否。

### 是否需要版本管理

需要轻量版本。

### 后续实现轮次

Round 05。

## DirectionConfig

### 用途

描述 `JP_TO_CN` 或 `CN_TO_JP` 的输入输出和规则选择。

### 核心字段

`direction_config_id`、`project_id`、`language_direction`、`source_language`、`target_language`、`input_dir`、`output_dir`、`style_rule_set`、`prompt_set`、`enabled`。

### 关系

隶属 Project，被 pipeline 和 UI 读取。

### 是否进入向量库

否。

### 是否需要版本管理

需要。

### 后续实现轮次

Round 05。

## SourceFile

### 用途

记录原文文件及扫描状态。

### 核心字段

`source_file_id`、`project_id`、`language_direction`、`path`、`file_name`、`file_type`、`size_bytes`、`checksum`、`scan_status`、`created_at`。

### 关系

生成 Chapter。

### 是否进入向量库

否，正文片段才进入。

### 是否需要版本管理

需要 checksum。

### 后续实现轮次

Round 06。

## Chapter

### 用途

描述章节、卷、番外、后记等结构。

### 核心字段

`chapter_id`、`project_id`、`source_file_id`、`chapter_index`、`title`、`chapter_type`、`start_offset`、`end_offset`、`status`、`warnings`。

### 关系

包含 Segment，关联 TranslationDraft 和 RefinedTranslation。

### 是否进入向量库

章节摘要可进入。

### 是否需要版本管理

需要。

### 后续实现轮次

Round 07。

## Paragraph

### 用途

描述章节内稳定段落，是 JSONL 中间态、审核定位和 exporter 回链的基础单位。

### 核心字段

`paragraph_id`、`project_id`、`language_direction`、`source_file_id`、`chapter_id`、`paragraph_index`、`source_text`、`source_text_hash`、`text_type`、`speaker`、`created_at`、`updated_at`。

### 关系

包含一个或多个 Segment，关联 ReviewIssue、TranslationMemoryEntry、Exporter 输出。

### 是否进入向量库

可选。MVP 以 Segment 或 Paragraph 的清洗文本进入检索。

### 是否需要版本管理

需要 `source_text_hash` 与重解析报告。

### 后续实现轮次

RM-03、RM-04、RM-05。

## Segment

### 用途

描述可翻译和可审核的最小文本片段。

### 核心字段

`segment_id`、`paragraph_id`、`project_id`、`language_direction`、`chapter_id`、`segment_index`、`source_text_ref`、`source_text_hash`、`speaker_character_id`、`text_type`、`start_offset`、`end_offset`、`status`、`prompt_version`、`provider_id`、`model_id`、`model_run_id`、`validation_errors`、`review_issues`、`locked`、`human_reviewed`。

### 关系

关联 ParagraphAlignment、TranslationMemoryEntry、EmbeddingRecord。

### 是否进入向量库

是，清洗后的可检索文本进入。

### 是否需要版本管理

需要。

### 后续实现轮次

Round 08。

## JSONLIntermediateRecord

### 用途

作为 parser、translation、validation、review、refinement 和 exporter 之间的可读中间态。

### 核心字段

见 `docs/stable_id_and_jsonl_design.md`。必须包含 `paragraph_id`、`segment_id`、`status`、`translation_draft`、`refined_translation`、`prompt_version`、知识资产版本、provider/model metadata、validation_errors 与 review_issues。

### 关系

连接 Segment、ModelRun、ReviewIssue、TranslationMemoryEntry 和 ExportedDocument。

### 是否进入向量库

否。可从其中抽取 source/target 文本生成 EmbeddingRecord。

### 是否需要版本管理

需要。schema 变化必须有迁移计划。

### 后续实现轮次

RM-04。

## ParagraphAlignment

### 用途

记录原文、初翻、润色之间的段落对齐。

### 核心字段

`alignment_id`、`project_id`、`chapter_id`、`segment_id`、`source_ref`、`draft_ref`、`refined_ref`、`alignment_status`、`risk_flags`、`updated_at`。

### 关系

关联 ReviewIssue 和 ExportJob。

### 是否进入向量库

对齐片段可进入。

### 是否需要版本管理

需要。

### 后续实现轮次

Round 25。

## Term

### 用途

术语库条目。

### 核心字段

`term_id`、`project_id`、`language_direction`、`source_text`、`target_text`、`term_type`、`status`、`confidence`、`first_seen_chapter`、`version`。

### 关系

关联 CharacterProfile、WorldBibleEntry、ReviewIssue。

### 是否进入向量库

术语上下文和例句可进入。

### 是否需要版本管理

需要。

### 后续实现轮次

Round 16。

## CharacterProfile

### 用途

记录角色姓名、别名、称呼和语气。

### 核心字段

`character_id`、`project_id`、`source_name`、`target_name_cn`、`target_name_jp`、`aliases`、`speaker_style`、`honorific_level`、`status`、`version`。

### 关系

关联 CharacterRelation、Segment、TranslationMemoryEntry。

### 是否进入向量库

角色发言样例可进入。

### 是否需要版本管理

需要。

### 后续实现轮次

Round 17。

## CharacterRelation

### 用途

记录角色间关系和互称规则。

### 核心字段

`relation_id`、`project_id`、`character_a`、`character_b`、`relationship_type`、`addressing_rule_a_to_b`、`addressing_rule_b_to_a`、`relationship_change_chapters`、`notes`。

### 关系

关联 CharacterProfile。

### 是否进入向量库

通常否。

### 是否需要版本管理

需要。

### 后续实现轮次

Round 17。

## WorldBibleEntry

### 用途

记录世界观设定。

### 核心字段

`world_entry_id`、`project_id`、`entry_type`、`source_name`、`target_name_cn`、`target_name_jp`、`description`、`source_evidence`、`status`、`version`。

### 关系

关联 Term、CharacterProfile、ReviewIssue。

### 是否进入向量库

证据片段可进入。

### 是否需要版本管理

需要。

### 后续实现轮次

Round 18。

## TranslationDraft

### 用途

记录初翻草稿。

### 核心字段

`draft_id`、`project_id`、`chapter_id`、`segment_id`、`source_ref`、`target_text_ref`、`model_run_id`、`quality_status`、`created_at`、`version`。

### 关系

关联 Segment、ModelRun、RefinedTranslation。

### 是否进入向量库

可进入。

### 是否需要版本管理

需要。

### 后续实现轮次

Round 20。

## RefinedTranslation

### 用途

记录润色稿。

### 核心字段

`refined_id`、`project_id`、`chapter_id`、`segment_id`、`draft_id`、`refined_text_ref`、`change_log`、`risk_notes`、`model_run_id`、`version`。

### 关系

关联 TranslationDraft、ReviewIssue、ExportJob。

### 是否进入向量库

可进入。

### 是否需要版本管理

需要。

### 后续实现轮次

Round 31。

## ReviewIssue

### 用途

记录质量审核问题。

### 核心字段

`issue_id`、`project_id`、`language_direction`、`chapter_id`、`segment_id`、`issue_type`、`severity`、`description`、`suggested_fix`、`status`。

### 关系

关联 Term、CharacterProfile、WorldBibleEntry、ParagraphAlignment。

### 是否进入向量库

通常否，典型案例可进入。

### 是否需要版本管理

需要状态历史。

### 后续实现轮次

Round 26 到 Round 28。

## TranslationMemoryEntry

### 用途

记录已翻译片段和可复用译法。

### 核心字段

`tm_id`、`project_id`、`language_direction`、`source_text`、`target_text`、`chapter_id`、`segment_id`、`quality_status`、`review_status`、`version`。

### 关系

关联 Segment、Term、CharacterProfile。

### 是否进入向量库

是。

### 是否需要版本管理

需要。

### 后续实现轮次

Round 24。

## EmbeddingRecord

### 用途

记录向量索引 metadata。

### 核心字段

`embedding_id`、`project_id`、`language_direction`、`text_type`、`chapter_id`、`segment_id`、`source_file`、`status`、`model`、`provider`、`version`。

JSON Schema（Round 48）：`data/schemas/vector_index_metadata.schema.json`。检查 CLI：`scripts/vector_db_inspect.py`。

### 关系

关联 Vector Store 外部索引和源对象。

### 是否进入向量库

是，它描述向量记录。

### 是否需要版本管理

需要模型和版本。

### 后续实现轮次

Round 13、Round 14。

## ModelRun

### 用途

记录模型调用。

### 核心字段

`model_run_id`、`project_id`、`language_direction`、`pipeline_stage`、`provider_id`、`model_name`、`status`、`started_at`、`finished_at`、`usage`。

### 关系

关联 TranslationDraft、RefinedTranslation、ReviewIssue。

### 是否进入向量库

否。

### 是否需要版本管理

需要审计记录。

### 后续实现轮次

Round 12、Round 34。

## ContextPack

### 用途

记录某次翻译或润色的上下文包。

### 核心字段

`context_pack_id`、`project_id`、`language_direction`、`chapter_id`、`segment_id`、`source_text_ref`、`glossary_refs`、`character_refs`、`world_refs`、`retrieval_refs`。

### 关系

关联 ModelRun。

### 是否进入向量库

通常否。

### 是否需要版本管理

需要。

### 后续实现轮次

Round 15。

## ExportJob

### 用途

记录导出任务。

### 核心字段

`export_job_id`、`project_id`、`language_direction`、`export_type`、`chapter_range`、`input_refs`、`output_path`、`status`、`created_at`、`completed_at`。

### 关系

关联 TranslationDraft、RefinedTranslation、ReviewIssue。

### 是否进入向量库

否。

### 是否需要版本管理

需要导出记录。

### 后续实现轮次

Round 35、Round 40。

## UserNote

### 用途

记录用户备注、人工审核说明和决策。

### 核心字段

`user_note_id`、`project_id`、`target_type`、`target_id`、`note_text`、`created_by`、`created_at`、`updated_at`、`status`。

### 关系

可关联任意对象。

### 是否进入向量库

重要审核说明可进入。

### 是否需要版本管理

需要。

### 后续实现轮次

Round 39。

## ProjectState

### 用途

记录项目整体和章节级状态。

### 核心字段

`project_state_id`、`project_id`、`chapter_states`、`pipeline_stage`、`pending_tasks`、`failed_tasks`、`budget_state`、`last_run_at`、`updated_at`。

### 关系

汇总 Project、Chapter、ModelRun、ReviewIssue。

### 是否进入向量库

否。

### 是否需要版本管理

需要 checkpoint。

### 后续实现轮次

Round 33。
