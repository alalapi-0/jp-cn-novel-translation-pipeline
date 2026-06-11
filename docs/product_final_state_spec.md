# Product Final State Specification

项目名称：长篇小说中日互译生产流水线
仓库路径：`/Users/alalapi/PycharmProjects/light_novel`
文档类型：最终成品规格 / 终局锚点 / 后续 Agent 防跑偏基准
版本：v1.1
优先级：高于普通 Roadmap、Round Report、临时 Prompt、单轮执行指令

---

## 1. 北极星目标

本项目的最终成品，是一个**本地可持续运行、可通过 Web UI 操作的长篇小说中日互译生产流水线**。

它允许用户在本地导入长篇小说原文，通过真实 API 分阶段完成：

1. 全书初翻；
2. 初翻后一致性检查；
3. baseline draft 锁定；
4. 全书润色；
5. 润色后质量检查；
6. 生成可人工最终审阅的 `production_candidate`。

最终用户不应该被迫长期盯着 Cursor 聊天窗口，也不应该通过复杂命令手动推进每个阶段。最终形态应是：

```text
用户启动本地 Web 项目
→ 在浏览器中配置项目与 API
→ 导入小说原文
→ 配置术语库 / 角色设定 / 翻译风格
→ 点击启动流水线
→ Web UI 显示进度、成本、错误、报告
→ 用户可以暂停 / 恢复 / 局部重跑
→ 初翻完成后自动一致性检查
→ baseline 锁定后自动润色
→ 润色完成后自动质量检查
→ 用户在 Web UI 中审阅、修改、上传人工修改稿
→ 系统根据用户修改同步术语库、翻译记忆和全书一致性
→ 最终导出 production_candidate
```

---

## 2. 最终成品一句话定义

本项目最终不是一个单次翻译脚本，而是：

```text
一个本地 Web UI 驱动的长篇小说中日互译生产系统。
它通过本地调度器和真实 API，将原文解析为稳定中间态，按 checkpoint 分阶段完成初翻、一致性检查、baseline、润色、终检和导出，并支持用户通过 Web UI 管理术语、角色、配置、进度、报告和人工修改同步。
```

---

## 3. 最终用户画像

本项目的最终用户是：

1. 想批量翻译长篇小说的人；
2. 想长期维护一部作品翻译资产的人；
3. 想让术语、人名、地名、技能名保持一致的人；
4. 想通过真实 API 自动翻译，但又不想被命令行和 Cursor 前台会话绑定的人；
5. 想在翻译过程中沉淀术语库、角色设定、世界观资料、翻译记忆的人；
6. 想通过 Web UI 审阅、修正、上传人工修改稿，并把修改反馈到整部作品的人。

---

## 4. 项目最终边界

### 4.1 本项目最终是什么

本项目最终是：

* 本地运行的长篇小说翻译生产流水线；
* 支持中日互译的结构化翻译系统；
* 支持真实 API 的批量翻译和润色系统；
* 支持 Web UI 操作的本地生产工具；
* 支持术语库、角色设定、世界观设定、翻译记忆的管理系统；
* 支持 checkpoint、断点续跑、暂停、恢复、局部重跑的任务系统；
* 支持用户人工修改稿上传和全书同步修正的译文管理系统；
* 支持最终导出 draft、baseline、refined、production candidate 的成品生成系统。

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
* TTS 或有声书系统；
* 面向普通公众的线上服务。

这些可以作为未来方向，但不能干扰当前主线。

---

## 5. 最终系统架构

最终系统由五层组成：

```text
Web UI 层
→ 本地 API / Backend 层
→ Pipeline Orchestrator 层
→ Translation / Refinement Worker 层
→ Storage / Workspace / Index 层
```

### 5.1 Web UI 层

Web UI 是最终用户主要操作入口。

用户应能通过浏览器完成：

* 创建项目；
* 导入原文；
* 配置 API；
* 配置模型；
* 管理术语库；
* 管理角色设定；
* 管理世界观资料；
* 启动初翻；
* 查看进度；
* 暂停 / 恢复；
* 查看错误；
* 查看成本；
* 查看章节状态；
* 查看初翻；
* 查看润色；
* 对比原文 / 初翻 / 润色 / 用户修改稿；
* 上传人工修改版本；
* 将人工修改同步到术语库、翻译记忆和全书一致性修正；
* 导出最终候选版本。

