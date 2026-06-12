# Final State Implementation Roadmap

> 最终成品实现总路线图（2026-06-10 创建；2026-06-11 Codex 治理复核）
> 最高锚点：`docs/product_final_state_spec.md`（v1.1）
> 配套轮次任务：`docs/final_state_round_task_list.md`
> 阶段验收：`docs/phase_acceptance_criteria.md`
> 防跑偏：`docs/non_goals_and_guardrails.md`
> Done 定义：`docs/definition_of_done.md`
> 推进协议：`docs/next_agent_execution_protocol.md`
>
> 与既有路线的关系：
> - `docs/translation_recovery_3ch_roadmap.md`（D-MR / R-MR 3 章 micro round 体系）**继续有效**，作为本路线图 Phase A / Phase D 的"批量执行子路线"。
> - `docs/translation_recovery_20ch_roadmap.md` 维持 deprecated。
> - `docs/AGENT_ROADMAP.md`（AL-xxx Agent Layer 轮）的剩余项并入本路线图对应阶段，优先级以本文件为准。
> - 若任何旧文档与 `docs/product_final_state_spec.md` 冲突，以最终规格为准。

---

## 1. 当前仓库状态摘要（2026-06-11 实测）

| 维度 | 现状 | 证据 |
| --- | --- | --- |
| 全书章节 | 613 章（input_jp） | `translation_recovery_3ch_roadmap.md` |
| 初翻进度 | **523/613 连续完成（85.32%）**；下一轮 `D-MR-108`（524–526） | `local_scheduler_status.py --json` |
| Phase | Phase A in_progress；B/C/D/E 未开始 | scheduler status + FS 状态表 |
| Worker 状态 | 0 active / 0 orphan；throughput_gate WARN 但 blocks=[] | `check_orphan_workers.py` / `throughput_gate.py` 实测 |
| 初翻执行器 | `scripts/run_micro_round.py`（supervised、checkpoint、budget、--dry-run 完备） | `--help` 实测 |
| 批次规划 | `scripts/plan_translation_batches.py` 完备 | `--help` 实测 |
| 本地调度器 | **S1 已完成**：tick / status / launchd / pause / lock / stale heal / runbook 均存在 | `scripts/local_scheduler_*`、`src/scheduler/`、测试 |
| pause / lock 文件 | 协议与互斥测试已实现；当前 paused=false、lock=absent | scheduler status 实测 |
| configs/ 目录 | **S3 已完成**：五 YAML 模板、五 schema、迁移脚本与校验器存在 | `configs/`、`schemas/`、`validate_configs.py` |
| 术语资产 | CRUD、三格式导入导出、usage index、prompt 注入已实现 | `src/glossary/`、FS-013…016 测试 |
| 前端 | 现有 4 页 Workbench（index / review / issues / export）+ 本地 API；尚非最终 15 页 UI | 真实浏览器检查 |
| 前端实测 | 4 页关键请求均 HTTP 200，console 无 error/warn；首页仍为旧工作台信息架构 | 2026-06-11 Browser 检查 |
| 前端测试 | Playwright 已配置，当前 3 个 spec 文件 | `package.json`、`tests/ui/` |
| Python 测试 | 52 个 `test_*.py` 文件 | `tests/` |
| 门禁 | agent_gate WARNING（无 failed/blocked）；throughput_gate WARN（blocks=[]）；orphan CLEAN | 2026-06-11 实测 |
| 真实 API | OpenRouter / DeepSeek 走 model_router；cost guard 与 smoke 入口存在；本治理轮未调用 | 代码、测试、浏览器状态卡 |
| Git 安全 | `.env` 未跟踪；本轮补齐 `workspace/archived_runs/` ignore | `.gitignore` + `git check-ignore` |

## 2. 与最终规格的差距分析

