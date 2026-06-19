# Product Final State Specification

项目名称：长篇小说中日互译生产流水线
仓库路径：`/Users/alalapi/PycharmProjects/light_novel`
文档类型：最终成品规格 / 终局锚点 / 后续 Agent 防跑偏基准
版本：v2.1（2026-06-19 用户决策后修订）
优先级：高于普通 Roadmap、Round Report、临时 Prompt、单轮执行指令

---

## 1. v2.1 核心变更

2026-06-18 至 2026-06-19 用户明确决定：

1. **取消润色主流程**：不再需要 Phase D refinement、R-MR、refined candidate、over-refinement checker 作为生产必经路线。
2. **取消 production_candidate 主流程**：自动化生产终点不再是 `production_candidate/`，而是通过一致性校对后的唯一最终译文文件。
3. **生产翻译可走两条合法执行路径**：
   - 外部真实 API：通过 provider / model router / cost guard 执行。
   - Agent 自身额度：由当前 Agent 在受控章节范围内直接完成翻译，写入同一中间态与报告结构。
4. **最终译文只保留一份**：默认唯一交付文件为 `output_cn/translated/full_volume_cn.md`，其他分章、双语、Workbench 导出都只是可再生成的辅助产物。
5. **baseline 正文不再是当前交付面**：旧 `draft_full_baseline/` 容易被误认为第二份译文，且会保留旧译名错误。当前自动化终点不再要求生成或保留 baseline 正文；一致性修复应直接作用于 canonical segments 并重新导出 singleton final。

任何旧文档、旧报告、旧脚本若仍要求 `refinement`、`R-MR`、`production_candidate` 或 `draft_full_baseline/` 正文作为当前主线，均视为 legacy，不得覆盖本文件。

---

## 2. 北极星目标

本项目最终是一个**本地可持续运行、可通过 Web UI 操作的长篇小说中日互译生产流水线**。

它允许用户在本地导入长篇小说原文，通过真实 API 或 Agent 自身额度完成：

1. 全书翻译；
2. 一致性检查；
3. canonical segments 修正闭环；
4. 必要的局部修正 / 局部重译；
5. 唯一最终译文导出；
6. 用户人工审阅与修改同步。

最终用户不应该被迫长期盯着 Cursor 聊天窗口，也不应该通过复杂命令手动推进每个阶段。最终形态应是：

```text
用户启动本地 Web 项目
→ 在浏览器中配置项目、语言方向、执行方式和预算
→ 导入小说原文
→ 配置术语库 / 角色设定 / 翻译风格
→ 选择外部 API 翻译或 Agent 额度翻译
→ 点击启动流水线
→ Web UI 显示进度、成本、错误、报告
→ 用户可以暂停 / 恢复 / 局部重跑
→ 翻译完成后自动一致性检查
→ 一致性问题闭环后直接更新 canonical segments
→ 导出唯一最终译文 full_volume_cn.md
→ 用户在 Web UI 中审阅、修改、上传人工修改稿
→ 系统根据用户修改同步术语库、翻译记忆和全书一致性
```

---

## 3. 最终成品一句话定义

```text
一个本地 Web UI 驱动的长篇小说中日互译生产系统。
它通过本地调度器、真实 API 或 Agent 自身额度，将原文解析为稳定中间态，完成翻译、一致性检查、canonical segments 修正和唯一最终译文导出，并支持用户通过 Web UI 管理术语、角色、配置、进度、报告和人工修改同步。
```

---

## 4. 项目最终边界

### 4.1 本项目最终是什么

本项目最终是：

* 本地运行的长篇小说翻译生产流水线；
* 支持中日互译的结构化翻译系统；
* 支持真实 API 和 Agent 额度两种翻译执行方式；
* 支持 Web UI 操作的本地生产工具；
* 支持术语库、角色设定、世界观设定、翻译记忆的管理系统；
* 支持 checkpoint、断点续跑、暂停、恢复、局部重跑的任务系统；
* 支持用户人工修改稿上传和全书同步修正的译文管理系统；
* 支持唯一最终译文导出与人工最终确认。

### 4.2 本项目当前不是

当前阶段不是：

* 公开 SaaS；
* 多用户协同平台；
* 云端托管翻译平台；
* 自动投稿或自动发布系统；
* 完整版权管理系统；
* 商业发行系统；
* 多模型长期排行榜；
* 漫画 OCR 翻译系统；
* 图像翻译系统；
* TTS 或有声书系统。

这些可以作为未来方向，但不能干扰当前主线。

---

## 5. 标准生产流程

