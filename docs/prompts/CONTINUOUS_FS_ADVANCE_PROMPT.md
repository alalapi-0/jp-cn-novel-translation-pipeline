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

## 8. 当前交接状态（2026-06-11 07:40，第二次交接）

| 项 | 状态 |
| --- | --- |
| 已完成轮次 | FS-000…FS-008 全部 ✅（S0 治理 + S1 调度器全线 + S2 批量启动轮） |
| **当前任务** | **S2 Phase A 批量推进**：D-MR 队列连续执行（D-MR-016 进行中被暂停） |
| Phase A 进度 | **247/613 章（40.29%）**，ch1-247 连续完成；191-211 历史缺口已全部回填 |
| 断点 | D-MR-016（248-250）中断于 122/412 段，checkpoint 在；恢复后 planner 自动同 offset 续跑，**不会重复翻译** |
| 暂停状态 | `workspace/control/scheduler_paused.json` 存在（交接保护）→ **恢复推进前必须先清除**（见 §11 第 1 步） |
| worker | 0 active / 0 orphan；调度器锁 absent |
| 测试基线 | 294 passed |
| 今日成本 | $0.31（96+ calls，全部 deepseek/deepseek-v4-pro 初翻） |
| 剩余工作量 | ch248-613 ≈ 366 章 ≈ 122 个 D-MR ≈ 预计 $4-5、≈20 小时纯翻译时间 |
| 已知 P2 | agent_gate warn `vector_index_health`（历史遗留，与调度器无关） |
| 闸门提醒 | FS-010（Phase A 收尾）与 FS-038 / FS-050 是闸门轮；FS-038/FS-050 需用户确认 |

## 11. 批量推进操作手册（FS-008 实战验证，后续 Agent 直接照做）

### 11.1 恢复推进（交接后第一件事）

```bash
# 1. 状态确认（必须 orphan CLEAN、无 active worker）
python3 scripts/check_orphan_workers.py --json
python3 scripts/local_scheduler_status.py --json

# 2. 清除交接 pause（这是上一个 Agent 留的保护态）
python3 -c "
import sys; sys.path.insert(0, 'src')
from scheduler.control import clear_pause
print('cleared:', clear_pause())"

# 3. 重新确认 safe_to_run=true 后开始循环
```

### 11.2 标准批量循环（一个 Milestone Block = 5 个 tick slot）

```bash
for i in 1 2 3 4 5; do
  echo "=== B<N> MR $i start $(date -u +%H:%M:%SZ) ==="
  python3 scripts/local_scheduler_tick.py --real-api --max-api-calls 30 --max-wall-time-minutes 40 --json > /tmp/tick_bN_$i.json 2>&1
  rc=$?
  st=$(python3 -c "import json;print(json.load(open('/tmp/tick_bN_$i.json'))['status'])" 2>/dev/null || echo parse_fail)
  plan=$(python3 -c "import json;d=json.load(open('/tmp/tick_bN_$i.json'));print(d['plan']['round_id'] if d.get('plan') else '-')" 2>/dev/null || echo -)
  echo "B<N> MR $i: exit=$rc status=$st plan=$plan"
  if [ $rc -ne 0 ] || [ "$st" != "completed" ]; then echo "B<N>_STOP_AT_$i"; break; fi
  python3 scripts/check_orphan_workers.py --json | python3 -c "import sys,json; d=json.load(sys.stdin); sys.exit(0 if d['decision']=='CLEAN' else 1)" || { echo "B<N>_ORPHAN_AT_$i"; break; }
  echo "B<N> MR $i: orphan CLEAN"
done; echo "B<N>_LOOP_END"
```

