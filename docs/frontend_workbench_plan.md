# 前端工作台规划

前端目标不是炫酷 UI，而是让用户更容易完成上传原文、创建翻译项目、选择翻译方向、配置模型、查看章节、审核术语、审核人物表、审核世界观设定、启动初翻、查看翻译进度、对照原文和译文、查看冲突问题、启动二次润色、对比初翻和润色、导出结果。

## 页面清单

### Project Home

- 页面目的：查看项目列表和最近状态。
- 核心组件：项目卡片、状态摘要、方向标记、最近任务。
- 读取哪些数据：Project、ProjectState、ModelRun 摘要。
- 写入哪些数据：无，跳转为主。
- 是否需要人工确认：否。
- 与 pipeline 的关系：提供项目入口。
- 后续实现轮次：Round 36、Round 37。

### Create Project

- 页面目的：创建新小说项目。
- 核心组件：项目名称、语言方向、输入输出目录、预算策略。
- 读取哪些数据：默认 schema、provider 列表。
- 写入哪些数据：Project、DirectionConfig。
- 是否需要人工确认：是，创建前确认目录和版权提示。
- 与 pipeline 的关系：初始化 Project Management Layer。
- 后续实现轮次：Round 38、Round 39。

### Upload Source Files

- 页面目的：导入原文文件。
- 核心组件：文件选择、目录预览、格式提示、版权提醒。
- 读取哪些数据：project config。
- 写入哪些数据：SourceFile manifest。
- 是否需要人工确认：是。
- 与 pipeline 的关系：触发 file scanner。
- 后续实现轮次：Round 38。

### Direction Selection

- 页面目的：选择 `JP_TO_CN` 或 `CN_TO_JP`。
- 核心组件：方向切换、规则摘要、输出目录提示。
- 读取哪些数据：DirectionConfig、direction rules。
- 写入哪些数据：DirectionConfig。
- 是否需要人工确认：是，方向变更影响后续 pipeline。
- 与 pipeline 的关系：决定输入输出、Prompt 和审核规则。
- 后续实现轮次：Round 36。

### Model and Budget Settings

- 页面目的：配置不同阶段 provider 和预算。
- 核心组件：provider 选择、模型选择、预算上限、dry-run 开关。
- 读取哪些数据：ProviderConfig、ModelRun 统计。
- 写入哪些数据：ProviderConfig、BudgetConfig。
- 是否需要人工确认：是。
- 与 pipeline 的关系：控制模型调用。
- 后续实现轮次：Round 39。

### Source File Manager

- 页面目的：查看源文件 manifest 和扫描状态。
- 核心组件：文件表、章节识别状态、异常提示。
- 读取哪些数据：SourceFile、Chapter。
- 写入哪些数据：手动排序或忽略标记。
- 是否需要人工确认：排序变更需要确认。
- 与 pipeline 的关系：支持扫描和章节解析。
- 后续实现轮次：Round 38。

### Chapter Manager

- 页面目的：查看章节、状态和任务进度。
- 核心组件：章节列表、状态标签、批量选择、重试按钮。
- 读取哪些数据：Chapter、ProjectState。
- 写入哪些数据：任务状态、skip/retry 标记。
- 是否需要人工确认：批量操作需要确认。
- 与 pipeline 的关系：驱动批量初翻、润色和审核。
- 后续实现轮次：Round 38、Round 39。

### Glossary Editor

- 页面目的：审核、编辑、锁定术语。
- 核心组件：术语表、状态筛选、冲突视图、例句面板。
- 读取哪些数据：Term、ReviewIssue、TermUsageExamples。
- 写入哪些数据：Term 状态、译名、human_note、locked。
- 是否需要人工确认：锁定和废弃需要确认。
- 与 pipeline 的关系：影响初翻、润色和术语审核。
- 后续实现轮次：Round 39。

### Character Profile Editor

- 页面目的：维护角色姓名、称呼、语气和关系。
- 核心组件：角色列表、关系表、台词样例、称呼规则。
- 读取哪些数据：CharacterProfile、CharacterRelation、voice examples。
- 写入哪些数据：角色字段、关系字段、状态。
- 是否需要人工确认：姓名和称呼锁定需要确认。
- 与 pipeline 的关系：影响台词翻译、润色和语气审核。
- 后续实现轮次：Round 39。

### World Bible Editor

