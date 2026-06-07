# Micro-Round Runner Design

> 2026-06-08 — 从「Agent → tick → Agent …」迁移到「Agent → micro-round runner → summary」

## 1. 问题陈述

旧 supervised tick loop（`translation_autopilot_loop.py`）每 **80 segment / 180s** 归还 Agent：

- 3 章 micro round 需 **10+ tick**，子进程与 gate 重复启动。
- `draft_runner` 固定 **8 segment/call**，API 次数线性膨胀。
- Agent 每 tick 读大段文档/feedback，但无法在一次会话内跑完 3 章。

## 2. 目标执行模型

```
Agent
  └─ run_micro_round.py  (supervised controller, 单进程)
        ├─ throughput_gate + orphan heal + lock
        ├─ optional hydrate_checkpoint
        └─ loop: run_draft_stage_b (planner batches)
              ├─ batch 1..N API calls
              ├─ checkpoint 每 batch
              ├─ micro_round_progress.json 每 30–60s
              └─ stop_requested → SIGTERM 链 → 无 orphan
        └─ compact summary JSON → stdout + workspace/logs/
Agent 读 summary → report / commit / 下一 MR
```

**不变约束：**

- Worker 仍注册 `pipeline_worker_registry`，`controller_pid` = runner PID。
- 禁止 detached background / nohup。
- Agent 停止时 `stop_requested.json` 生效。

## 3. CLI 接口

```bash
python3 scripts/run_micro_round.py \
  --phase draft \
  --round-id D-MR-003 \
  --chapter-range 209-211 \
  --run-id run_20260607_095821_draft_stage_b_50ch \
  --model-profile draft_translation_primary \
  --real-api \
  --supervised \
  --batch-token-budget 12000 \
  --max-segments-per-call 30 \
  --max-api-calls 30 \
  --progress-interval-seconds 30 \
  --resume-from-checkpoint
```

验证/限流参数：

| 参数 | 用途 |
|------|------|
| `--dry-run` | 仅 batch plan，不注册 worker / 不调 API |
| `--fake-provider` / `--no-real-api` | fake provider 流程验证 |
| `--diagnostic-only` | 隔离 `micro_validate_*` run_id，跳过 gate |
| `--max-api-calls` | 小规模验证上限（如 3） |
| `--max-segments` | 单次 runner 最多新译段数 |
| `--max-wall-time-minutes` | 墙钟预算 |
| `--stop-on-round-complete` | 3 章完成即停（默认开启） |
| `--skip-gate` | 仅诊断；生产默认跑 gate |

## 4. Batch Planner

脚本：`scripts/plan_translation_batches.py`

- 输入：ordered segments
- 约束：token budget 8k–16k；max 15–30 seg/call
- 长度分档决定 target batch size
- 输出：JSON plan（CLI `--json`）或供 `draft_runner` 内部调用
- **失败 batch**：`split_failed_batch()` 二分，仅重试失败半批

Dry-run 样例（ch209）：**8 batches，avg 19 seg/batch**（旧 8-seg 策略约 19 calls）。

## 5. Context Pack

| 层 | 内容 |
|----|------|
| System（静态） | `prompt_builder.SYSTEM_PROMPT` |
| User 前缀（动态） | chapter title、batch 首段摘要 |
| Glossary hits | `select_batch_context_hits()` 子串匹配，max ~8 terms |
| User 后缀 | segments JSON 契约 + source 文本 |

**禁止：** 全书 TM、world bible、roadmap 全量注入。

## 6. Thinking / Model

- Profile：`draft_translation` → `deepseek/deepseek-v4-pro`
- 无 reasoning/thinking 通道
- Nemotron candidate **disabled**（`config/draft_models.yaml`）

## 7. Progress & Checkpoint

| 文件 | 频率 |
|------|------|
| `workspace/runs/{run_id}/run_progress.json` | 每 segment flush 间隔 |
| `workspace/checkpoints/{run_id}.json` | 每 batch 后 `controlled.save()` |
| `workspace/runs/{run_id}/micro_round_progress.json` | 每 30–60s compact |
| `workspace/logs/micro_round_{round_id}_summary.json` | runner 退出时 |

Compact summary 字段：`progress`, `api_calls`, `segments_per_call_avg`, `cost_usd`, `budget`.

## 8. 与旧 Autopilot 关系

- `translation_autopilot_loop.py` **保留** 作为单 tick 兼容入口。
- 生产推荐：**Agent 启动一次 `run_micro_round.py`**，读 summary 后继续治理。
- Tick loop 仅用于 fallback 或极长 MR 人工切片。

## 9. 验收清单

- [x] checkpoint 续跑跳过已完成 segment
- [x] 每 call segment ≥15（短章；末批可 <15）
- [x] extractor 稳定；失败 batch 二分不 abort 全书
- [x] validator 通过（fake provider）
- [x] stop signal 后无新 API call
- [x] exit 无 orphan worker
- [x] compact progress 可供 Agent 读取

## 10. Safe Resume 命令

```bash
python3 scripts/pipeline_worker_registry.py --heal
python3 scripts/check_orphan_workers.py --json
python3 scripts/run_micro_round.py \
  --round-id D-MR-004 \
  --run-id run_20260607_222525_draft_stage_b_50ch \
  --real-api --supervised \
  --batch-token-budget 12000 \
  --max-segments-per-call 30 \
  --resume-from-checkpoint
```

（round-id / run-id 以 `throughput_gate --json` 的 `run_analysis` 为准。）