### 5.2 Backend 层

Backend 负责：

* 读取项目配置；
* 暴露本地 API；
* 管理任务状态；
* 调用 pipeline 脚本；
* 读写 workspace；
* 读取报告；
* 提供 Web UI 数据；
* 管理暂停 / 恢复 / 重跑 / 导出请求。

### 5.3 Pipeline Orchestrator 层

Pipeline Orchestrator 负责：

* 判断当前 Phase；
* 判断下一任务；
* 调用 D-MR / R-MR；
* 调用一致性检查；
* 调用 baseline lock；
* 调用最终质量检查；
* 管理 checkpoint；
* 防止并发 worker；
* 维护 lock；
* 生成报告；
* 处理失败重试；
* 保证不会产生孤儿 worker。

### 5.4 Worker 层

Worker 负责：

* 调用真实 API；
* 执行初翻；
* 执行润色；
* 执行局部重译；
* 保存 batch 结果；
* 保存 checkpoint；
* 更新 run_progress；
* 输出 compact progress；
* 按 token budget 分批；
* 不读取全书上下文；
* 不提交真实正文。

### 5.5 Storage 层

Storage 负责保存：

* 原文解析结果；
* segment 中间态；
* draft；
* baseline；
* refined；
* production candidate；
* glossary；
* character profile；
* world bible；
* translation memory；
* consistency audit；
* final review；
* round reports；
* scheduler 状态；
* logs；
* lock；
* pause file。

---

## 6. 最终 Web UI 总体要求

Web UI 不是附属品，而是最终成品的重要组成部分。

最终 Web UI 必须满足：

1. 能启动整个流水线；
2. 能暂停和恢复流水线；
3. 能显示当前阶段；
4. 能显示当前章节范围；
5. 能显示当前 API 模型；
6. 能显示已完成章节数；
7. 能显示失败章节和失败 segment；
8. 能显示成本估算；
9. 能显示最近一次错误；
10. 能查看每轮报告；
11. 能查看术语库；
12. 能编辑术语库；
13. 能导入 / 导出术语库；
14. 能查看角色设定；
15. 能编辑角色设定；
16. 能查看原文 / 初翻 / 润色 / 用户修改稿；
17. 能上传用户人工修改版本；
18. 能根据用户修改生成同步计划；
19. 能执行局部修正或全书一致性同步；
20. 能导出最终候选成品。

UI 必须是中文优先。

UI 不得简陋到只像调试页面。
UI 不得只有命令行输出搬运。
UI 必须让非开发者也能理解当前项目在做什么、进展如何、哪里出错、下一步是什么。

---

## 7. Web UI 信息架构

最终 Web UI 应至少包含以下主页面。

### 7.1 Dashboard 总览页

用途：显示整个项目当前状态。

必须显示：

* 项目名称；
* 当前 Phase；
* 当前任务；
* 当前 round；
* 当前章节范围；
* 全书章节总数；
* 初翻完成进度；
* 一致性检查状态；
* baseline 状态；
* 润色完成进度；
* 最终质量检查状态；
* production_candidate 状态；
* 当前模型；
* 本轮 API 调用数；
* 累计成本；
* active worker 状态；
* orphan worker 状态；
* scheduler 状态；
* 最近错误；
* 下一步任务。

必须提供按钮：

* 启动 / 继续；
* 暂停；
* 恢复；
* 查看报告；
* 查看错误；
* 打开当前章节；
* 打开术语库；
* 打开设置。

### 7.2 项目设置页

用途：配置当前小说项目。

必须支持：

* 项目名称；
* 源语言；
* 目标语言；
* 小说类型；
* 题材；
* 文风；
* 章节输入目录；
* 输出目录；
* 是否启用双语对照；
* 是否保留原文排版；
* 是否生成 Markdown；
* 是否生成 EPUB；
* 是否生成 TXT；
* 是否生成 production_candidate；
* 是否允许自动进入下一阶段；
* 成本上限；
* 每轮章节数；
* batch token budget；
* max segments per call。