最终流程分为三个主阶段和一个人工可选阶段：

```text
Phase A：Translation
→ Phase B：Consistency Audit
→ Phase C：Singleton Final Export
→ Optional：Human Approved Final
```

明确废弃为主线：

```text
Phase D：Refinement
R-MR
Phase E：Refinement Final Review
production_candidate
```

旧 refine 代码、旧 R-MR 报告、旧 production_candidate 文档只能作为历史参考或 legacy 工具，不得作为下一轮任务来源。

---

## 6. 两种翻译执行方式

### 6.1 外部真实 API 模式

适用于需要批量、可续跑、可记录成本的生产翻译。

必须满足：

* 用户明确允许真实 API；
* API Key 只从环境变量或安全设置读取，不打印、不提交；
* cost guard 生效；
* 每轮有 max-api-calls / max-segments / wall-time 限制；
* pause file 存在时不得启动真实 API；
* no active worker / no orphan worker；
* 输出写入统一 segment 中间态。

### 6.2 Agent 额度模式

适用于用户希望直接使用当前 Agent 能力完成翻译，而不是调用外部付费 API。

必须满足：

* 用户明确选择或允许 Agent 额度模式；
* 每轮只处理有限章节 / segment，避免上下文膨胀；
* 输出必须写入与 API 模式相同的结构化中间态；
* 必须保留 chapter_id / paragraph_id / segment_id；
* 不得绕过术语库、角色设定、一致性检查和最终单例导出；
* 必须在 round report / latest-agent-report 中记录本轮使用了 Agent 额度模式；
* 不得把无法验证的聊天输出直接当最终译文，必须进入一致性校对和导出流程。

两种执行方式的产物必须同构。后续一致性检查、canonical segments 修正、导出不应关心译文来自外部 API 还是 Agent。

---

## 7. 系统架构

最终系统由五层组成：

```text
Web UI 层
→ 本地 API / Backend 层
→ Pipeline Orchestrator 层
→ Translation Worker 层
→ Storage / Workspace / Index 层
```

### 7.1 Web UI 层

用户应能通过浏览器完成：

* 创建项目；
* 导入原文；
* 配置 API；
* 选择 API 模式或 Agent 额度模式；
* 配置模型和预算；
* 管理术语库；
* 管理角色设定；
* 管理世界观资料；
* 启动翻译；
* 查看进度；
* 暂停 / 恢复；
* 查看错误；
* 查看成本或 Agent 使用记录；
* 查看章节状态；
* 查看译文；
* 对比原文 / 译文 / 用户修改稿；
* 上传人工修改版本；
* 将人工修改同步到术语库、翻译记忆和全书一致性修正；
* 导出唯一最终译文。

UI 必须中文优先，不得简陋到只像调试页面。

### 7.2 Backend 层

Backend 负责：

* 读取项目配置；
* 暴露本地 API；
* 管理任务状态；
* 调用 pipeline 脚本；
* 读写 workspace；
* 读取报告；
* 提供 Web UI 数据；
* 管理暂停 / 恢复 / 重跑 / 导出请求。

### 7.3 Pipeline Orchestrator 层

Pipeline Orchestrator 负责：

* 判断当前 Phase；
* 判断下一任务；
* 调用翻译 micro round；
* 调用一致性检查；
* 调用 singleton final export；
* 管理 checkpoint；
* 防止并发 worker；
* 维护 lock；
* 生成报告；
* 处理失败重试；
* 保证不会产生孤儿 worker。

### 7.4 Worker 层

Worker 负责：

* 调用真实 API，或接收 Agent 额度模式生成的结构化译文；
* 执行翻译；
* 执行局部重译；
* 保存 batch 结果；
* 保存 checkpoint；
* 更新 run_progress；
* 输出 compact progress；
* 按 token budget 分批；
* 不读取全书上下文；
* 不提交真实正文。

### 7.5 Storage 层

Storage 负责保存：

* 原文解析结果；
* segment 中间态；
* draft / translated text；
* singleton final export manifest；
* glossary；
* character profile；
* world bible；
* translation memory；
* consistency audit；
* round reports；
* scheduler 状态；
* logs；
* lock；
* pause file。

---

## 8. Web UI 信息架构

最终 Web UI 至少包含：

1. Dashboard 总览页；
2. 项目设置页；
3. API / Agent 执行方式设置页；
4. 原文导入页；
5. Pipeline 控制台；
6. 章节管理页；
7. 原文 / 译文 / 用户修改稿对照页；
8. 术语库页面；
9. 角色设定页面；
10. 世界观 / 设定页面；
11. 翻译记忆页面；
12. 用户修改稿上传页面；
13. 报告页面；
14. 导出页面；
15. 设置与安全页面。

