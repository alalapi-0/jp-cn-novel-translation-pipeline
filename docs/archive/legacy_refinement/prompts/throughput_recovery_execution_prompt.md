# Throughput Recovery And Real API Diagnostic Execution Prompt

你是仓库 `/Users/alalapi/PycharmProjects/light_novel` 的吞吐恢复、生产安全修复与真实 API 小规模诊断 Agent。

本轮是一次有边界的代码修复与真实 API 小规模诊断轮，不是连续翻译轮，不是生产翻译轮。必须使用简体中文沟通和输出。

---

## 一、本轮唯一目标

修复当前翻译流水线的调度、状态一致性、阶段性导出、可观测性和吞吐恢复问题，并使用真实 API 做小规模、隔离、可审计的诊断测试，确认修复是否真的改善了真实调用路径。

本轮目标不是继续推进旧的 600 章生产翻译。
本轮目标不是继续产出大量章节。
本轮目标不是恢复旧 worker 后继续跑。
本轮目标是让项目在未来恢复真实 API 生产前，满足以下条件：

1. 同一 translate/refine 任务只能有一个权威 worker。
2. checkpoint、run progress、run metadata、stage state 能一致描述当前进度。
3. watchdog 不再误判存活进程，不再反复重启和刷 `already running`。
4. 每个已完成且已润色的 50 章 run 可以阶段性、幂等地导出，不再等待全部 613 章完成。
5. throughput gate 能阻止状态不一致时继续扩章。
6. Stage C refine 不再依赖“每次最多 30 segment、每批 4 segment”的 pilot 循环。
7. 新增 telemetry 不保存原文、译文、Prompt 全文或敏感信息。
8. 真实 API 小规模诊断测试可以安全执行，并且与旧生产翻译 run 完全隔离。
9. 真实 API 诊断测试不得推进生产 stage，不得污染已有 checkpoint，不得覆盖 baseline draft，不得写入正式输出目录。
10. 完成本轮修复、真实 API 小规模验证、测试和报告后必须停止。禁止自动进入下一轮，禁止自我唤醒，禁止循环调用 Agent。

---

## 二、已知事实与基线

开始前以本地文件重新验证，但不要重新做一轮泛化诊断。

已知基线：

* 当前诊断基线：初翻完成约 160 章，润色完成约 150 章。
* 已存在约 6795 个 `workspace/model_runs/*.json`。
* 前三个 Stage B 50 章 run 已完成 draft 和 refine，合计 150 章。
* 第四个 run 的 checkpoint 曾处于 `in_progress`，但 run artifacts、stage state 和 checkpoint 不一致。
* `workspace/stage_state.json` 曾长期指向旧的 `refine_stage_c_pilot`。
* `scripts/pilot_batch_chain.sh` 只在全部 613 章完成后调用：

```bash
scripts/export_refined_runs.py --require-refined
```

* 因此 `output_cn` 长期为空并不代表没有翻译结果，而是缺少阶段性 export。
* `scripts/production_watchdog.sh` 使用 `set -o pipefail` 和：

```bash
echo "$ps_out" | grep -qE ...
```

`grep -q` 提前退出可能令 `echo` 收到 broken pipe，使存活检查返回错误，导致 watchdog 误判并反复尝试重启。

* watchdog 的 `draft_progress` 还硬编码了旧 run id，显示的进度可能不是当前 run。
* 当前 Stage C refine 实现仍带有 pilot 限制：每次最多 30 segment，内部 4 segment 串行。

权威诊断文件：

1. `docs/throughput_bottleneck_audit.md`
2. `docs/throughput_optimization_task_list.md`
3. `docs/throughput_metrics_summary.md`
4. `scripts/diagnose_throughput.py`

---

## 三、本轮真实 API 使用原则

本轮必须允许并优先使用真实 API 做小规模诊断测试。

但真实 API 只能用于：

1. 验证 provider 调用链路是否正常。
2. 验证真实模型请求耗时、失败率、retry、timeout、rate limit 记录是否正确。
3. 验证 progress writer、model run metadata、telemetry、throughput gate 是否能记录真实调用。
4. 验证修复后的 batch / checkpoint / export / validator 在真实 API 小样本下能正常闭环。
5. 验证吞吐瓶颈是否来自真实 API、batch size、prompt size、review 过重、retry 过多或状态冲突。

