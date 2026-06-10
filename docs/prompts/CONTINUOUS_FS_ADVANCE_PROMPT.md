# Continuous FS Advance Prompt（连续推进轮 Prompt）

> 用途：让推进轮 Agent 按既有路线连续逐轮推进 FS-000…FS-070，每轮提交 GitHub main，无硬阻塞不停轮。
> 使用方法：在 **普通前台 Cursor Agent**（禁止 Multitask）中粘贴本文件全文，或粘贴启动短语：
> 「请读取 `docs/prompts/CONTINUOUS_FS_ADVANCE_PROMPT.md` 并严格按其执行连续推进。」
> 本 Prompt 代表用户授权：每轮结束 commit 并 push 到 main；允许按轮次定义使用真实 API 与真实数据。

---

## 0. 你的角色

你是本仓库的推进轮 Agent。路线已经治理完毕，**你不需要也不允许重新设计路线**。你的全部工作是：

读取轮次清单 → 执行下一轮 → 验收 → 提交 → 推进下一轮 → 循环，直到没有新轮次或遇到硬阻塞。

---

## 1. 最高锚点与必读（每个新会话开始时按序读取）

1. `docs/product_final_state_spec.md` —— 最高规格，任何冲突以它为准
2. `AGENTS.md` —— 顶部「最终成品规格」专节
3. `docs/next_agent_execution_protocol.md` —— 每轮 13 步标准流程（本 Prompt 的细则基础）
4. `docs/final_state_implementation_roadmap.md` —— S0–S15 阶段地图
5. `docs/final_state_round_task_list.md` —— **执行队列唯一来源**（轮次定义 + 完成状态标记）
6. `docs/phase_acceptance_criteria.md`、`docs/definition_of_done.md` —— 验收标准
7. `docs/non_goals_and_guardrails.md` —— 硬阻塞、禁止事项、需用户确认事项
8. `reports/latest-agent-report.json` —— 上轮交接（含遗留 P1/P2）

---

## 2. 连续推进主循环

```
LOOP:
  1. 读 docs/final_state_round_task_list.md，找到第一个未标记「✅ 完成」的 FS 轮
     （按编号顺序；Roadmap §3 标注的可并行 Stage 仅在批量 API 轮等待间隙穿插）。
  2. 所有轮次已完成？ → 输出最终总结，停止。
  3. 该轮是否为里程碑闸门？
     FS-038（baseline lock）、FS-050（production_candidate 生成）
     → 停止，向用户展示前置验收证据，等待用户明确确认后才执行该轮。
  4. 执行该轮（见 §3 每轮流程）。
  5. 验收逐条核对该轮「验收标准」：
     - 全部通过 → 在任务清单该轮末尾追加「> ✅ 完成于 YYYY-MM-DD（证据）」，
       更新轮次状态总表，写 reports/latest-agent-report.json + agent_audit_log.jsonl。
     - 未通过 → 当轮内修复重验；仍不过 → 按 §5 判断是否硬阻塞。
  6. Git：三连检查 → 只 add 本轮文件 → commit → push origin main。
     push 失败：重试一次；再失败记录原因继续下一轮（除非失败原因本身是硬阻塞，
       如检测到待推送内容含密钥/正文）。
  7. 检查 §5 硬阻塞清单。无 → 回到 1；有 → 输出 BLOCKED 报告，停止。
```

**会话续航**：若上下文接近耗尽或会话中断，先完成当前轮的状态落盘 + commit + push，再输出交接摘要。新会话粘贴本 Prompt 即可无缝续跑（任务清单状态即断点）。

---

## 3. 每轮流程（精简，全文见 next_agent_execution_protocol.md）

1. `git status --short` 确认工作区干净（残留未知变更 → 先甄别，不得裹挟提交）。
2. 状态探针：`python3 scripts/agent_gate.py --json`、`python3 scripts/check_orphan_workers.py --json`、`python3 scripts/local_scheduler_status.py --json`。
3. 按该轮任务卡的「输入 / 要修改的文件 / 要执行的命令」实现。
4. 测试：代码变更跑 `npm run test:py`（全套必须绿）；UI 变更另跑 `npm run test:ui`。
5. 报告校验：`.venv/bin/python scripts/validate_agent_report.py` 必须 PASS。
6. 轮次产物入规定路径；脱敏报告入 `workspace/round_reports/` 或 `docs/reports/`。

---

## 4. 真实 API 规则（用户已授权，按轮次边界执行）

- **允许**：凡轮次任务卡标注「是否允许真实 API：是」的轮次，直接使用真实 API 与真实小说数据执行（生产模型 `deepseek/deepseek-v4-pro`，初翻 profile `draft_translation_primary`），无需逐轮再询问用户。
- **预算**：遵守 cost guard 与 `MAX_TEST_COST_USD` / `agent_layer.yaml` / `docs/COST_CONTROL.md`；每轮记录 api_calls 与 cost_usd 到轮次报告。单轮成本超限 → 立即停止该轮并按 §5 处理。
- **批量阶段（S2 Phase A / S8 Phase D）**：
  - 以 supervised micro round（3 章）为子单位连续执行；禁止 detached background worker、禁止并发 worker。
  - 每个 D-MR / R-MR 结束：保存 checkpoint、生成 MR 报告、orphan 自检（CLEAN 才继续）。
  - 每完成一个 Milestone Block（5 个 MR / 15 章）：执行一次 FS-009 式健康检查 + commit + push（仓库可跟踪变更通常为脱敏报告与任务状态；真实译文永不提交）。
  - **已知前置**：FS-008 启动批量前必须先回填 ch191-208 缺口（见 FS-002 报告；status 已输出 `draft_gap_backfill range=191-202`，另含 203-208）。回填同样以 3 章 MR 粒度执行。
  - **禁止重用已有 run 目录**（FS-002 发现的数据丢失根因）。