Dashboard 必须显示：

* 当前 Phase；
* 当前任务；
* 当前 round；
* 当前章节范围；
* 全书章节总数；
* 翻译完成进度；
* 一致性检查状态；
* final translation 状态；
* 当前执行方式（API / Agent quota / dry-run / mock）；
* 当前模型；
* 本轮 API 调用数或 Agent 使用记录；
* 累计成本；
* active worker 状态；
* orphan worker 状态；
* scheduler 状态；
* 最近错误；
* 下一步任务。

Pipeline 控制台必须支持：

* 启动翻译；
* 暂停 scheduler；
* 恢复 scheduler；
* 手动运行一次 tick；
* 手动执行下一个 translation micro round；
* 手动执行一致性检查；
* 手动导出唯一最终译文；
* 停止当前 worker；
* 查看 active worker；
* 查看 orphan worker；
* 查看 lock；
* 清理 stale lock；
* 查看当前 checkpoint。

危险操作必须二次确认。

---

## 9. 本地调度系统最终要求

最终本地调度系统必须包含：

```text
scripts/local_scheduler_tick.py
scripts/local_scheduler_status.py
scripts/local_scheduler_launchd.sh
scripts/launchd/com.lightnovel.translation.scheduler.plist.template
docs/local_scheduler_runbook.md
```

### 9.1 local_scheduler_tick.py

每次运行只执行一个主任务：

* 下一个 translation micro round；
* 下一个一致性检查子任务；
* singleton final export。

每次运行结束必须：

* 保存 checkpoint；
* 保存 progress；
* 保存 report；
* 确认 no orphan worker；
* 干净退出。

### 9.2 local_scheduler_status.py

必须输出：

* current_phase；
* next_task；
* next_round_id；
* next_chapter_range；
* active_worker_count；
* orphan_worker_count；
* scheduler_lock_status；
* paused；
* last_successful_tick；
* last_blocked_reason；
* draft_progress；
* final_translation_progress；
* safe_to_run。

可以保留 legacy compatibility 字段，但不得用 legacy 字段驱动主流程。

### 9.3 pause file

如果存在：

```text
workspace/control/scheduler_paused.json
```

且内容包含：

```json
{
  "paused": true
}
```

则调度器不得启动真实 API，也不得启动 Agent 额度翻译任务。

### 9.4 lock file

本地调度器必须使用互斥锁：

```text
workspace/control/scheduler_running.lock
```

如果 lock 存在且 pid 活跃，新的 tick 必须退出。

如果 lock stale，可以安全清理。

---

## 10. 数据与目录最终要求

最终目录结构应至少包含：

```text
input_jp/
input_zh/

workspace/
  control/
  logs/
  runs/
  round_reports/
  consistency_audit/
  diagnostics/
  indexes/
  translation_memory/

configs/
  glossary.yaml
  character_profile.yaml
  style_profile.yaml
  world_bible.yaml
  model_profiles.yaml

output_cn/
  translated/
    full_volume_cn.md
  final_export_manifest.json

docs/
  product_final_state_spec.md
  definition_of_done.md
  phase_acceptance_criteria.md
  non_goals_and_guardrails.md
  local_scheduler_runbook.md
  translation_production_protocol.md
  translation_consistency_protocol.md
```

真实原文和真实译文默认不提交 Git。

不再把以下目录作为最终主线产物：

```text
output_refined/
refined_full_candidate/
production_candidate/
```

---

## 11. Phase A：全书翻译

### 11.1 目标

生成完整、忠实、结构稳定、可审计的全书译文。

优先保证：

* 完整；
* 忠实；
* 不漏段；
* 不错位；
* 术语基本一致；
* 人名基本一致；
* checkpoint 完整；
* 可重跑；
* 可导出；
* 可进入一致性检查。

### 11.2 完成标准

Phase A 完成条件：

* 全书所有章节已完成 translation；
* 所有 segment status 为 completed；
* failed segment 数为 0；
* blocking validation_failed 数为 0；
* 无章节错位；
* 无漏段；
* checkpoint 完整；
* round reports 完整；
* no active worker；
* no orphan worker；
* draft / translation 输出可导出或已导出。

---

## 12. Phase B：一致性检查

### 12.1 目标

检查全书译文的一致性。

重点关注：