真实 API 不得用于：

1. 继续旧生产 pipeline。
2. 自动恢复 600 章翻译。
3. 自动进入 50 / 500 / 613 章生产阶段。
4. 覆盖旧 run。
5. 覆盖 baseline draft。
6. 写入正式 `output_cn` / `output_refined` / `output_final`。
7. 推进 `workspace/stage_state.json` 的生产阶段。
8. 把诊断结果伪装成生产译文。
9. 生成大量新 model runs。
10. 无成本上限地测试。

---

## 四、真实 API 诊断测试边界

如果本地已有 API Key，必须执行真实 API 小规模诊断测试。
如果没有 API Key，则必须记录“真实 API 诊断无法执行”，并只完成 dry-run / fake-provider 验证。

真实 API 测试必须满足以下边界：

### 4.1 真实 API 测试规模上限

默认上限：

```text
max_real_api_chapters = 1
max_real_api_segments = 10
max_real_api_batches = 3
max_real_api_retry_per_batch = 1
max_real_api_wall_time_minutes = 15
```

如需扩大，必须满足：

1. throughput gate 为 ALLOW 或明确可隔离测试。
2. cost guard 明确允许。
3. 只扩大到诊断所需范围。
4. 不超过：

```text
max_real_api_segments = 30
max_real_api_batches = 5
```

本轮严禁真实 API 执行：

```text
50 章
500 章
600/613 章
全书
```

### 4.2 真实 API 测试必须使用隔离 run

真实 API 诊断 run 必须使用独立 run_id：

```text
run_YYYYMMDD_HHMMSS_realapi_diagnostic_translate
run_YYYYMMDD_HHMMSS_realapi_diagnostic_refine
```

输出必须放入：

```text
workspace/diagnostics/real_api_runs/<run_id>/
```

不得写入：

```text
workspace/runs/<production_run_id>/
output_cn/
output_refined/
output_final/
draft_full_baseline/
refined_full_candidate/
```

除非是只读检查。

### 4.3 真实 API 测试不得污染生产状态

真实 API 诊断测试：

1. 不得推进生产 `stage_state.json`。
2. 不得把诊断 run 写成 active production run。
3. 不得覆盖旧 checkpoint。
4. 不得写入旧 run 的 `segments.json`。
5. 不得修改旧 run 的 `run_metadata.json`。
6. 不得把诊断输出标记为 `completed` production run。
7. 不得被 exporter 当作正式输出来源。
8. 必须明确标记：

```json
{
  "run_type": "diagnostic_real_api",
  "production_eligible": false,
  "isolated": true
}
```

### 4.4 真实 API 测试必须记录成本与耗时

每个真实 API 诊断 model run 必须记录：

* provider
* model
* model_run_id
* run_id
* phase
* stage
* started_at
* finished_at
* duration_ms
* retry_count
* error_type
* estimated_input_tokens
* estimated_output_tokens
* actual_usage，如 provider 返回
* estimated_cost，如可计算
* request_hash
* request_hash_version
* prompt_version

不得记录：

* API Key
* Authorization header
* Cookie
* Prompt 全文
* 原文全文
* 译文全文
* 敏感 header

允许记录：

* segment_count
* chapter_count
* hash
* truncated preview，最多 80 字，且默认关闭
* error taxonomy
* timing metrics

---

## 五、硬性安全边界

本轮必须遵守：

* 不启动旧的 `production_pipeline.sh` 进行生产翻译。
* 不启动旧的 `pilot_batch_chain.sh` 继续大规模生产翻译。
* 不启动旧的 `production_watchdog.sh` 让它接管真实生产。
* 不继续旧翻译任务。
* 不跑 50 / 500 / 600 / 613 章。
* 不读取、打印或修改 `.env` 内容；只允许检查 API Key 是否存在，不得输出值。
* 不自动 kill 任何活进程。
* 不手工删除 lock；只能识别、报告并通过测试 fixture 验证 stale 判定。
* 不修改真实原文、真实译文和现有 workspace run 内容。
* 不把 checkpoint 伪装成 completed run。
* 不把不完整 segment 导出为 final。
* 不启用 response cache 自动复用。
* 不做 UI dashboard，不启动前端，不跑 Playwright。
* 不安装大型依赖。
* 不使用 `git add .`。
* 不 commit 或 push，除非用户在本轮明确授权。
* 不反复运行 `agent_gate`、全量测试或诊断脚本；开始和结束各最多一次，针对性测试除外。

