# Non-Goals and Guardrails

> 非目标与防跑偏约束（v2.0，2026-06-18）。锚点：`docs/product_final_state_spec.md` v2.0。
> 任何轮次任务、临时 Prompt、优化想法与本文件冲突时，以最终规格与本文件为准。

## 1. 当前阶段不做什么（Non-Goals）

以下方向**不属于**当前主线，不得占用推进轮：

- 公开 SaaS / 多用户权限系统 / 云端部署 / 商业计费；
- 自动投稿、自动发布、外部分享页面；
- 漫画 OCR 翻译、图像翻译、语音合成（TTS / 有声书）；
- 多模型长期排行榜 / 大规模模型 A/B；
- 插件市场、复杂团队协作；
- 版权管理系统、商业发行系统。

可作为未来方向记录在 backlog，但不得为其修改主线架构。

## 2. 必须后置的任务

| 任务类型 | 后置到 |
| --- | --- |
| UI 视觉抛光（P2 级） | Web UI Final |
| 阅读体验 / 信息密度优化 | Web UI Final |
| 非阻塞术语 / 人名 / 风格问题 | 对应 Phase 的阶段检查（P2 backlog） |
| EPUB 等次要导出格式 | S13 |
| 性能优化（无实测瓶颈时） | 出现 P1 级实测瓶颈后 |
| 重构（与当前轮产物无关时） | 不做，除非阻塞当前轮 |

P0 / P1 未清零时不得做 P2 / P3（定义见规格 §23）。

## 3. 需要用户确认才能做的事

- 标记 `human_approved_final`（**只能用户做，Agent 永远不能**）；
- 更换生产模型 / 启用 Nemotron / 开启模型 A/B；
- 提高成本上限（`MAX_TEST_COST_USD` 等）；
- 启动并发真实 API worker；
- push 到远程 / 开 PR；
- 提交任何含 workspace 运行产物的变更；
- 提交含真实术语 / 译名的 configs 数据；
- 删除任何 run / checkpoint / 归档数据；
- 修改 `docs/product_final_state_spec.md`（须按其修改流程说明五项理由）；
- 对外发布任何译文。

## 4. 禁止 Agent 自动执行的行为

- 自动标记 human_approved_final；
- 自动 commit / push；Round Prompt、edit/build 请求均不授权 Git，commit 与 push 分别需要用户当前轮明确授权；
- 自动发布、公开译文；
- 自动删除真实原文（`input_jp/` / `input_zh/`）；
- 自动覆盖原文、baseline、human_approved_final、人工校对译文；
- 自动清理"看似无用"的 workspace 数据；
- 用 `git add .` 提交；
- 无限制连续调用真实 API（必须有 max-api-calls / cost guard）；
- 在 Multitask / 后台子 Agent 中控制浏览器；
- 读取或打印 `.env` 内容、API Key、token、cookie。

## 5. 禁止提交 Git 的内容

```
.env 及任何密钥（API Key / token / cookie / PAT）
真实小说原文（input_jp/ input_zh/）
真实译文（output_draft/ output_refined/ output_final/ draft_full_baseline/
  output_cn/translated/full_volume_cn.md / 正文）
workspace/runs、workspace/diagnostics、workspace/archived_runs 大型内容
大型日志、Chrome profile
含真实正文的报告
```

可以提交：scripts、tests、docs、runbook、roadmap、task list、脱敏报告模板、配置模板、.gitignore 修复、小型脱敏统计报告。

## 6. 必须二次确认的操作（UI 与 CLI 同等适用）

- 停止真实 API worker；
- 清理 lock（且必须先验证 pid 不活跃）；
- 局部重跑 / 重译；
- 删除 run；
- 覆盖任何输出；
- 导入用户修改稿并执行同步；
- 存在 blocking issue 时导出 final package。

## 7. 必须停止并报告的情况（硬阻塞）

- 合同允许的一次性隔离副本中，`agent_gate.py` 退出码 2（BLOCKED）；真实工作树禁止运行完整 gate；
- 发现 orphan worker 且无法安全回收；
- checkpoint / run_progress 出现可能丢数据的错乱；
- 发现密钥或真实正文已被纳入待提交内容；
- cost guard 缺失或失效而任务需要真实 API；
- 浏览器工具未暴露而当前轮必须做 UI 验收（输出 `BLOCKED: MISSING_FROM_THREAD_TOOL_REGISTRY`）；
- 当前任务与最终规格冲突且无法在轮内消解。

## 8. 可以继续自动推进的情况

- 上一轮完成且无 P0 / P1 遗留；
- 合同指定的 targeted/read-only checks 通过；如合同要求完整 gate，则一次性隔离副本中的 gate 通过（或仅 warn 且已记录）；
- 下一轮任务在 `final_state_round_task_list.md` 中有明确定义；
- 所需工具可用或有已记录的 fallback；
- 真实 API 轮：cost guard 生效、pause file 不存在、无 active worker 冲突。

满足以上即可按轮次清单继续，无需用户逐轮确认（里程碑闸门除外：baseline lock、singleton final export、human_approved_final）。

## 9. 真实 API 处理规则

- 真实 API 是本项目生产目标的一部分，**不得永久禁用**；按轮次任务的"是否允许真实 API"字段执行。
- 只从环境变量读取 Key；不读 `.env` 文件内容、不打印、不入日志、不入前端响应。
- 每次真实运行必须有：max-api-calls 或等效预算、cost guard、成本记录。
- 失败重试有限次（指数退避），不得无限循环。
- pause file 存在时一切真实 API 调度停止。
- 缺 Key 时进入 dry-run / mock 并记录 `missing_api_key`，不阻断可离线推进的工作。

## 10. 大型 workspace 处理规则

- `workspace/runs`、`workspace/archived_runs/`、`diagnostics`、`logs`、`indexes` 等保持 gitignore；每轮 commit 前可用 `git check-ignore workspace/archived_runs/` 复核；
- 不全量读取大型 run 文件入上下文（用统计 / manifest / 抽样）；
- 归档而非删除：历史 run 移入 `workspace/archived_runs/`；
- 状态模板放 `docs/examples/` 或 `templates/`，真实状态留 workspace。

## 11. 真实原文与真实译文处理规则

- 原文只读：任何脚本不得改写 / 移动 / 删除 `input_jp/`、`input_zh/`；
- 译文产物只能写入规定输出目录；baseline 与 human_approved_final 生成后写保护；
- 报告与文档中引用正文时只允许小段脱敏示例或纯统计；
- 上下文注入遵守最终规格：仅当前 batch 相关内容，禁止全书回溯。

## 12. Legacy 路线禁用

以下旧路线已从主线删除，不得自动推进：

```text
Phase D refinement
R-MR
Phase E final review
production_candidate
```

若旧脚本仍保留，只能作为历史诊断或 fixture；scheduler planner 不得自动执行这些路线。
