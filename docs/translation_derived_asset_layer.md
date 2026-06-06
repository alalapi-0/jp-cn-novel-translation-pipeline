# Translation-Derived Asset Extraction Layer

## 定位

在现有翻译流水线 **旁路** 新增一层「翻译副产物资产抽象」能力。该层 **只读** `segments.json`（及可选元数据），将章节/段落信号提炼为可复用的 **抽象模式**，不修改 `draft/`、`refined/`、`final/`、`checkpoint`、`stage_state` 或原文/译文文件。

## 插入点（审计结论）

| 流水线阶段 | 可读取产物 | 是否可写入 | 推荐插入时机 |
|---|---|---|---|
| parse_and_segment | `segments.json`（source） | 否 | 不推荐（信息不足） |
| draft_translation | `segments.json`（+draft_text） | 否 | 可选（初稿后） |
| refinement | `segments.json`（+refined_text） | 否 | **推荐**（信息最全） |
| quality_review | review issues | 否 | 可选（质量信号） |
| export | export 产物 | 否 | 不推荐 |

**MVP 默认读取：** `workspace/runs/<source_run_id>/segments.json`

**MVP 默认输出：** `workspace/asset_extraction_runs/<run_id>/`

公共库 `assets_extracted/` 仅在 safety 通过且 `write_to_public_asset_library=true` 时写入。

## 四大资产类别

1. **Narrative Assets** — 叙事结构模式（钩子、伏笔、信息释放），非情节复述
2. **Game Design Assets** — 游戏化机制抽象（等级、技能、成就、VR 世界等）
3. **Naming Pattern Assets** — 命名/标注 **结构模式**（片假名专名、对话引号、【标注】），非原作独创词
4. **Chapter Structure Assets** — 章节功能、节奏、开篇/收束钩子类型

## Schema

### AssetExtractionRun (`extraction_metadata.json`)

```json
{
  "run_id": "asset_extract_20260606_120000_run_xxx",
  "source_run_id": "run_20260602_203645_draft_stage_b_50ch",
  "mode": "rule-based",
  "chapters_processed": ["ch-001", "ch-002"],
  "created_at": "2026-06-06T12:00:00+00:00",
  "config_snapshot": {
    "enabled": false,
    "default_mode": "rule-based",
    "allow_real_api": false,
    "max_chapters": 5,
    "max_segments": 50,
    "max_requests": 5,
    "write_to_public_asset_library": false
  },
  "stats": {
    "chapters_processed": 2,
    "segments_processed": 6,
    "assets_total": 8,
    "assets_safe": 7,
    "assets_blocked": 1,
    "api_calls": 0
  }
}
```

### 共有资产字段（Narrative / GameDesign / NamingPattern / ChapterStructure）

| 字段 | 类型 | 说明 |
|---|---|---|
| `asset_id` | string | 唯一 ID |
| `asset_type` | enum | `narrative` / `game_design` / `naming_pattern` / `chapter_structure` |
| `abstraction_level` | enum | `high` / `medium` / `low` |
| `copyright_safety_level` | enum | `safe` / `caution` / `unsafe` |
| `reuse_guidance` | string | 复用边界说明 |
| `pattern_description` | string | 抽象模式描述（短文本） |
| `generated_examples` | string[] | **合成示例**，不得摘自原文 |
| `source_chapter_ids` | string[] | 来源章节 ID（非原文） |
| `tags` | string[] | 标签 |
| `safety_notes` | string[] | 可选安全备注 |

### NarrativeAsset 扩展

- `narrative_role`: 如 `hook_or_foreshadow`
- `structural_pattern`: 如 `dialogue_hook`, `foreshadowing`

### GameDesignAsset 扩展

- `mechanism_category`: 如 `status_system`, `skill_acquisition`
- `abstraction_scope`: 如 `cross_title_mechanism`

### NamingPatternAsset 扩展

- `pattern_kind`: 如 `katakana_proper_noun`, `bracket_annotation`
- `linguistic_markers`: 语言学标记说明

### ChapterStructureAsset 扩展

- `chapter_function`: 如 `setup_and_hook`, `information_release`
- `hook_type`: 如 `dialogue_led`, `layered_reveal`
- `pacing_notes`: 节奏说明

## 模块结构

```
src/assets/
  config.py
  types.py
  loader.py
  rule_based_extractor.py
  model_assisted_extractor.py
  asset_safety_validator.py
  runner.py
scripts/extract_translation_assets.py
```

## 模式

| 模式 | API | 限制 |
|---|---|---|
| `rule-based` | 不调用 | 默认；关键词/结构启发式 |
| `model-assisted` | 可选 | `max_chapters≤5`, `max_segments≤50`, `max_requests≤5`；需 Key + 显式授权 |

## 参考

- `docs/asset_abstraction_safety_rules.md`
- `docs/asset_extraction_workflow.md`
- `prompts/asset_extraction_prompt_v0.1.0.md`