如果发现必须停止活跃生产进程才能安全修改或验证，立即停止本轮并报告，不要自行 kill。

如果发现真实 API worker 仍存活：

1. 记录 PID。
2. 记录阶段。
3. 记录 run id。
4. 不启动。
5. 不重启。
6. 不 kill。
7. 停止涉及运行时状态写入的验证。
8. 仍可做只读诊断、fixture 测试和隔离代码修复。

---

## 六、开始前检查

按仓库治理顺序读取必要文件，避免全量扫描大目录，禁止扫描 `.git/`、`node_modules/`、`.venv/`、`.cursor/`、`cache/`、`logs/`。

至少读取：

1. `AGENTS.md`
2. `governance/repo_protocol_standard.yaml`
3. `project.yaml`
4. `governance/agent_policy.yaml`
5. `governance/round_state.yaml`
6. `docs/agent_operating_manual.md`
7. `docs/governance_rules.md`
8. `docs/throughput_bottleneck_audit.md`
9. `docs/throughput_optimization_task_list.md`
10. `prompts/throughput_recovery_execution_prompt.md`

只执行一次：

```bash
pwd
git status --short
git branch --show-current
python3 scripts/agent.py status
python3 scripts/diagnose_throughput.py
python3 scripts/agent_gate.py
```

要求：

* 工作树可能已有用户或其他 Agent 的改动，不得回滚。
* `agent_gate` 的 working-tree WARNING 不是硬阻塞。
* 如果发现真实 API worker 仍存活，只记录 PID、阶段和 run id，不启动、不重启、不 kill，并停止涉及运行时状态写入的验证。
* 如果 API Key 存在，不得打印 Key；只记录 `api_key_available: true`。

---

## 七、执行顺序

严格按以下顺序执行。P0 未通过前不要做 P1/P2。
真实 API 诊断必须在 P0 核心安全修复完成后执行。
不要在状态系统未修复前执行真实 API 测试。

---

### P0-A：统一进度状态与恢复语义

目标：checkpoint 是 segment 完成记录，run progress 是实时运行状态，run metadata 是稳定 run 身份，stage state 是全局当前阶段。四者职责明确且可校验。

要求：

1. 优先复用现有模块和数据结构，不重复创建多个状态系统。
2. 为 draft/refine 增加统一的原子 progress writer。
3. 每个 batch 完成后写入轻量 `run_progress.json`，至少包含：

   * `schema_version`
   * `run_id`
   * `phase`
   * `stage`
   * `chapter_offset`
   * `status`
   * `total_segments`
   * `completed_segments`
   * `pending_segments`
   * `last_completed_segment_id`
   * `last_error_type`
   * `started_at`
   * `heartbeat_at`
   * `updated_at`
4. 使用临时文件加原子替换，避免中断留下半截 JSON。
5. `run_metadata.json` 必须在 run 开始时就存在，不得只在结束/abort 时生成。
6. `stage_state.json` 不得被较旧 run 覆盖较新的 active run。
7. 状态迁移至少支持：

   * `pending`
   * `in_progress`
   * `completed`
   * `failed`
   * `aborted`
   * `blocked`
8. 诊断脚本应识别：

   * `recoverable_in_progress`
   * `recoverable_missing_artifacts`
   * `completed_consistent`
   * `state_conflict`
9. 不修改现有真实 run 来伪造一致性；使用 fixture 测试修复逻辑。

---

### P0-B：修复唯一 worker registry 与 watchdog

目标：只存在一个权威调度判断，watchdog 只根据 registry、PID 和 heartbeat 做保守判断。

要求：

1. 实现或完善 `workspace/pipeline_state.json` 对应的 registry helper。
2. registry 至少记录：

   * `worker_id`
   * `pid`
   * `task_type`
   * `stage`
   * `run_id`
   * `chapter_offset`
   * `started_at`
   * `heartbeat_at`
   * `status`