- 页面目的：维护世界观设定。
- 核心组件：设定列表、证据片段、剧透标记、关系图简表。
- 读取哪些数据：WorldBibleEntry、related terms、related characters。
- 写入哪些数据：设定描述、状态、spoiler、inferred。
- 是否需要人工确认：approved/locked 需要确认。
- 与 pipeline 的关系：影响 context pack 和世界观冲突检查。
- 后续实现轮次：Round 39。

### Batch Translation Monitor

- 页面目的：查看批量初翻进度。
- 核心组件：任务队列、进度条、失败列表、成本摘要。
- 读取哪些数据：ProjectState、ModelRun、TranslationDraft。
- 写入哪些数据：暂停、重试、跳过请求。
- 是否需要人工确认：真实 API 批量调用需要确认。
- 与 pipeline 的关系：监控 translation pipeline。
- 后续实现轮次：Round 38、Round 39。

### Side-by-side Translation Review

- 页面目的：原文译文对照审核。
- 核心组件：左右对照、segment 定位、issue 标记、术语高亮。
- 读取哪些数据：ParagraphAlignment、TranslationDraft、RefinedTranslation、ReviewIssue。
- 写入哪些数据：ReviewIssue、human_reviewed 状态。
- 是否需要人工确认：最终确认需要人工操作。
- 与 pipeline 的关系：连接审核和最终导出。
- 后续实现轮次：Round 38、Round 39。

### Refinement Comparison

- 页面目的：比较初翻和润色。
- 核心组件：diff、change log、风险标记、术语变化。
- 读取哪些数据：TranslationDraft、RefinedTranslation、change_log。
- 写入哪些数据：接受/拒绝润色、issue。
- 是否需要人工确认：接受润色需要确认。
- 与 pipeline 的关系：支持 refinement pipeline 审核。
- 后续实现轮次：Round 39。

### Issue Review Dashboard

- 页面目的：集中处理审核 issue。
- 核心组件：issue 列表、严重级别、筛选、解决状态。
- 读取哪些数据：ReviewIssue。
- 写入哪些数据：status、suggested_fix、resolved_at。
- 是否需要人工确认：关闭高严重级别 issue 需要确认。
- 与 pipeline 的关系：贯穿质量审核。
- 后续实现轮次：Round 39。

### Export Center

- 页面目的：导出译文、双语对照、报告和归档。
- 核心组件：格式选择、范围选择、版权提醒、导出按钮。
- 读取哪些数据：Project、TranslationDraft、RefinedTranslation、ReviewIssue。
- 写入哪些数据：ExportJob。
- 是否需要人工确认：导出最终稿需要确认。
- 与 pipeline 的关系：连接 Export Layer。
- 后续实现轮次：Round 40。

### Project Settings

- 页面目的：管理项目路径、方向、状态和元数据。
- 核心组件：配置表单、路径设置、项目状态、危险操作。
- 读取哪些数据：Project、DirectionConfig、ProjectState。
- 写入哪些数据：project config。
- 是否需要人工确认：危险操作需要确认。
- 与 pipeline 的关系：影响全局配置。
- 后续实现轮次：Round 39。

### Provider Settings

- 页面目的：管理 provider 配置。
- 核心组件：provider 列表、模型类型、环境变量名、能力标记。
- 读取哪些数据：ProviderConfig。
- 写入哪些数据：provider config，不写 API Key。
- 是否需要人工确认：启用真实 provider 需要确认。
- 与 pipeline 的关系：影响模型调用。
- 后续实现轮次：Round 39。

## 前端技术路线

- Phase 1: 静态 HTML / 简单本地页面。**← Round 57 MVP 已落地**（`frontend/` + `src/workbench/`）
- Phase 2: React / Vite 前端。
- Phase 3: 后端 API。（Workbench 已提供只读/小样本写 API，非完整 pipeline API）
- Phase 4: 本地 Web App。
- Phase 5: 多项目管理。

## Round 57 已实现页面（对照上文规划）

| 规划页面 | 当前对应 | 状态 |
|---|---|---|
| Project Home | `frontend/index.html` | MVP：项目列表、Quickstart、API 状态 |
| Side-by-side Review | `frontend/review.html` | MVP：审核、项目切换、状态持久化 |
| Quality Issues | `frontend/issues.html` | MVP：Issue 列表与数据源标注 |
| Export | `frontend/export.html` | MVP：manifest / runs 导出 |

未实现：Glossary、Character、Polish Diff、完整 Dashboard 等（见 `tests/ui/smoke.spec.ts` 显式 skip）。

---

> 以下各页「后续实现轮次」为 **历史路线标注**；实现状态以 `README.md` 与 `docs/architecture_overview.md`「当前已实现入口」为准。