* 人名；
* 角色名；
* 技能名；
* 地名；
* 组织名；
* 道具名；
* 称号；
* 特有名词；
* 同源多译；
* 同译多源；
* 高频未收录术语；
* 源语言残留；
* 漏段；
* 章节错位；
* 格式异常。

### 12.2 检查方式

必须采用 progressive disclosure，不得全文硬扫。

```text
Level 0：metadata / manifest
Level 1：entity index / glossary / character index
Level 2：冲突统计
Level 3：只展开冲突 segment
Level 4：规则无法判断时才调用模型或 Agent 判断
Level 5：局部重译或局部修正
```

### 12.3 完成标准

Phase B 完成条件：

* chapter manifest 已构建；
* segment index 已构建；
* entity index 已构建；
* glossary 冲突已统计；
* blocking conflicts 为 0；
* 必要的局部修正或局部重译已完成；
* 一致性报告完整；
* 可以进入 singleton final export。

---

## 13. Phase C：唯一最终译文导出

### 13.1 目标

将通过一致性检查的 canonical segments 直接导出为唯一最终译文。

`output_cn/translated/full_volume_cn.md` 是默认且唯一的自动化交付译文。旧 `draft_full_baseline/` 属于 legacy 审计机制，不得作为当前交付正文、调度前置条件或后续修复输入。

### 13.2 输出

必须生成：

```text
output_cn/translated/full_volume_cn.md
output_cn/final_export_manifest.json
reports/final_translation_singleton_check.json
```

### 13.3 完成标准

Phase C 完成条件：

* Phase A 完成；
* Phase B 完成；
* blocking conflicts 为 0；
* failed / validation_failed 为 0；
* 无漏段；
* 无章节错位；
* final export manifest 指向唯一最终译文；
* singleton checker PASS；
* no active worker；
* no orphan worker。

---

## 14. human_approved_final 定义

`human_approved_final` 只能由用户明确确认后生成。

任何 Agent 不得自动标记 `human_approved_final`。

`full_volume_cn.md` 可以是自动化交付译文，但不等于用户已逐章审阅，也不等于可以公开发布。

---

## 15. 用户修改稿同步机制

最终系统必须支持用户上传人工修改版本。

用户可以上传：

* 单章人工修改稿；
* 多章人工修改稿；
* 全书人工修改稿；
* 修改后的术语库；
* 修改后的角色设定；
* 修改后的世界观设定；
* 修改后的 translation memory。

上传后必须先生成 sync plan。

sync plan 至少包含：

* 修改了哪些章节；
* 修改了哪些 segment；
* 涉及哪些术语；
* 涉及哪些角色；
* 是否需要更新 glossary；
* 是否需要更新 character_profile；
* 是否需要更新 style_profile；
* 是否需要更新 translation memory；
* 是否需要局部重译；
* 是否需要重新执行一致性检查；
* 是否影响当前 final export。

同步不得直接覆盖：

* 原文；
* human_approved_final。

同步应写入：

* translation memory；
* glossary；
* character profile；
* local fix plan；
* revised output；
* audit report。

---

## 16. Git 安全规则

任何 Agent 都不得提交：

```text
.env
API Key
token
cookie
真实小说原文
真实译文
workspace/runs 大型内容
workspace/diagnostics 大型内容
output_draft
output_refined
output_final
production_candidate 正文
Chrome profile
大型日志
```

可以提交：

```text
scripts
tests
docs
Runbook
Roadmap
Task List
脱敏报告模板
.gitignore 修复
配置模板
小型脱敏统计报告
```

不得使用：

```bash
git add .
```

---

## 17. 模型与上下文使用规则

### 17.1 翻译模型 / Agent

默认生产翻译 profile：

```text
draft_translation_primary
```

若使用外部 API，必须遵守 cost guard。若使用 Agent 额度，必须记录为 `agent_quota_translation`，并写入与 API 模式同构的中间态。

### 17.2 模型切换限制

未经用户明确确认，不得：

* 启用 Nemotron 作为生产模型；
* 开启大规模模型 A/B；
* 更换生产模型；
* 提高成本上限；
* 启动并发真实 API worker。

### 17.3 上下文规则

Agent 和脚本不得每轮回溯全书。

每次 API 调用或 Agent 额度翻译只允许注入：

* 固定 system prompt；
* 当前语言方向；
* 输出格式；
* 当前 chapter metadata；
* 当前 batch source segments；
* 当前 batch 命中的 glossary；
* 当前 batch 涉及角色的 character notes；
* 上一 batch 的短尾部或摘要；
* 当前章节摘要，如果已有。

禁止注入：