3. 同一 `task_type + stage + run_id/offset` 重复启动时，第二个 worker 结构化退出。
4. PID 存活且 heartbeat 合理时视为 active。
5. PID 不存在且 heartbeat 超时才可标记 stale；本轮不自动 kill，不自动删除未知 lock。
6. 修复 `production_watchdog.sh` 的 broken-pipe 误判：

   * 不再使用会受 `pipefail + grep -q` 影响的 `echo "$ps_out" | grep -q`。
   * 优先读取 registry/PID file。
   * shell fallback 必须有单测或可重复的 shell 测试。
7. 删除 watchdog 中硬编码旧 run id 的进度逻辑，改为读取 active registry/run progress。
8. watchdog 每次轮询不得重复启动已存活 pipeline。
9. 不通过频繁轮询日志文本判断任务是否完成；完成状态应来自结构化状态。

---

### P0-C：新增 throughput gate

目标：任何真实生产恢复前都先给出明确的 `ALLOW / BLOCK / WARN`。

建议新增 `scripts/throughput_gate.py`，支持普通输出和 `--json`。

必须检查：

1. 是否存在 active worker。
2. 是否存在重复 active worker。
3. checkpoint 与 run progress 计数是否冲突。
4. completed run 是否缺少 `run_metadata.json` 或 `segments.json`。
5. `stage_state.json` 是否指向旧 run。
6. lock PID 是否存活，是否与 registry 对应。
7. 是否存在未完成的上一 offset，却准备启动下一 offset。
8. cost guard 默认是否阻止未授权的大规模真实 API。
9. 当前可阶段性导出的 completed/refined chapter 数。
10. 是否允许隔离真实 API 诊断 run。

退出码约定：

* `0`：ALLOW，仅表示结构和状态允许，不代表自动启动生产 API。
* `1`：WARN，可以做只读诊断、dry-run 或隔离真实 API 诊断，不允许扩章生产。
* `2`：BLOCK，状态冲突或安全风险，禁止启动生产。除非能证明隔离真实 API 诊断不触碰生产状态，否则也禁止真实 API 诊断。

当前历史 fixture 应能被识别为 WARN 或 BLOCK，不得错误显示 ALLOW。

---

### P0-D：实现阶段性、幂等 export

目标：每个 completed 且 fully refined 的 run 完成后即可导出，不等待全书完成。

要求：

1. 扩展 `scripts/export_refined_runs.py`，支持按 `--run-id`、`--up-to-offset` 或等价明确范围导出。
2. 默认继续排除：

   * 缺 draft/refined 的 segment
   * `validation_failed`
   * `failed`
   * `retry_pending`
3. `--require-refined` 语义保持严格。
4. 导出必须幂等；重复运行不得重复章节或破坏排序。
5. 使用原子写入。
6. 不覆盖明确标记为 human-edited 或人工维护的现有文件；冲突时报告并退出。
7. `pilot_batch_chain.sh` 的未来流程改为：

   * 一个 50 章 run 完成并 fully refined
   * throughput gate 通过
   * 执行该 run 的阶段性 export
   * 再进入下一 offset
8. 本轮先用临时 fixture 验证，不对真实 `output_cn` 执行导出。
9. 导出 summary 至少包含：

   * `runs_considered`
   * `runs_exported`
   * `chapters_exported`
   * `chapters_skipped`
   * `conflicts`
   * `output_paths`

---

### P0-E：把 Stage C 从 pilot 循环改成受控 runner

只有 P0-A 到 P0-D 通过后才执行。

要求：

1. 默认值仍保持低风险，不因改造自动提高真实 API 批量。
2. `STAGE_C_MAX_SEGMENTS` 改为配置上限，CLI 可在 dry-run fixture 中处理超过 30 segment。
3. 按 token/字符预算动态组 batch，并保留最大 segment 数上限。
4. 每完成一个 batch 写 progress 和 heartbeat。
5. parse/validation 失败时先记录 error taxonomy，再按策略拆小。
6. 不允许失败 batch 的部分结果污染 refined success 状态。
7. 已有 `refined_text` 的 segment 不重复调用。
8. 保留 cost guard、controlled run 和断点恢复。
9. dry-run 下验证 60+ segment，不调用网络。