| # | 规格要求（章节） | 现状 | 差距等级 |
| --- | --- | --- | --- |
| G1 | 本地调度系统（§9：tick / status / launchd / pause / lock） | **已完成 S1**；待 S5 接入 Web UI | 小（UI 接线） |
| G2 | Phase A 全书初翻（§12） | 523/613 连续完成，执行链路成熟 | 中（剩余 D-MR-108…137） |
| G3 | Phase B 一致性检查（§13：manifest / entity index / progressive disclosure） | 仅有 quality_review 雏形与 consistency 设计文档，无 manifest/entity index 工具链 | **大** |
| G4 | Phase C baseline lock（§14） | 无 | 中（工具量小，依赖 B） |
| G5 | Phase D 全书润色（§15） | refine_runner / refine_prompt_builder 存在，R-MR 队列未启动，over-refinement checker 缺失 | 大 |
| G6 | Phase E 终检 + production_candidate（§16–17） | 无 | 大 |
| G7 | Web UI 15 页信息架构（§7） | 4 页 Workbench 可运行；无最终 Dashboard / 设置 / 控制台 / 资产管理 / 修改稿同步 | **极大** |
| G8 | UI 视觉系统（§8：统一状态标签 / 色彩 / 反馈 / 二次确认） | 部分 Dark theme CSS 变量，未系统化 | 大 |
| G9 | 术语库系统（§7.8：CRUD / 导入导出 / locked / approved） | 内核已完成；UI 未开始 | 中 |
| G10 | 角色 / 世界观 / 翻译记忆管理（§7.9–7.11） | configs 模板已存在；专用 store / UI 未完成 | 中 |
| G11 | 用户修改稿同步（§19：对齐 / diff / sync plan / 同步执行） | 完全缺失 | **大** |
| G12 | configs/ 目录与五个 YAML（§10） | **已完成 S3** | 已关闭 |
| G13 | 导出系统（§7.14：MD / 双语 / TXT / EPUB / package） | exporter.py 支持部分 MD 导出 | 中 |
| G14 | 状态标签统一（§8.3） | 各处叫法不一 | 中 |

**结论**：执行内核、S1 调度器和 S3 术语资产层已成熟；当前主缺口是"Phase A 剩余批量 + Phase B-E 工具链 + Web UI 全量 + 用户修改稿同步"。后续不再回做 S1/S3，按 `D-MR-083` 继续 S2，并可与 S4 UI 基座交错推进。

## 3. 阶段拆分总览

| Stage | 名称 | 轮次 | 真实 API | Web UI | 浏览器测试 | 依赖 |
| --- | --- | --- | --- | --- | --- | --- |
| S0 | 治理与基线对齐 | FS-000（本轮） | 否 | 否 | 否 | — |
| S1 | 本地调度器主线 | FS-001…FS-007 | 仅 smoke | 否 | 否 | S0 |
| S2 | Phase A 初翻完成 | FS-008…FS-010（+ D-MR-008…137 批量执行） | **是** | 否 | 否 | S1 |
| S3 | configs 资产层与术语库内核 | FS-011…FS-016 | 否 | 否 | 否 | S0（可与 S2 并行） |
| S4 | Web UI 基座与设计系统 | FS-017…FS-022 | 否 | **是** | **是** | S0（可与 S2 并行） |
| S5 | Web UI MVP（Dashboard / 控制台 / 章节 / 术语 / 报告 / 导出入口） | FS-023…FS-030 | 否 | **是** | **是** | S1、S3、S4 |
| S6 | Phase B 一致性检查工具链 | FS-031…FS-037 | Level 4 小规模 | 否 | 否 | S2 |
| S7 | Phase C baseline lock | FS-038…FS-039 | 否 | 否 | 否 | S6 |
| S8 | Phase D 润色工具链与 R-MR 推进 | FS-040…FS-045（+ R-MR 批量执行） | **是** | 否 | 否 | S7 |
| S9 | Phase E 终检与 production_candidate | FS-046…FS-050 | Level 5 小规模 | 否 | 否 | S8 |
| S10 | 角色 / 世界观 / 翻译记忆 UI | FS-051…FS-053 | 否 | **是** | **是** | S5 |
| S11 | 译文对照阅读页 | FS-054…FS-056 | 否 | **是** | **是** | S5 |
| S12 | 用户修改稿同步主线 | FS-057…FS-062 | 局部重译小规模 | **是** | **是** | S9、S11 |
| S13 | 导出系统完整化 | FS-063…FS-064 | 否 | **是** | **是** | S9 |
| S14 | Web UI Final 打磨与全量用户视角测试 | FS-065…FS-068 | 否 | **是** | **是** | S5–S13 |
| S15 | 端到端 DoD 验收 | FS-069…FS-070 | 验证性 | **是** | **是** | 全部 |

当前状态：S0、S1、S3 completed；S2 in_progress（523/613）；S4–S15 not_started。首个可继续的生产任务是 D-MR-108；首个可并行工程任务是 FS-017。

> 并行建议：S2（真实 API 初翻批量执行）与 S3 / S4（资产层、UI 基座）可交替推进——初翻轮消耗 API 与时间，工程轮消耗 Agent 实现能力，二者交错可最大化吞吐。

## 4. 各阶段详情

### S1 本地调度器主线（FS-001…FS-007）

