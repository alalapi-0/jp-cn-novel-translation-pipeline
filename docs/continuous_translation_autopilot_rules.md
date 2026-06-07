# Continuous Translation Autopilot Rules

## 执行单位：3 章 Micro Round（2026-06-07 起）

- **20 章/轮已废弃**；真实 API 执行单位改为 **3 章 micro round**（D-MR-XXX / R-MR-XXX）。
- 主路线图：`docs/translation_recovery_3ch_roadmap.md`
- 任务清单：`docs/translation_recovery_3ch_task_list.md`

## Supervised Tick Loop（强制）

真实 API 初翻/润色必须经 **supervised mode** + **tick loop** 运行：

```bash
python3 scripts/translation_autopilot_loop.py \
  --phase draft \
  --round-id D-MR-001 \
  --round-size 3 \
  --real-api \
  --supervised
```

续跑 partial checkpoint 示例：

```bash
python3 scripts/translation_autopilot_loop.py \
  --phase draft \
  --run-id run_20260607_095821_draft_stage_b_50ch \
  --round-size 3 \
  --real-api \
  --supervised
```

### 核心规则

1. **每个 tick 必须返回控制权给 Agent**——禁止长时间 foreground worker 独占 terminal。
2. **Agent 停止 → worker 必须停止**（`stop_requested.json` + SIGTERM + checkpoint 落盘）。
3. **禁止** `nohup` / 裸 `&` / `disown` 启动无人监管的真实 API 翻译。
4. **detached background worker 禁止**用于真实 API。
5. 子进程必须记录 `controller_pid` / `controller_run_id`（见 `pipeline_worker_registry`）。
6. `throughput_gate` 对 **orphan API worker**（无存活 controller）返回 **BLOCK**。
7. Agent 正常结束前须确认无 active/orphan worker；stale lock 须 `--heal`。

### Stop signal

路径：`workspace/control/stop_requested.json`

Worker 在 batch 前/后、API call 前检查；controller 退出时写入并 SIGTERM 子进程。

### Micro Round 衔接（无需用户确认）

- D-MR-00N → D-MR-00(N+1) 自动衔接（初翻）
- R-MR-00N → R-MR-00(N+1) 自动衔接（润色，baseline 后）
- 每 3 章 micro round 完成后：报告 → 修复 → gate →（授权时）commit → 下一 MR
- 全书初翻完成 → 渐进式一致性检查（Phase B）→ baseline lock → 润色 micro rounds → 渐进式质量检查（Phase E）

### 需要用户确认

- 删除原文/大量译文、覆盖人工校对、外部发布、`human_approved_final`
- 大幅提高 `MAX_TEST_COST_USD`
- 并行多个真实 API worker

### 3 章是执行单位，不代表每 3 章都要人工确认

无硬阻塞时 micro round 自动推进；仅 baseline lock、production_candidate、human_approved_final 等里程碑需明确决策。
