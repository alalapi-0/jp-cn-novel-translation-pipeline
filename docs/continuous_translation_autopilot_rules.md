# Continuous Translation Autopilot Rules

## Supervised execution mode（强制）

真实 API 初翻/润色必须经 **supervised mode** 运行：

```bash
python3 scripts/translation_autopilot_loop.py \
  --phase draft \
  --round-id T-002 \
  --round-size 20 \
  --real-api \
  --supervised
```

### 核心规则

1. **Agent 停止 → worker 必须停止**（`stop_requested.json` + SIGTERM + checkpoint 落盘）。
2. **禁止** `nohup` / 裸 `&` / `disown` 启动无人监管的真实 API 翻译。
3. 子进程必须记录 `controller_pid` / `controller_run_id`（见 `pipeline_worker_registry`）。
4. `throughput_gate` 对 **orphan API worker**（无存活 controller）返回 **BLOCK**。
5. Agent 正常结束前须确认无 active/orphan worker。

### Stop signal

路径：`workspace/control/stop_requested.json`

Worker 在 batch 前/后、API call 前检查；controller 退出时写入并 SIGTERM 子进程。

### 轮次衔接（无需用户确认）

- T-00N → T-00(N+1) 自动衔接
- 每 20 章初翻报告 → 修复 → commit
- 全书初翻完成 → 一致性检查 → baseline → 润色

### 需要用户确认

- 删除原文/大量译文、覆盖人工校对、外部发布、`human_approved_final`
- 大幅提高 `MAX_TEST_COST_USD`
- 并行多个真实 API worker