- **状态**：completed（2026-06-11）。
- **目标**：实现规格 §9 全部组件，使初翻可由 launchd 周期 tick 推进，不再依赖 Cursor 前台。
- **输入**：`run_micro_round.py`、`throughput_gate.py`、`check_orphan_workers.py`、`workspace/control/`。
- **输出**：`scripts/local_scheduler_tick.py`、`scripts/local_scheduler_status.py`、`scripts/local_scheduler_launchd.sh`、`scripts/launchd/com.lightnovel.translation.scheduler.plist.template`、`docs/local_scheduler_runbook.md`、pause / lock 文件协议、对应 pytest。
- **完成标准**：`python3 scripts/local_scheduler_status.py --json` 输出规格 §9.2 全部字段；`local_scheduler_tick.py --dry-run` 干净退出且不留 orphan；pause file 存在时拒绝启动真实 API；lock 互斥与 stale 清理有测试覆盖。
- **可验证命令**：`python3 scripts/local_scheduler_status.py --json`、`python3 scripts/local_scheduler_tick.py --dry-run`、`npm run test:py`。
- **风险**：launchd 环境变量与 PATH 差异；tick 内 worker 超时处理。
- **真实 API**：仅最后一轮做 1 次 supervised 真实 tick smoke（≤3 章）。

### S2 Phase A 初翻完成（FS-008…FS-010 + D-MR 批量）

- **状态**：in_progress；连续完成 ch1–523。
- **目标**：用调度器 + supervised micro round 跑完 D-MR-083…D-MR-137（ch449–613），达到规格 §12.2 完成标准。
- **输入**：S1 调度器、`translation_recovery_3ch_task_list.md` 的 D-MR 队列。
- **输出**：全书 draft、`workspace/round_reports/D-MR-*/`、draft export、Phase A completion report。
- **完成标准**：见 `docs/phase_acceptance_criteria.md` Phase A 节。
- **可验证命令**：`python3 scripts/throughput_gate.py --json`、`python3 scripts/check_orphan_workers.py --json`。
- **风险**：API 成本（按现行单价估算全书剩余约 \$0.6–1.5）；失败 segment 重试堆积。
- **真实 API**：是（生产模型 `deepseek/deepseek-v4-pro`，遵守 cost guard 与 §21.3 模型切换限制）。

### S3 configs 资产层与术语库内核（FS-011…FS-016）

- **状态**：completed（2026-06-11）。
- **目标**：建立规格 §10 的 `configs/` 五 YAML 与术语库 CRUD 内核（无 UI）。
- **输出**：`configs/glossary.yaml`、`character_profile.yaml`、`style_profile.yaml`、`world_bible.yaml`、`model_profiles.yaml`（模板 + 从现有资产迁移）；`src/glossary/` CRUD 模块；CSV / YAML / JSON 导入导出；locked / approved_by_user / conflict 字段；term usage index；pytest。
- **完成标准**：glossary CRUD 全字段（规格 §7.8）可用且有测试；导入导出 roundtrip 测试通过；初翻 prompt builder 能消费 configs 资产。
- **风险**：现有 translation_memory 资产迁移时丢字段；YAML 含真实译名是否提交需用户确认（默认不提交真实内容，提交脱敏模板）。

### S4 Web UI 基座与设计系统（FS-017…FS-022）

- **目标**：确定 UI 架构（延续静态 HTML + `frontend/assets/` + workbench server，扩展为多页应用），建立规格 §8 的设计系统。
- **输出**：`frontend/assets/design-system.css`（色彩 / 状态标签 / 卡片 / 表格 / 按钮 / toast / 确认对话框组件）；统一布局壳（侧边导航 + 顶栏）；状态标签字典（§8.3 的 11 个状态）与前后端共享常量；空状态 / loading / 错误提示规范；Stitch 设计输入流程（导出物入 `docs/design/stitch/`）。
- **完成标准**：设计系统页（styleguide.html）经 Playwright 截图检查；所有新页面复用同一布局壳；状态标签前后端来源唯一。
- **浏览器测试**：必须（before / after 截图入 `artifacts/`）。

### S5 Web UI MVP（FS-023…FS-030）

- **目标**：实现规格 §12（治理 Prompt）要求的 MVP 八项：Dashboard、项目设置、API / 模型设置、Pipeline 控制台、章节状态、术语库基本 CRUD、报告查看、导出入口。
- **输入**：S1 调度器 status JSON、S3 glossary 内核、S4 设计系统、`src/workbench/server.py`。
- **输出**：每页一轮或两轮，含后端 API 扩展 + 页面 + Playwright 用户视角测试。
- **完成标准**：见 `docs/phase_acceptance_criteria.md` Web UI MVP 节；每页中文、复用设计系统、危险操作二次确认、`npm run test:ui` 通过。
- **浏览器测试**：每轮必须。

### S6 Phase B 一致性检查工具链（FS-031…FS-037）