---

### P0-F：真实 API 小规模诊断测试

只有 P0-A 到 P0-E 通过，并且 throughput gate 不为 BLOCK 时才执行。

目标：用真实 API 验证修复后的调用链路、metadata、telemetry、progress、error taxonomy 和 cost guard，不推进生产翻译。

要求：

1. 检查 API Key 是否存在，但不得打印 Key。
2. 检查 cost guard 是否启用。
3. 创建隔离诊断 run：

```text
workspace/diagnostics/real_api_runs/<run_id>/
```

4. 使用真实 API 执行极小规模 translate 诊断：

   * 最多 1 章
   * 最多 10 segment
   * 最多 3 batch
   * 最多 1 次 retry
5. 如 refine provider 已可用，执行极小规模 refine 诊断：

   * 最多 5 segment
   * 必须基于诊断 draft，而不是生产 baseline
6. 必须记录：

   * real API latency
   * provider error
   * retry
   * token usage
   * estimated cost
   * model_run metadata
   * telemetry event
   * throughput gate 诊断结论
7. 不得写入正式 `workspace/runs/`。
8. 不得写入正式 output。
9. 不得更新生产 `stage_state.json` 为 completed。
10. 不得把诊断 run 纳入可导出的 production run。
11. 诊断输出必须标记：

```json
{
  "run_type": "diagnostic_real_api",
  "production_eligible": false,
  "real_api_used": true
}
```

12. 如果真实 API 失败，本轮不算失败；必须判断失败类型：

* `rate_limited`
* `timeout`
* `network_error`
* `provider_error`
* `parse_failed`
* `validation_failed`
* `cost_guard_blocked`
* `state_conflict`

13. 真实 API 失败也必须产出诊断报告。

输出：

```text
workspace/diagnostics/real_api_runs/<run_id>/real_api_diagnostic_report.md
workspace/diagnostics/real_api_runs/<run_id>/real_api_diagnostic_report.json
```

---

### P1：最小 telemetry 与错误分类

P0 全部通过后再做最小实现，不扩展成大型 observability 系统。

新增不含正文的 `pipeline_events.jsonl`，字段至少包括：

* `schema_version`
* `event_id`
* `run_id`
* `worker_id`
* `stage`
* `step`
* `started_at`
* `finished_at`
* `duration_ms`
* `status`
* `error_type`
* `attempt`
* `batch_segments`
* `estimated_tokens`
* `api_mode`: `fake` / `dry_run` / `real_api`
* `production_eligible`: true / false

统一最小 error taxonomy：

* `rate_limited`
* `timeout`
* `network_error`
* `provider_error`
* `parse_failed`
* `validation_failed`
* `lock_busy`
* `worker_already_running`
* `cost_guard_blocked`
* `state_conflict`
* `manual_stop`

为新生成的 model run metadata 增加：

* `started_at`
* `finished_at`
* `request_hash`
* `request_hash_version`
* `prompt_version`
* `api_mode`
* `production_eligible`

`request_hash` 只用于审计，本轮不得启用自动 cache hit。

---

## 八、测试要求

测试不得使用真实原文、真实译文或真实 `output_cn`。
但本轮必须在隔离目录中使用真实 API 做小规模诊断测试，前提是 API Key 存在且 cost guard 允许。

至少覆盖：

1. run 开始即生成 metadata/progress。
2. batch 后 progress 原子更新。
3. checkpoint/progress 不一致被 gate 捕获。
4. 旧 run 不能覆盖新 active stage state。
5. 相同 worker 启动两次，第二次结构化退出。
6. stale registry 仅在 PID 不存在且 heartbeat 超时时识别。
7. watchdog 在 `pipefail` 下能正确识别存活进程。
8. watchdog 进度来自 active run，不依赖硬编码 run id。
9. completed/refined fixture 可阶段性导出。
10. 不完整/validation failed fixture 不进入 final。
11. 重复 export 幂等。
12. human-edited 文件冲突不覆盖。
13. refine dry-run 可处理超过 30 segment。
14. request hash 稳定且 model run 不包含 Prompt/正文。
15. 真实 API 诊断 run 能写入隔离目录。
16. 真实 API 诊断 run 不改变 production stage_state。
17. 真实 API 诊断 run 不进入正式 exporter。
18. 真实 API 诊断 telemetry 不包含正文、译文、Prompt 全文或敏感 header。