### 7.3 API / 模型设置页

用途：配置真实 API。

必须支持：

* Provider；
* API Base URL；
* API Key 状态检测；
* 初翻模型；
* 润色模型；
* 审查模型；
* embedding 模型；
* temperature；
* top_p；
* reasoning / thinking 开关；
* max tokens；
* rate limit；
* cost guard；
* 连接测试；
* 小规模 smoke test。

禁止在 UI 中明文显示完整 API Key。
最多显示脱敏形式，例如：

```text
sk-****abcd
```

### 7.4 原文导入页

用途：导入小说原文。

必须支持：

* 上传单章；
* 批量上传章节；
* 选择本地目录；
* 检查章节顺序；
* 自动识别章节标题；
* 自动生成 chapter_id；
* 自动生成 paragraph_id / segment_id；
* 显示解析结果；
* 显示异常章节；
* 重新解析；
* 导入确认。

必须避免：

* 覆盖已有原文；
* 改写原文文件；
* 破坏原文顺序；
* 自动删除原文。

### 7.5 Pipeline 控制台

用途：控制流水线运行。

必须支持：

* 启动 Phase A；
* 暂停 scheduler；
* 恢复 scheduler；
* 手动运行一次 tick；
* 手动执行下一个 D-MR；
* 手动执行下一个 R-MR；
* 停止当前 worker；
* 查看 active worker；
* 查看 orphan worker；
* 查看 lock；
* 清理 stale lock；
* 查看当前 checkpoint；
* 查看下一任务；
* 查看本地 launchd 状态。

危险操作必须二次确认。

危险操作包括：

* 停止真实 API worker；
* 清理 lock；
* 局部重跑；
* 删除 run；
* 覆盖输出；
* 导入用户修改稿并同步全书。

### 7.6 章节管理页

用途：查看章节级状态。

必须显示：

* 章节编号；
* 章节标题；
* 原文段数；
* 初翻状态；
* 一致性状态；
* baseline 状态；
* 润色状态；
* 终检状态；
* failed 数；
* validation_failed 数；
* 术语冲突数；
* 角色名冲突数；
* 技能名冲突数；
* 最近更新时间；
* 所属 run；
* 所属 round。

支持过滤：

* 未翻译；
* 初翻完成；
* failed；
* validation_failed；
* 术语冲突；
* 需要局部重译；
* 润色完成；
* 需要人工审阅。

### 7.7 译文阅读 / 对照页

用途：阅读和审阅译文。

必须支持多栏视图：

```text
原文
初翻
润色
用户修改稿
```

至少支持以下模式：

* 原文 + 初翻；
* 原文 + 润色；
* 初翻 + 润色；
* 润色 + 用户修改稿；
* 原文 + 初翻 + 润色；
* 原文 + 初翻 + 润色 + 用户修改稿。

必须支持：

* 段落级对齐；
* segment_id 显示；
* 搜索；
* 跳转章节；
* 显示术语命中；
* 显示角色名；
* 显示差异；
* 标记问题；
* 添加人工备注；
* 标记为已审阅；
* 标记为需要重译；
* 标记为需要润色；
* 标记为术语问题。

### 7.8 术语库页面

用途：维护术语一致性。

必须支持：

* 查看术语；
* 新增术语；
* 编辑术语；
* 删除术语；
* 锁定术语；
* 解锁术语；
* 标记人工确认；
* 标记机器建议；
* 标记冲突；
* 分类；
* 搜索；
* 批量导入；
* 批量导出；
* CSV 导入；
* CSV 导出；
* YAML 导入；
* YAML 导出；
* JSON 导入；
* JSON 导出。

术语字段至少包括：

```text
source_term
target_term
reading
category
description
first_seen_chapter
confidence
locked
approved_by_user
aliases
notes
created_at
updated_at
```

术语分类至少包括：

* 人名；
* 地名；
* 组织名；
* 技能名；
* 道具名；
* 称号；
* 种族；
* 魔法；
* 系统术语；
* 游戏术语；
* 不翻译词；
* 其他。

### 7.9 角色设定页面

用途：维护角色说话方式和称呼。

必须支持：