- **永不**：打印 API Key、读 `.env` 内容、未经用户确认更换生产模型 / 开并发 / 提高成本上限、无限制连续调用（每轮必须有 max-api-calls 或等效预算）。
- pause file（`workspace/control/scheduler_paused.json` 含 `"paused": true`）存在时一切真实 API 停止。
- 缺 Key → dry-run 并记录 `missing_api_key`，继续可离线推进的轮次，不卡死整体。

---

## 5. 停止条件（硬阻塞，唯一允许停轮的情形）

出现以下任一情况，停止循环并输出 BLOCKED 报告（现象 / 证据 / 建议处置）：

1. `agent_gate.py` 退出码 2（BLOCKED）；
2. orphan worker 无法安全回收；
3. checkpoint / run_progress 出现可能丢数据的错乱；
4. 发现密钥或真实正文已进入待提交内容；
5. cost guard 失效或单轮成本超限且无法在轮内消解；
6. 当前轮必须用浏览器但工具未暴露（输出 `BLOCKED: MISSING_FROM_THREAD_TOOL_REGISTRY`）;
7. 当前轮与最终规格冲突且轮内无法消解；
8. 里程碑闸门（FS-038 / FS-050）等待用户确认；
9. P0 问题修复失败（P0 定义见规格 §23.1）。

**以下不是停止理由**：单个测试失败（修复它）、push 网络抖动（重试一次后记录）、P2 视觉问题（记 backlog）、真实 API 单次调用失败（按退避重试有限次）。

---

## 6. Git 规则（每轮强制）

- 提交目标：**main 分支直接提交并 push**（用户已授权；禁止 force push）。
- commit 前三连：`git status --short && git diff --stat && git diff --check`。
- **禁止 `git add .`**；只 add 本轮任务卡列出的文件 + 任务清单 + 报告三件套。
- commit message 格式沿用现有风格：`feat(scope): FS-XXX 中文摘要` + 要点列表。
- **永不提交**：`.env`、密钥、`input_*` 真实原文、真实译文、`output_*`、baseline / production_candidate 正文、`workspace/runs|archived_runs|diagnostics` 大型内容、大日志。
- `workspace/archived_runs/` 等未跟踪真实数据：保持未跟踪，不 add、不删除。

---

## 7. UI 轮特殊要求（S4 / S5 / S10–S14）

- 必须普通前台 Agent + 真实浏览器（chrome-devtools / playwright / Cursor 内置 browser）做 before/after 检查：页面内容、console 错误、关键 network 请求；截图入 `artifacts/`（不提交敏感内容）。
- 不得仅凭代码宣称 UI 完成；每轮只做一个主要 UI 切片。
- 中文界面、统一设计系统、危险操作二次确认、API Key 永不出现在 DOM/响应。
- Stitch 仅作设计输入，导出物入 `docs/design/stitch/`。

---

## 8. 当前交接状态（2026-06-11）

| 项 | 状态 |
| --- | --- |
| 已完成轮次 | FS-000（治理）、FS-001（pause/lock 内核）、FS-002（status 聚合） |
| **下一轮** | **FS-003：local_scheduler_tick.py dry-run 骨架** |
| Phase A 进度 | 223/613 章（36.38%），metadata 与 content 双口径一致 |
| 已知 P1 | ch191-208 缺口（run 目录重用致历史丢失）→ FS-008 前回填 |
| 已知 warn | stale lock `refine_stage_c_run_20260602_203645.lock`、stage_state_stale → FS-006 治理 |
| worker | 0 active / 0 orphan |
| 测试基线 | 239 passed |

---

## 9. 每轮输出格式（聊天回复）

```
# FS-XXX 完成：<标题>
## 实现内容（要点）
## 验收核对（逐条 ✅/❌ + 证据）
## 真实 API 使用（是/否；调用数；成本）
## Git（commit hash；push 结果）
## 下一轮（编号 + 一句话目标；或 BLOCKED 报告）
```

批量阶段可按 Milestone Block 汇总输出，避免刷屏。

---

## 10. 重要禁止（违反任一即视为本 Prompt 执行失败）

1. 重新发明路线 / 跳过验收 / 跳过闸门轮；
2. 自动标记 human_approved_final（永远只能用户做）；
3. 自动对外发布；
4. 覆盖原文 / baseline / production_candidate / 人工校对译文；
5. `git add .` 或提交真实正文 / 密钥；
6. Multitask 控制浏览器；
7. 留下 orphan worker 结束轮次；
8. 为继续推进而删除失败测试或伪造测试结果；
9. P0/P1 未清零去做 P2/P3；
10. 把"没有新轮次"之外的可修复问题当作停止理由（能修则修，修完继续）。

现在开始：读取必读文件，从任务清单中找到下一个未完成轮次，执行。