- **目标**：实现规格 §13 的 progressive disclosure 六层检查。
- **输出**：`scripts/build_chapter_manifest.py`、`scripts/build_segment_index.py`、`scripts/build_entity_index.py`、glossary conflict audit、character / place / skill / item audit、source residual audit、local fix plan 生成器、selective segment expansion、local retranslation plan、full draft consistency report。
- **完成标准**：blocking conflicts 统计可复现；Level 0–3 全规则化（无 API）；Level 4 模型调用有 budget 与审计记录。
- **真实 API**：仅 Level 4 小规模（按 fix plan 限定 segment 数）。

### S7 Phase C baseline lock（FS-038…FS-039）

- **目标**：规格 §14。生成 `draft_full_baseline/`、metadata、go decision，并实现 baseline 只读保护。
- **完成标准**：baseline 目录写保护（脚本拒绝写入 + 测试）；go decision 文档生成且引用 Phase B 报告；handoff 文档指向 Phase D。

### S8 Phase D 润色工具链与 R-MR 推进（FS-040…FS-045 + R-MR 批量）

- **目标**：规格 §15。R-MR 队列、diff / change_log、over-refinement checker、terminology preservation checker、character voice checker、refined export。
- **真实 API**：是（refinement_primary；切换更强模型需用户确认）。
- **完成标准**：见 `phase_acceptance_criteria.md` Phase D 节。

### S9 Phase E 终检与 production_candidate（FS-046…FS-050）

- **目标**：规格 §16–17。final review index、diff ratio audit、over-refinement candidate selection、semantic drift review、local fix plan、production_candidate 生成与 go decision。
- **完成标准**：`production_candidate/` + `production_candidate_metadata.json` + `production_candidate_go_decision.md` 生成；不标记 human_approved_final。

### S10–S13 资产 UI、对照页、用户同步、导出

- S10：角色设定页、世界观页、翻译记忆页（规格 §7.9–7.11）。
- S11：多栏对照阅读页（规格 §7.7，6 种模式、段落对齐、标记 / 备注）。
- S12：用户修改稿上传 → segment 对齐 → diff → sync plan → 用户确认 → 同步执行（规格 §19，禁止直接覆盖 baseline / production_candidate）。
- S13：导出页完整化（双语 MD / TXT / EPUB / package，规格 §7.14）。

### S14 Web UI Final 打磨（FS-065…FS-068）

- **目标**：规格 §6–8 全量达标：15 页齐全、视觉统一、响应式、可访问性基础、全量 Playwright 用户视角测试套件。

### S15 端到端 DoD 验收（FS-069…FS-070）

- **目标**：逐条核对规格 §25 的 27 项 Definition of Done，生成最终验收报告。

## 5. 推进顺序与路径

### 最小可用路径（MVP path）

S0 → S1（调度器）→ S2（初翻跑完）→ S3+S4+S5（资产层 + UI MVP，与 S2 交替）→ S6 → S7 → S8 → S9 → 最小导出。
此路径终点：production_candidate 可生成，Web UI MVP 八页可用。

### 完整最终形态路径（Final path）

最小路径 + S10 + S11 + S12 + S13 + S14 + S15。
此路径终点：规格 §25 全部 27 项满足。

### 推荐执行节奏

1. 从 `D-MR-083` 继续 S2；每个 Milestone Block 后执行 FS-009 健康检查。
2. S2 初翻批量轮与 S4 工程轮**交替**：每完成若干 D-MR 即插入 1–2 个 UI 基座轮。
3. UI 每轮只做一个页面切片（遵守 `.cursor/rules/cursor-browser-ui.mdc`）。
4. Phase B–E 工具链在 Phase A 接近完成时提前开工（规则层 Level 0–3 不依赖全书完成）。

## 6. 全局风险

| 风险 | 等级 | 缓解 |
| --- | --- | --- |
| launchd 后台 tick 产生 orphan worker | P0 | tick 末尾强制 `check_orphan_workers`；lock 协议；supervised 模式 |
| 真实 API 成本失控 | P0 | cost guard、`MAX_TEST_COST_USD`、每 tick 单 MR、Dashboard 成本显示 |
| 真实译文 / 原文误提交 | P0 | agent_gate 已覆盖 input/output ignore；commit 前 `git diff` 三连 |
| UI 范围膨胀拖垮主线 | P1 | 每轮一个切片；MVP 八页优先；视觉打磨后置到 S14 |
| Phase B 全文硬扫导致上下文膨胀 | P1 | progressive disclosure 强制分层；Level 4 才允许模型 |
| 用户修改稿同步覆盖 baseline | P0 | 同步只写 TM / glossary / fix plan / revised output，禁写 baseline（代码层拒绝 + 测试） |
| 旧 Roadmap 与新路线冲突 | P2 | 本文件 + 最终规格优先；冲突时在轮次报告标注 |
| 叙述性进度快照落后于运行状态 | P1 | 每轮以 `local_scheduler_status.py --json` 为真值并同步 3ch 子路线、FS 状态表与 latest report |
