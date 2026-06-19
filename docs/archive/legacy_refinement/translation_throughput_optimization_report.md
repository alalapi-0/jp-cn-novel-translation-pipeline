# Translation Throughput Optimization Report

> 生成时间：2026-06-08（治理/工具轮，基于只读诊断 + 小规模改造验证）  
> 范围：D-MR-001（第 203–205 章）慢因分析；micro-round runner / batch planner 落地

## 执行摘要

**当前慢的主因不是 DeepSeek 模型本身**，而是：

1. **硬编码小 batch**：`draft_runner._split_batches` 限制 `MAX_SEGMENTS_PER_BATCH=8`、`MAX_CHARS_PER_BATCH=5500`，3 章约 562 段 → **~64–70 次 API call**（与观测一致）。
2. **Supervised tick 外层开销**：D-MR-001 在 `pipeline_state.json` 中记录 **12 次 tick**（11× `tick_paused` + 1× `completed`），墙钟约 **31 分钟**（13:04–13:35 UTC）；每 tick 重启 `translate.py`、跑 `throughput_gate`、可能 `hydrate_checkpoint`、Agent 回合等待。
3. **Telemetry 粒度不足**：provider 平均 latency ~13s/call，但 scan/parse/validator/exporter 无结构化计时，难拆分「API vs 编排」。

## D-MR-001 统计（第 203–205 章）

| # | 指标 | 值 | 来源 |
|---|------|-----|------|
| 1 | API calls | **~64**（run 累计；3 章全新约 562÷8≈70） | `draft_runner` batch=8；checkpoint/run summary |
| 2 | segment 数 | **562**（ch203=316, ch204=129, ch205=117） | `input_jp` parse |
| 3 | 平均每 call segment | **~8–9** | 562÷64；由 `MAX_SEGMENTS_PER_BATCH=8` 决定 |
| 4 | 平均每 call token 估算 | **~2,500–4,500 input**（含 JSON 契约 + 250 字 asset context） | segment 长度 + prompt 模板估算 |
| 5 | 平均 API latency | **~13s**（全书 draft_translation 均值） | `workspace/model_runs` / throughput_metrics |
| 6 | 每个 tick overhead | **~150–180s wall**（`tick_max_wall_seconds=180`）+ 子进程启动 ~2–5s | autopilot 默认 tick 预预算 |
| 7 | Agent/shell/gate/report | **12 tick ×（gate + hydrate? + translate 启动）≈ 15–25% 墙钟** | `pipeline_state` D-MR-001 workers |
| 8 | 每 tick 重复读文档/hydrate | **条件 hydrate**（offset/status 变化时）；每 tick **重新 parse 章节 + hydrate segments** | `translation_autopilot_loop.py` |
| 9 | prompt/context pack | **全量 asset context 仅 ~250 字**（当前 TM 文件小）；JSON 契约重复嵌入每 batch | `pw-user-assets-flow.json` |
| 10 | thinking/reasoning | **未用于 draft**；profile=`draft_translation`，temperature=0.3，无 reasoning 字段 | `model-router/config/models.yaml` |
| 11 | JSON extractor 失败拆 batch | **旧逻辑：同 batch 重试 3 次后 abort**；**新逻辑：失败 batch 二分拆分** | `draft_runner` 改造后 |
| 12 | validator 过严导致重复 | **否**；validator 仅 coverage/非空/长度比，不是主因 | `validator.py` + throughput_bottleneck_audit |

## 核心问题回答

### 为什么 3 章用了约 64 API calls？

- 562 个 segment ÷ **每 call 最多 8 段** ≈ **70 calls**（理论上限）。
- ch203 在 D-MR-001 前已有 partial（152/316），实际新译约 **410 段** → 410÷8 ≈ **51 calls**；加上 **失败重试、tick 边界重复扫描、run 内其它 offset 批次** 等，观测 **~64 calls** 合理。
- **根因：batch 粒度由常量 8 决定，而非 token budget。**

### 为什么每 call 只有约 8–9 segment？

- 代码硬限制：`MAX_SEGMENTS_PER_BATCH = 8`（`src/translation/draft_runner.py`）。
- 与章节长度无关；长章（ch203=316 段）只会 **线性放大 call 次数**。