* 角色列表；
* 角色名；
* 别名；
* 译名；
* 称呼关系；
* 第一人称；
* 口癖；
* 敬语风格；
* 性格摘要；
* 说话风格；
* 禁止事项；
* 出场章节；
* 角色关系；
* 人工备注。

角色设定必须能被初翻、润色和一致性检查复用。

### 7.10 世界观 / 设定页面

用途：维护小说世界观资料。

必须支持：

* 世界观条目；
* 阵营；
* 国家；
* 地区；
* 魔法体系；
* 等级体系；
* 技能体系；
* 货币；
* 宗教；
* 种族；
* 组织；
* 游戏系统；
* 任务系统；
* 成就系统；
* 其他设定。

这些资料主要用于：

* 翻译一致性；
* 润色一致性；
* 后续小说生成项目资产沉淀；
* 后续游戏设定资产沉淀。

### 7.11 翻译记忆页面

用途：保存和复用用户修改、机器翻译、最终译文之间的映射。

必须支持：

* source segment；
* draft translation；
* refined translation；
* user revised translation；
* final candidate translation；
* change reason；
* applied_to_glossary；
* applied_to_prompt；
* applied_to_character_profile；
* applied_to_full_novel；
* created_at；
* updated_at。

### 7.12 用户修改稿上传页面

用途：让用户上传人工修改过的版本，并同步到系统。

必须支持：

* 上传用户修改后的章节；
* 上传用户修改后的全书；
* 自动对齐 segment_id；
* 如果无法自动对齐，进入人工对齐模式；
* 生成 diff；
* 识别术语修改；
* 识别人名修改；
* 识别风格修改；
* 识别增删信息；
* 生成同步建议；
* 用户确认后同步到术语库；
* 用户确认后同步到角色设定；
* 用户确认后同步到 translation memory；
* 用户确认后生成局部重译 / 局部重润色计划；
* 用户确认后应用到全书一致性检查。

上传用户修改稿不得直接覆盖 production candidate。
必须先生成 review diff 和 sync plan。

### 7.13 报告页面

用途：查看所有报告。

必须支持：

* round report；
* consistency report；
* baseline decision；
* refinement report；
* final review report；
* production candidate decision；
* cost report；
* error report；
* worker report；
* scheduler report。

报告页面必须支持：

* 按阶段过滤；
* 按 round 过滤；
* 按严重程度过滤；
* 按时间过滤；
* 导出 Markdown；
* 导出 JSON。

### 7.14 导出页面

用途：导出最终成品。

必须支持导出：

* 纯译文 Markdown；
* 双语对照 Markdown；
* TXT；
* EPUB；
* glossary；
* character profile；
* world bible；
* translation memory；
* consistency report；
* final review report；
* production candidate package。

导出前必须显示：

* 当前版本；
* 是否 production_candidate；
* 是否 human_approved_final；
* 是否存在 blocking issue；
* 是否存在 P2 backlog；
* 导出路径；
* 文件列表。

---

## 8. Web UI 视觉和交互要求

UI 最终必须做到：

* 清晰；
* 稳定；
* 不丑；
* 不像临时调试页；
* 不像纯表格堆砌；
* 不让用户迷路；
* 不让用户猜当前状态；
* 不让危险操作太容易误触。

### 8.1 视觉风格

建议风格：

```text
现代、干净、低噪音、信息密度适中、偏生产工具感
```

可接受风格参考：

* Notion 式清爽结构；
* Linear 式状态清晰；
* GitHub Actions 式任务状态；
* VS Code / Cursor 式开发者工具感；
* 日式轻小说阅读器的阅读舒适度。

禁止：

* 默认浏览器裸 HTML；
* 大片无层级表格；
* 颜色混乱；
* 按钮样式不统一；
* 状态标签不统一；
* 中英文混杂；
* 页面跳动；
* 过宽文本行；
* 无留白；
* 无视觉重点。

### 8.2 颜色规则

必须定义统一色彩系统。

建议：

* 成功：绿色；
* 运行中：蓝色；
* 警告：黄色 / 橙色；
* 错误：红色；
* 暂停：灰色；
* 人工确认：紫色；
* 生产候选：青色或蓝绿色。

