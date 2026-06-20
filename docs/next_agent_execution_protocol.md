# Next Agent Execution Protocol

> 后续推进轮 Agent 标准工作协议（v2.0，2026-06-18）。
> 目的：后续轮 Agent **不重新发明路线**，只按 Roadmap 与 Round Task List 执行。
> 若本协议与 `docs/product_final_state_spec.md` 冲突，以最终规格为准。

## 0. 必读文件（按序）

1. `docs/product_final_state_spec.md` —— 最高项目目标锚点
2. `docs/translation_production_protocol.md` —— API / Agent 额度双路径翻译协议
3. `docs/translation_consistency_protocol.md` —— 一致性治理与唯一最终译文规则
4. `AGENTS.md` —— 执行与安全规则
5. `docs/final_state_implementation_roadmap.md` —— 总路线
6. `docs/final_state_round_task_list.md` —— 轮次任务与状态
7. `docs/phase_acceptance_criteria.md` / `docs/definition_of_done.md` —— 验收
8. `docs/non_goals_and_guardrails.md` —— 防跑偏
9. `reports/latest-agent-report.json`（若存在）—— 上轮交接

## 1. 每轮标准流程

```
① 读取最终规格 + Roadmap + Round Task List
② git status --short / git diff --stat 了解工作区
③ 串行运行 local_scheduler_status / orphan / singleton 探针；不要与 agent_gate 并发
④ 在 Round Task List 中找到第一个 not_started（或 in_progress）的 FS 轮，
   确认其依赖 Stage 已完成；阻塞则按清单允许的并行 Stage 取下一可执行轮
⑤ 状态门禁：python3 scripts/agent_gate.py --json（与 scheduler 探针串行）
⑥ 执行该轮"要修改 / 新增的文件"与"要执行的命令"
⑦ 若涉及 Web UI：npm run dev:frontend 启动，用 chrome-devtools / playwright /
   Cursor 内置 browser 做 before/after 检查（页面内容、console、network），
   截图入 artifacts/；普通前台 Agent 执行，禁止 Multitask 控浏览器
⑧ 若该轮允许真实 API：确认 pause file 不存在、cost guard 生效、无 active worker，
   按该轮预算执行；记录调用数与成本；缺 Key 则 dry-run 并记录 missing_api_key
   若该轮允许 Agent 额度翻译：按 `translation_production_protocol.md` 写入同构 segment/run schema
⑨ 验证：按该轮"验收标准"逐条核对；npm run test:py / npm run test:ui 视变更运行
⑩ 报告：写 reports/latest-agent-report.json + 追加 reports/agent_audit_log.jsonl；
   轮次详情入 workspace/round_reports/（脱敏）
⑪ 更新任务状态：在 final_state_round_task_list.md 该轮末尾追加
   "> ✅ 完成于 YYYY-MM-DD（证据引用）"；未完成则标注阻塞原因
⑫ Git：git status --short && git diff --stat && git diff --check；
   只 add 本轮相关文件（禁止 git add .）；确认无密钥 / 正文
⑬ Commit：仅用户或当前轮 Prompt 明确要求时执行；使用 scoped add
⑭ Push：仅用户已明确授权时执行；失败一次即记录原因，不反复重试
⑮ 输出下一轮建议（轮次号 + 一句话目标）
```

## 2. 轮次选择规则

- 默认顺序执行 `final_state_round_task_list.md` 中的 v2 FS 轮；
- 当前作品应保持 `current_phase=final_ready`、`next_round_id=null`；如果任何旧文档声称下一轮是 `R-MR-001`，先修正文档，不要执行；
- 新作品翻译按 API Mode 或 Agent Quota Mode 执行，产物必须进入同构 segment/run schema；
- P0 / P1 问题出现时中断当前轮，先修复（定义见规格 §23）；
- 不得跳过闸门轮（Phase A / Phase B / Phase C / Web UI / DoD）。

## 3. 真实 API 规则（摘要，详见 non_goals_and_guardrails §9）

- 按轮次任务字段执行；不预设禁区也不超预算；
- 生产模型 `deepseek/deepseek-v4-pro`（translation）；切换 / 并发 / 提价需用户确认；
- 永不打印 Key；永不读 `.env` 内容。

## 4. UI 检查规则（摘要）

- 改 UI 必先看真实页面，改完必再看；不得仅凭代码宣称完成；
- console 错误与关键 network 请求必查必记；
- 每轮只做一个主要 UI 切片；
- Stitch 仅作设计输入，导出物入 `docs/design/stitch/`；
- 浏览器工具缺失时输出 `BLOCKED: MISSING_FROM_THREAD_TOOL_REGISTRY` 并停止该轮 UI 部分。

## 5. 停止条件

遇到 `non_goals_and_guardrails.md` §7 任一硬阻塞：停止、写明阻塞原因与建议处置、输出 BLOCKED 报告。不得带病推进。

## 6. 报告最小字段

`reports/latest-agent-report.json` 须含：round_id（FS-xxx）、goal、files_changed、commands_run、tools_used / tools_not_used、real_api_used（bool + 调用数 + 成本）、ui_checked（bool + 证据路径）、acceptance_result（逐条）、blockers、next_recommended_round。Schema：`schemas/agent_round_report.schema.json`。