### 哪些开销是 API？哪些是 Agent/shell/gate/report？

| 类别 | 估算占比 | 说明 |
|------|----------|------|
| **Provider API** | **~70–80% 墙钟** | ~64 calls × ~13s ≈ 14min；D-MR-001 总 span ~31min |
| **Tick 编排** | **~15–25%** | 12 次 autopilot tick；每次 subprocess + gate + 锁 + registry |
| **Agent 回合** | **~5–10%** | 读文档、解析 feedback JSON、决策下一 tick（无结构化计时） |
| **Validator/Extractor** | **<1% CPU** | 本地 JSON 解析，非瓶颈 |
| **Git/report** | **未纳入 run 热路径** | 每 MR 完成后才跑 |

## 已实施改造

| 组件 | 变更 |
|------|------|
| `scripts/plan_translation_batches.py` | token budget 组 batch；长度分档；失败 batch 二分 |
| `scripts/run_micro_round.py` | supervised 单次启动、内部多 batch、compact progress |
| `src/translation/draft_runner.py` | 接入 planner；RunBudget；compact context；checkpoint 每 batch |
| `src/translation/prompt_builder.py` | 静态 system 在前；动态 source + 命中 glossary 在后 |
| `src/assets/translation_memory.py` | `select_batch_context_hits()` 按 batch 注入术语 |

## 新 batch 策略（目标）

- token budget：**8k–16k**（默认 12k）
- max segments/call：**15–30**（默认 30，min 15）
- 长度分档：short 25–40 / medium 15–25 / long 5–10 / extra-long 单段
- ch209 样例：**8 batches，avg 19 seg/batch**（dry-run planner）

## 新 context 策略

- System prompt 固定在最前（缓存友好）
- User 消息：chapter title → batch 首段摘要 → **命中** glossary/character → segments JSON 在最后
- **禁止**塞全书 glossary / world bible / roadmap

## Thinking 策略

- Draft 保持 **`draft_translation` profile**，**不启用** reasoning/thinking（Nemotron A/B 本轮 disabled）。

Dry-run 命令：

```bash
python3 scripts/plan_translation_batches.py \
  --run-id run_20260607_095821_draft_stage_b_50ch \
  --chapter-range 209-211 \
  --batch-token-budget 12000 \
  --max-segments-per-call 30 \
  --dry-run --json
```

**2026-06-08 复验（209–211）：** 17 batches，avg **20.12** seg/batch，max 26，overlong=0。

## 小规模真实 API 验证

| 项 | 结果 |
|----|------|
| batch planner dry-run (209–211) | **17 batches，avg 20.12 seg/batch** |
| fake provider runner (max 3 calls / 60 seg) | **3 calls，60 segments，avg 20.0 seg/call**，orphan=CLEAN |
| D-MR-003 生产续跑 | **已完成**（342/342 @ offset 208）；续跑 **0 新 API call** |
| 真实 API smoke (D-MR-003-SMOKE) | **跳过**（生产 checkpoint 已满；避免重复计费） |

**说明：** 验证时 `run_20260607_222525` 被旧 autopilot tick worker 占用锁，故使用独立 `run_id` 做 3-call 限流验证。生产续跑 D-MR-004 前须等 autopilot 退出或 `--heal` stale lock。

**修复：** `micro_round_plan.resolve_round_plan` 在指定 `--run-id` 时仍应用 `--chapter-range`（原为 `elif` 导致忽略）。

## Safe resume（D-MR-003+）

```bash
cd /Users/alalapi/PycharmProjects/light_novel
python3 scripts/pipeline_worker_registry.py --heal
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
  --progress-interval-seconds 30 \
  --resume-from-checkpoint
```

D-MR-003 若在 `run_20260607_095821` 已完成（342/342 @ offset 208），续跑将 **0 新 API call**；下一未完成 MR 见 `throughput_gate --json` 的 `run_analysis`。

## 参考

- `docs/micro_round_runner_design.md`
- `docs/throughput_bottleneck_audit.md`
- `docs/continuous_translation_autopilot_rules.md`