颜色不得作为唯一信息来源。
状态必须同时有文本标签。

### 8.3 状态标签

所有状态必须统一。

建议状态：

```text
not_started
in_progress
paused
completed
completed_with_warnings
failed
blocked
needs_review
superseded
production_candidate
human_approved_final
```

不得在不同页面使用不同叫法。

### 8.4 反馈原则

用户操作后必须有反馈。

例如：

* 点击启动后显示任务已启动；
* 点击暂停后显示已写入 pause file；
* 上传文件后显示解析数量；
* 导入术语后显示新增 / 覆盖 / 冲突数量；
* 执行同步后显示影响章节；
* 导出后显示路径和文件列表；
* 出错后显示错误原因和可执行修复建议。

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

* 下一个 D-MR；
* 下一个一致性检查子任务；
* baseline lock；
* 下一个 R-MR；
* 下一个终检子任务；
* production candidate 生成。

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
* refinement_progress；
* safe_to_run。

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

则调度器不得启动真实 API。

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
  final_review/
  diagnostics/
  indexes/
  translation_memory/

configs/
  glossary.yaml
  character_profile.yaml
  style_profile.yaml
  world_bible.yaml
  model_profiles.yaml

output_draft/
draft_full_baseline/
output_refined/
refined_full_candidate/
production_candidate/

docs/
  product_final_state_spec.md
  definition_of_done.md
  phase_acceptance_criteria.md
  non_goals_and_guardrails.md
  local_scheduler_runbook.md