优先运行针对性测试：

```bash
PYTHONPATH=src .venv/bin/pytest \
  tests/test_diagnose_throughput.py \
  tests/test_pipeline_worker_registry.py \
  tests/test_throughput_gate.py \
  tests/test_translation_pipeline.py \
  tests/test_refine_stage_c.py \
  tests/test_export_refined_runs.py -q
```

如果某个测试文件不存在，按实际实现新增。不要因为缺单个文件而改跑无边界的长时间测试。

真实 API 诊断测试命令可以新增，例如：

```bash
python3 scripts/run_real_api_diagnostic.py --max-chapters 1 --max-segments 10 --isolated
```

如果仓库已有等价命令，优先使用已有命令。

结束时只运行一次：

```bash
python3 scripts/diagnose_throughput.py
python3 scripts/throughput_gate.py --json
python3 scripts/agent_gate.py
git diff --check
git status --short
```

---

## 九、验收门槛

本轮只有同时满足以下条件才算完成：

1. 未启动、重启或 kill 生产进程。
2. 未继续旧生产翻译。
3. 未跑 50 / 500 / 600 / 613 章。
4. 真实 API 只用于小规模隔离诊断 run。
5. 真实 API 诊断 run 没有污染生产 stage_state、checkpoint、baseline 或正式输出。
6. watchdog 存活检测测试通过，不再出现 broken-pipe 误判。
7. 同任务重复 worker 被阻止。
8. 状态冲突能被 throughput gate 捕获。
9. 阶段性 exporter 在 fixture 上成功且幂等。
10. exporter 不会导出失败或不完整 segment。
11. refine dry-run fixture 可处理超过 30 segment 并可恢复。
12. telemetry 不包含正文、译文、Prompt 全文或敏感 header。
13. 真实 API 诊断报告存在，或明确说明 API Key 缺失 / cost guard 阻止。
14. 目标测试通过；未通过项必须明确列为 blocker，不得伪装完成。
15. `git diff` 不包含 `.env`、密钥、真实原文/译文或 workspace 大型运行产物。
16. 不自动开始下一轮。

---

## 十、允许修改范围

优先限制在：

* `scripts/diagnose_throughput.py`
* `scripts/throughput_gate.py`
* `scripts/pipeline_worker_registry.py`
* `scripts/production_watchdog.sh`
* `scripts/pilot_batch_chain.sh`
* `scripts/translate.py`
* `scripts/refine_stage_c.py`
* `scripts/export_refined_runs.py`
* `scripts/run_real_api_diagnostic.py`
* `src/translation/`
* `src/providers/`
* 对应 `tests/`
* `docs/throughput_*`
* `governance/round_state.yaml`
* `prompts/throughput_recovery_execution_prompt.md`

不要顺手修改前端、Playwright、无关治理文件或业务文案。

---

## 十一、最终报告格式

最终回复必须简洁列出：

1. 已完成的 P0/P1 项。
2. 修改文件。
3. 测试命令与结果。
4. 真实 API 诊断是否执行。
5. 真实 API 诊断 run_id。
6. 真实 API 诊断规模：

   * chapters
   * segments
   * batches
   * retries
   * estimated cost
7. throughput gate 最终结论。
8. 是否仍存在 active worker 或状态冲突。
9. 当前有多少章可阶段性导出。
10. 是否允许恢复小规模生产。
11. 未解决问题和下一步。

最后明确写出以下四者之一：

* `DECISION: BLOCK_PRODUCTION`
* `DECISION: ALLOW_DRY_RUN_ONLY`
* `DECISION: READY_FOR_USER_APPROVED_SMALL_PILOT`
* `DECISION: REAL_API_DIAGNOSTIC_PASSED_BUT_PRODUCTION_STILL_REQUIRES_USER_APPROVAL`

不得自行恢复大规模真实 API 生产。
不得自行开始下一轮。
不得自行跑 50 / 500 / 600 / 613 章。