* 全书原文；
* 全书译文；
* 全书 glossary；
* 全书 character profile；
* 全部 world bible；
* 长 Roadmap；
* 所有历史报告；
* 所有前文。

---

## 18. P0 / P1 / P2 问题定义

### 18.1 P0：必须立即修复

* orphan worker；
* active worker 冲突；
* checkpoint 会被覆盖；
* run_progress 严重错乱；
* 章节错位；
* 漏段；
* failed segments 无法 retry；
* blocking validation_failed；
* API cost guard 缺失；
* Git 将真实内容纳入提交；
* 真实 API 无限制连续调用；
* 删除真实原文；
* 覆盖人工校对译文。

### 18.2 P1：优先修复

* batch planner 退化；
* runner progress 不清晰；
* report 不支持当前 phase；
* draft_completed_chapters 统计口径异常；
* source_residual 启发式误判严重；
* context pack 过长；
* prompt 输出格式不稳；
* validator 误判太多；
* local scheduler 状态不清晰；
* launchd 日志不可读；
* Web UI 状态不清晰；
* Web UI 操作路径混乱。

### 18.3 P2：记录到阶段检查

* 非阻塞术语问题；
* 非阻塞人名问题；
* 非阻塞技能名问题；
* 风格问题；
* 轻微格式问题；
* UI 视觉优化；
* UI 信息密度优化；
* 阅读体验优化。

---

## 19. 整个项目 Definition of Done

整个项目只有在以下条件全部满足时，才算自动化生产流程完成：

1. Phase A 全书翻译完成；
2. Phase B 一致性检查完成；
3. Phase C singleton final export 完成；
4. 唯一最终译文 `output_cn/translated/full_volume_cn.md` 已生成；
5. `output_cn/final_export_manifest.json` 已生成且声明 `singleton_full_volume_cn`；
6. `reports/final_translation_singleton_check.json` PASS；
7. Web UI 可以启动；
8. Web UI 可以显示项目总览；
9. Web UI 可以启动 / 暂停 / 恢复流水线；
10. Web UI 可以查看章节状态；
11. Web UI 可以查看和编辑术语库；
12. Web UI 可以导入 / 导出术语库；
13. Web UI 可以查看原文 / 译文 / 用户修改稿对照；
14. Web UI 可以上传用户修改稿；
15. Web UI 可以生成用户修改同步计划；
16. Web UI 可以导出唯一最终译文；
17. 所有 blocking issue 为 0；
18. failed / validation_failed 为 0；
19. no active worker；
20. no orphan worker；
21. local scheduler 可暂停、可恢复、可查看状态；
22. 所有关键报告存在；
23. Git 中没有真实原文、真实译文、API Key、token、cookie、大型 workspace 文件；
24. 未标记 human_approved_final；
25. 未对外发布。

---

## 20. 后续 Agent 必读规则

任何后续 Agent 在执行前，必须优先读取：

```text
docs/product_final_state_spec.md
docs/translation_production_protocol.md
docs/translation_consistency_protocol.md
docs/definition_of_done.md
docs/phase_acceptance_criteria.md
docs/non_goals_and_guardrails.md
docs/local_scheduler_runbook.md
```

如果临时 Prompt、Roadmap、Task List、Run Report 与本文件冲突，以本文件为准。

---

## 21. 本文件定位

本文件不是普通说明文档。

它是：

* 项目最终成品规格；
* 后续 Agent 防跑偏锚点；
* 自动推进验收基准；
* 阶段目标统一来源；
* Web UI 最终形态约束；
* 判断任务是否偏航的最高级别文档。

任何 Agent 不得随意删除、弱化或绕过本文件。

如需修改本文件，必须说明：

1. 为什么修改；
2. 修改了哪些最终目标；
3. 是否影响已有 Roadmap；
4. 是否影响已生成产物；
5. 是否需要用户确认。

---

## 22. 最终原则

```text
稳定完成真实小说的本地自动化翻译生产流程，并通过不丑、清晰、可控的 Web UI 让用户能够管理翻译、一致性校对、最终导出和人工修改同步。
```

任何优化都必须服务于：

* 更稳定地完成翻译；
* 更可靠地检查一致性；
* 更准确地导出唯一最终译文；
* 更方便地通过 Web UI 管理项目；
* 更清楚地展示状态；
* 更容易地维护术语库；
* 更安全地上传和同步用户修改；
* 更少地产生人工介入；
* 更少地产生孤儿 worker；
* 更少地产生上下文膨胀；
* 更少地产生无效重跑。

如果某项工作不能服务于这些目标，应后置。