```

真实原文和真实译文默认不提交 Git。

---

## 11. 阶段总览

最终流程分为五个阶段：

```text
Phase A：Draft Translation
→ Phase B：Draft Consistency Audit
→ Phase C：Baseline Draft Lock
→ Phase D：Refinement
→ Phase E：Final Quality Review
→ production_candidate
```

---

## 12. Phase A：全书初翻

### 12.1 目标

生成完整、忠实、结构稳定、可审计的全书初翻稿。

初翻阶段不追求最终文学润色。

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

### 12.2 完成标准

Phase A 完成条件：

* 全书所有章节已完成 draft；
* 所有 segment status 为 completed；
* failed segment 数为 0；
* blocking validation_failed 数为 0；
* 无章节错位；
* 无漏段；
* checkpoint 完整；
* round reports 完整；
* no active worker；
* no orphan worker；
* draft 输出可导出或已导出。

---

## 13. Phase B：初翻一致性检查

### 13.1 目标

检查全书初翻的一致性。

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

### 13.2 检查方式

必须采用 progressive disclosure，不得全文硬扫。

层级：

```text
Level 0：metadata / manifest
Level 1：entity index / glossary / character index
Level 2：冲突统计
Level 3：只展开冲突 segment
Level 4：规则无法判断时才调用模型
Level 5：局部重译或局部修正
```

### 13.3 完成标准

Phase B 完成条件：

* chapter manifest 已构建；
* segment index 已构建；
* entity index 已构建；
* glossary 冲突已统计；
* blocking conflicts 为 0；
* 必要的局部修正或局部重译已完成；
* 一致性报告完整；
* 可以进入 baseline lock。

---

## 14. Phase C：baseline draft 锁定

### 14.1 目标

将通过一致性检查的初翻稿锁定为 baseline draft。

baseline draft 是润色阶段输入基线。
baseline draft 不是最终人工定稿。

### 14.2 输出

必须生成：

```text
draft_full_baseline/
draft_full_baseline_metadata.json
draft_full_baseline_go_decision.md
```

### 14.3 完成标准

Phase C 完成条件：

* Phase A 完成；
* Phase B 完成；
* blocking conflicts 为 0；
* failed / validation_failed 为 0；
* 无漏段；
* 无章节错位；
* baseline metadata 完整；
* baseline go decision 允许进入 Phase D。

---

## 15. Phase D：全书润色

### 15.1 目标

基于：

* 原文；
* baseline draft；
* glossary；
* character_profile；
* terminology fix plan；
* entity index；
* style_profile；

对全书译文进行二次润色。

润色不是重新翻译，而是改善表达。

润色必须保持：

* 原意；
* 信息量；
* 术语一致；
* 人名一致；
* 角色语气；
* 轻小说节奏；
* 伏笔暧昧性；
* 段落结构。

### 15.2 完成标准

Phase D 完成条件：

* 全书所有章节都有 refined 输出；
* 所有 R-MR round report 完整；
* 每个 R-MR 都有 diff；
* 每个 R-MR 都有 change_log；
* failed 数为 0；
* blocking validation_failed 数为 0；
* 无明显术语破坏；
* 无明显角色语气破坏；
* 无 blocking over-refinement issue；
* no orphan worker。

---

## 16. Phase E：润色后质量检查

### 16.1 目标

检查 refined 版本是否可以成为 production candidate。

重点检查：

* 是否改变原意；
* 是否删减信息；
* 是否新增信息；
* 是否破坏术语；
* 是否破坏角色语气；
* 是否把角色声音统一化；
* 是否提前解释伏笔；
* 是否把暧昧表达强行明确化；
* 是否过度文学化；
* 是否 diff 异常大；
* 是否章节风格漂移。

### 16.2 检查方式

不得全文硬扫。

采用：

```text
Level 0：refined metadata
Level 1：diff / change_log index
Level 2：修改比例异常统计
Level 3：定位过度润色候选章节
Level 4：局部展开 source / draft / refined 三方对比
Level 5：必要时模型审查或局部重润色
```

### 16.3 完成标准

Phase E 完成条件：

* refined metadata 完整；
* diff / change_log index 完整；
* 修改比例异常已检查；
* 过度润色候选已检查；
* blocking quality issue 为 0；
* 局部重润色或修正已完成；
* final review report 完整；
* production_candidate 已生成；
* 未标记 human_approved_final；
* 未对外发布。

---

## 17. production_candidate 定义

`production_candidate` 是自动化流程可以生成的最高级别成品。

它表示：

* 初翻已完成；
* 一致性检查已完成；
* baseline 已锁定；
* 润色已完成；
* 润色后质量检查已完成；
* 系统认为可以进入人工最终审阅。

它不表示：

* 人工已逐章审阅；
* 可以直接出版；
* 可以直接公开发布；
* 已解决所有主观风格问题；
* 已获得版权或发布许可；
* 已标记为 human_approved_final。

---

## 18. human_approved_final 定义

`human_approved_final` 只能由用户明确确认后生成。

任何 Agent 不得自动标记 `human_approved_final`。

---

## 19. 用户修改稿同步机制

最终系统必须支持用户上传人工修改版本。

### 19.1 上传对象

用户可以上传：

* 单章人工修改稿；
* 多章人工修改稿；
* 全书人工修改稿；
* 修改后的术语库；
* 修改后的角色设定；
* 修改后的世界观设定；
* 修改后的 translation memory。

### 19.2 对齐机制

系统必须尝试自动对齐：

* chapter_id；
* paragraph_id；
* segment_id；
* 原文；
* draft；
* refined；
* user revised text。

如果无法自动对齐，必须进入人工对齐模式，不得强行覆盖。

### 19.3 同步计划

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
* 是否需要局部重润色；
* 是否需要重新执行一致性检查；
* 是否影响 production_candidate。

### 19.4 同步规则

用户确认 sync plan 后，系统才可以执行同步。

同步不得直接覆盖：

* 原文；
* baseline draft；
* production_candidate；
* human_approved_final。

同步应写入：

* translation memory；
* glossary；
* character profile；
* local fix plan；
* revised output；
* audit report。

---

## 20. Git 安全规则

### 20.1 严禁提交

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

### 20.2 可以提交

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

### 20.3 Git 操作要求

不得使用：

```bash
git add .
```

必须只 add 本轮相关文件。

每次 commit 前必须执行：

```bash
git status --short
git diff --stat
git diff --check
```

---

## 21. 模型使用规则

### 21.1 初翻模型

默认使用：

```text
draft_translation_primary
```

当前生产模型为：

```text
deepseek/deepseek-v4-pro
```

### 21.2 润色模型

默认使用：

```text
refinement_primary
```

润色模型可以比初翻模型能力更强，但必须保持：

* 不擅自扩写；
* 不删减信息；
* 不破坏术语；
* 不破坏角色语气；
* 不提前解释伏笔；
* 不把暧昧表达强行明确化。

### 21.3 模型切换限制

未经用户明确确认，不得：

* 启用 Nemotron 作为生产模型；
* 开启大规模模型 A/B；
* 更换生产模型；
* 提高成本上限；
* 启动并发真实 API worker。

---

## 22. 上下文使用规则

Agent 和脚本不得每轮回溯全书。

每次 API 调用只允许注入：

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

## 23. P0 / P1 / P2 问题定义

### 23.1 P0：必须立即修复

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

### 23.2 P1：优先修复

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

### 23.3 P2：记录到阶段检查

* 非阻塞术语问题；
* 非阻塞人名问题；
* 非阻塞技能名问题；
* 风格问题；
* 轻微格式问题；
* 润色自然度问题；
* diff 异常候选；
* UI 视觉优化；
* UI 信息密度优化；
* 阅读体验优化。

---

## 24. 明确非目标

当前阶段不优先做：

* 公开 SaaS；
* 多用户权限系统；
* 云端部署；
* 自动投稿；
* 自动发布；
* 漫画翻译；
* OCR 翻译；
* 图像翻译；
* 语音合成；
* 商业计费；
* 外部分享页面；
* 复杂团队协作；
* 插件市场。

这些可以作为未来方向，但不得干扰当前主线。

---

## 25. 整个项目 Definition of Done

整个项目只有在以下条件全部满足时，才算自动化生产流程完成：

1. Phase A 全书初翻完成；
2. Phase B 初翻一致性检查完成；
3. Phase C baseline draft 锁定完成；
4. Phase D 全书润色完成；
5. Phase E 润色后质量检查完成；
6. `production_candidate/` 已生成；
7. `production_candidate_metadata.json` 已生成；
8. `production_candidate_go_decision.md` 已生成；
9. Web UI 可以启动；
10. Web UI 可以显示项目总览；
11. Web UI 可以启动 / 暂停 / 恢复流水线；
12. Web UI 可以查看章节状态；
13. Web UI 可以查看和编辑术语库；
14. Web UI 可以导入 / 导出术语库；
15. Web UI 可以查看原文 / 初翻 / 润色对照；
16. Web UI 可以上传用户修改稿；
17. Web UI 可以生成用户修改同步计划；
18. Web UI 可以导出 production_candidate；
19. 所有 blocking issue 为 0；
20. failed / validation_failed 为 0；
21. no active worker；
22. no orphan worker；
23. local scheduler 可暂停、可恢复、可查看状态；
24. 所有关键报告存在；
25. Git 中没有真实原文、真实译文、API Key、token、cookie、大型 workspace 文件；
26. 未标记 human_approved_final；
27. 未对外发布。

---

## 26. 后续 Agent 必读规则

任何后续 Agent 在执行前，必须优先读取：

```text
docs/product_final_state_spec.md
docs/definition_of_done.md
docs/phase_acceptance_criteria.md
docs/non_goals_and_guardrails.md
docs/local_scheduler_runbook.md
docs/translation_recovery_3ch_roadmap.md
docs/translation_recovery_3ch_task_list.md
```

如果这些文档尚不存在，应根据本文件拆分创建。

如果临时 Prompt、Roadmap、Task List、Run Report 与本文件冲突，以本文件为准。

---

## 27. 本文件定位

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

## 28. 最终原则

本项目的最终原则是：

```text
稳定完成真实小说的本地自动化翻译生产流程，并通过不丑、清晰、可控的 Web UI 让用户能够管理整个流程。
```

任何优化都必须服务于：

* 更稳定地完成初翻；
* 更可靠地检查一致性；
* 更安全地锁定 baseline；
* 更可控地完成润色；
* 更准确地生成 production_candidate；
* 更方便地通过 Web UI 管理项目；
* 更清楚地展示状态；
* 更容易地维护术语库；
* 更安全地上传和同步用户修改；
* 更少地产生人工介入；
* 更少地产生孤儿 worker；
* 更少地产生上下文膨胀；
* 更少地产生无效重跑。

如果某项工作不能服务于这些目标，应后置。