要点：
- **后台启动 + 周期轮询**（每 4-5 分钟看一次终端输出 / 侧查最新 run 的 `run_progress.json`）。
- 普通 MR（~300-560 段）一个 tick 完成（9-15 分钟）；**大 MR（如 D-MR-015 有 1562 段）需 2-3 个 tick**——budget 耗尽时 tick 仍报 completed，下个 slot 由 planner `find_resumable_run` 同 offset 自动续跑，这是正常行为不是 bug。
- 决策表自动跳过已完成章节区，无需手工指定 round。

### 11.3 每个 Block 结束后（强制）

```bash
# 健康检查（FS-009 式）
python3 scripts/throughput_gate.py --json   # 期望 WARN 且只有 refine_pending / diagnostic_* 类
python3 scripts/check_orphan_workers.py --json
python3 -c "  # failed 必须为 0
import json, glob
fails = sum(int(json.load(open(p)).get('failed_segments') or 0) for p in glob.glob('workspace/runs/run_*/run_progress.json'))
print('TOTAL failed:', fails)"
# 成本累计（写入轮次报告）
python3 -c "
import json, glob
print(round(sum(float(json.load(open(p)).get('spent_usd') or 0) for p in glob.glob('workspace/checkpoints/run_*.json')), 4))"
```

然后：更新 `docs/final_state_round_task_list.md` 的 FS-008/FS-009 注记 → 写 `reports/latest-agent-report.json` + 追加 `reports/agent_audit_log.jsonl` → `validate_agent_report.py` PASS → commit + push（见 11.5）。

### 11.4 实战坑清单（本会话踩过，勿重蹈）

1. **commit 用 `git commit -F <消息文件>`**，不要用 heredoc 内嵌消息——heredoc 形式在本环境曾让 shell 卡死 4 分钟（无任何输出，git 进程不存在）。消息文件写到 `.git/COMMIT_MSG_*.txt`，用完删除。
2. **Shell spawn 报 "Execution backend unavailable" 不代表命令没跑**——先查 `workspace/control/scheduler_running.lock` 持有者与 `ps`，确认后再决定重试，否则会撞 `skipped_lock_held`。
3. **永不 kill -9 worker**。优雅停止 = `request_pause`（挡新 tick）+ `translation.stop_control.request_stop`（让运行中 worker 在下个 heartbeat 存盘退出）→ 等锁释放 → `clear_stop_request`（一次性信号，pause file 才是持续暂停）。
4. tick exit 2 = blocked：先看 `workspace/control/tick_reports/` 最新 json 的 `execution.stderr_tail`，再 `throughput_gate --json` 看 `blocks`。gate BLOCK 修复后 tick 直接重试即可。
5. **绝不把不同章节窗口 hydrate 进已有 run 目录**（FS-002 / FS-008 两次数据事故根因；现已有三防线代码拦截，若再遇 `hydrate refused` 报错 = 防线生效，开 fresh run 而不是绕过）。
6. `workspace/archived_runs/`、`workspace/runs/` 等真实数据：保持未跟踪，不 add、不删、不改写历史窗口。
7. 全套测试目前 294 passed 是基线；任何代码改动后 `npm run test:py` 必须不低于此。

### 11.5 提交模板

```bash
git status --short && git diff --stat && git diff --check
git add <仅本轮文件 + 任务清单 + reports 三件套>
git commit -F .git/COMMIT_MSG_XXX.txt && rm .git/COMMIT_MSG_XXX.txt
git push origin main
```

commit message 风格：`feat(scope): FS-XXX 中文摘要` 或批量轮 `feat(pipeline): Phase A Block #N（D-MR-xxx…yyy，章节 a-b）`+ 要点列表。

### 11.6 后续轮次衔接

- 批量期间每 Block 重复 FS-009 健康检查；S3（configs 资产层 FS-011…）可在等待 API 的间隙穿插推进（Roadmap §3 允许并行）。
- 613/613 完成 → FS-010 Phase A 收尾闸门（completion check + draft 导出 + 报告）。
- FS-038（baseline lock）、FS-050（production_candidate）到达时**停止等用户确认**。

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
