# Throughput Optimization Task List

## P0

### P0-1：改造 Stage C refine runner，解除 30 segment pilot 上限

- 对应问题：Stage C 每次最多 30 segment、内部 4 segment 串行，导致 150 章润色产生数千次请求和大量 CLI 循环。
- 目标：把 Stage C 从 pilot CLI 改成可恢复的受控批次 runner，支持按 token / segment 动态组批、可配置 limit、失败批次拆小、进度持续落盘。
- 修改范围：`scripts/refine_stage_c.py`、`src/translation/refine_runner.py`、相关测试、吞吐文档。
- 具体修改步骤：
  1. 新增参数 `--limit-segments` 允许生产窗口配置大于 30，但默认保持低风险值。
  2. 将 `STAGE_C_MAX_SEGMENTS` 改为配置项，并加入 cost guard / controlled run 前置检查。
  3. 将 `REFINE_BATCH_SIZE=4` 改为按 token 上限组批，保留最大 segment 数兜底。
  4. 每完成一个 batch 写入 progress metadata，不等整个 run 结束。
  5. 失败时记录 `error_type`，同批最多重试后拆小，而不是直接终止整轮。
- 验收标准：
  - dry-run 下可一次处理超过 30 个候选 segment。
  - 真实 API 默认仍被 `REAL_API_TESTS_ENABLED=false` 阻止。
  - 中断后可从 progress metadata 恢复，不重复处理已 refined segment。
- 测试命令：
  - `python3 scripts/refine_stage_c.py --run-id <fixture-run> --limit-segments 60 --dry-run --json`
  - `.venv/bin/pytest tests/test_refine_stage_c.py -q`（若环境可用）
  - `python3 scripts/diagnose_throughput.py`
- 风险：提高批量后可能增加单次请求失败代价；必须保留拆小和 cost guard。
- 不做事项：不直接跑 500/600 章；不绕过 Validator；不提交真实译文。
- 建议 commit message：`fix: improve refine stage throughput controls`

### P0-2：建立唯一 worker registry，阻止重复启动 pipeline

- 对应问题：日志出现重复 `pilot_batch_chain start`、大量 `already running`、锁等待和残留 lock。
- 目标：同一阶段、同一 run_id / offset 同时只能有一个活跃 worker；重复启动应快速退出并给出结构化原因。
- 修改范围：`scripts/pilot_batch_chain.sh`、可能新增 `scripts/pipeline_worker_registry.py`、`.agent_runtime/status.json` 或 `workspace/pipeline_state.json`。
- 具体修改步骤：
  1. 设计 `workspace/pipeline_state.json`，记录 worker_id、pid、stage、run_id、offset、started_at、heartbeat_at。
  2. 启动 translate/refine 前检查 registry 和 lock，pid 存活则退出并写 `already_running`。
  3. heartbeat 超时且 pid 不存在时清理 stale registry，不直接删除未知 lock。
  4. watchdog 只读 registry，不重复启动同一任务。
  5. 将 `already_running` 计数写入诊断指标。
- 验收标准：
  - 连续启动两次同一命令，第二次结构化退出，不产生新 worker。
  - stale lock 能被识别并报告，不误杀活进程。
  - `production_pipeline.log` 不再每轮刷屏 `already running`。
- 测试命令：
  - `python3 scripts/diagnose_throughput.py`
  - 新增单测：`PYTHONPATH=src .venv/bin/pytest tests/test_pipeline_worker_registry.py -q`
- 风险：registry 判断错误可能阻止合法恢复；需保守处理 pid 存活判断。
- 不做事项：不自动 kill 用户进程；不删除真实运行产物。
- 建议 commit message：`fix: prevent duplicate pipeline workers`

### P0-3：修复 checkpoint、run_metadata、stage_state 对齐

- 对应问题：第 4 个 Stage B checkpoint 仍 `in_progress` 且 completed_segments=3871，但 run 目录缺少可统计 `segments.json` / `run_metadata.json`；`stage_state.json` 仍指旧 refine run。
- 目标：任何进行中的 run 都能被诊断脚本、runner 和后续恢复逻辑可靠识别。
- 修改范围：`src/translation/draft_runner.py`、`scripts/translate.py`、`scripts/refine_stage_c.py`、`scripts/diagnose_throughput.py`、测试。
- 具体修改步骤：
  1. 在 draft/refine 每个 batch 后写 `run_progress.json`，包含 run_id、stage、chapter_offset、completed_segments、pending_segments、last_error。
  2. `stage_state.json` 只记录全局当前阶段，不被旧 refine pilot 覆盖新生产 run。
  3. `diagnose_throughput.py` 从 checkpoint + progress 双源识别 in_progress run。
  4. 对缺失 `segments.json` 的 in_progress run 标为 `recoverable_missing_artifacts`。
  5. 增加恢复前检查，禁止在 metadata 不一致时直接扩到下一批。
- 验收标准：
  - 中断中的 run 可在 summary 里显示 stage、offset、完成 segment、下一动作。
  - 已完成 run 的 checkpoint、run_metadata、segments 计数一致。
  - `stage_state.json` 不再长期指向已完成的旧 run。
- 测试命令：
  - `python3 scripts/diagnose_throughput.py`
  - `PYTHONPATH=src .venv/bin/pytest tests/test_translation_pipeline.py -q`
- 风险：错误地重写 stage_state 可能影响当前 worker；只允许通过受控函数写入。
- 不做事项：不手工拼接真实译文；不把 checkpoint 伪装成完整 run。
- 建议 commit message：`fix: align pipeline progress metadata`

### P0-4：暂停盲目扩章并增加吞吐 gate

- 对应问题：在第 4 个 50 章尚未稳定完成时继续 500/600 章会扩大不可观测状态。
- 目标：每次生产推进前先检查吞吐、锁、checkpoint、metadata、cost guard 和 hard blocker。
- 修改范围：`scripts/diagnose_throughput.py`、`scripts/agent_gate.py` 或新增轻量 `scripts/throughput_gate.py`、文档。
- 具体修改步骤：
  1. 新增 gate：若存在 in_progress checkpoint 但缺 run artifacts，返回 WARNING/BLOCKED。
  2. 若 `.locks` 指向死 pid，返回 WARNING 并提示人工确认。
  3. 若 `stage_state.refine_blocked=true` 且 run 已完成，返回 WARNING。
  4. gate 输出下一步建议：resume、repair metadata、or stop。
- 验收标准：
  - 当前仓库状态能被 gate 标为“不建议继续 500/600 章”。
  - 无真实 API 调用。
  - 报告不包含正文/译文。
- 测试命令：
  - `python3 scripts/diagnose_throughput.py`
  - `python3 scripts/throughput_gate.py`（若新增）
  - `python3 scripts/agent_gate.py`
- 风险：gate 过严可能阻塞合法小规模恢复；需支持 `--json` 和明确 override 流程。
- 不做事项：不把 gate 设计成自动修复真实产物。
- 建议 commit message：`feat: add throughput safety gate`

## P1

### P1-1：补最小 pipeline timing instrumentation

- 对应问题：除 provider latency 外，scan/parse/prompt/extractor/validator/export/git/CI 没有耗时数据。
- 目标：建立 `pipeline_events.jsonl`，记录每个步骤耗时和结果，不保存正文。
- 修改范围：`src/translation/draft_runner.py`、`src/translation/refine_runner.py`、`src/providers/router_provider.py`、`scripts/diagnose_throughput.py`。
- 具体修改步骤：
  1. 新增轻量 context manager：`timed_step(run_id, stage, step)`。
  2. 写入字段：run_id、stage、step、started_at、finished_at、duration_ms、status、error_type、count。
  3. 对 provider 外的 parse、prompt build、extractor、validator、exporter 包一层计时。
  4. 诊断脚本汇总平均/最慢耗时。
- 验收标准：
  - dry-run 产生 `workspace/pipeline_events.jsonl`。
  - 报告能显示每步骤耗时。
  - 事件不包含 source_text、draft_text、refined_text。
- 测试命令：
  - `python3 scripts/run_round_50_e2e_trial.py`
  - `python3 scripts/diagnose_throughput.py`
- 风险：频繁写文件可能有少量 IO 开销；可按 batch 写入。
- 不做事项：不引入数据库或重型 tracing。
- 建议 commit message：`feat: record pipeline timing events`

### P1-2：补 model_run request_hash 与 started_at

- 对应问题：6795 个 model_run 都缺少 `request_hash` 和 `started_at`，无法识别重复请求。
- 目标：真实 provider 写入完整 metadata，支持重复请求审计和后续 cache 设计。
- 修改范围：`src/providers/router_provider.py`、`src/providers/openrouter_provider.py`、`src/providers/types.py`、测试。
- 具体修改步骤：
  1. 对 messages + options 计算脱敏 request_hash。
  2. 写入 started_at、finished_at、latency_ms、request_hash、prompt_version。
  3. 只记录 hash 和长度，不记录正文。
  4. 诊断脚本统计重复 request_hash 比例。
- 验收标准：
  - 新 model_run 文件包含 started_at 和 request_hash。
  - 单测验证不包含 message content。
  - 真实 API 默认仍被 cost guard 阻止。
- 测试命令：
  - `.venv/bin/pytest tests/test_openrouter_provider.py tests/test_model_router.py -q`
  - `python3 scripts/run_real_api_smoke.py --status-only`
- 风险：hash 输入字段变化会影响去重判断；需固定版本。
- 不做事项：本任务不启用自动 cache hit 复用。
- 建议 commit message：`feat: add model run request hashes`

### P1-3：统一 retry / error taxonomy

- 对应问题：429、timeout、API error、parse fail、validation fail、lock busy、manual stop 分散在日志中，无法统计比例。
- 目标：所有失败和重试写入统一 error_type。
- 修改范围：provider、draft/refine runner、worker registry、diagnose script。
- 具体修改步骤：
  1. 定义 error_type 枚举：`rate_limited`、`timeout`、`network_error`、`parse_failed`、`validation_failed`、`lock_busy`、`cost_guard_blocked`、`manual_stop` 等。
  2. 捕获异常时写入 run progress 和 pipeline event。
  3. retry 记录 attempt、max_attempts、backoff_ms。
  4. 诊断脚本输出失败/重试表。
- 验收标准：
  - 模拟 provider timeout 可统计为 `timeout`。
  - validation failed 不进入 success。
  - 报告显示 retry_pending / failed / validation_failed。
- 测试命令：
  - `PYTHONPATH=src .venv/bin/pytest tests/test_translation_pipeline.py -q`
  - `python3 scripts/diagnose_throughput.py`
- 风险：错误分类过细会增加维护成本；先保持小枚举。
- 不做事项：不吞掉原始异常摘要。
- 建议 commit message：`feat: classify pipeline retry errors`

### P1-4：生产窗口隔离 UI/Playwright 和治理检查

- 对应问题：Runner 同时做真实 API smoke、浏览器检查、治理推进和翻译生产，章节/轮偏低。
- 目标：生产翻译窗口只执行 pipeline health check 和当前 run 恢复，不穿插 UI/Playwright。
- 修改范围：`.agent_runtime/status.json` 规则、`scripts/agent.py` 或 runner 文档、任务队列策略。
- 具体修改步骤：
  1. 增加 `production_window=true` 时跳过非必要 browser inspection。
  2. 保留低频 health check，不启动前端。
  3. UI 问题进入队列，不阻塞翻译 run。
  4. 文档写明何时恢复浏览器验证。
- 验收标准：
  - 生产窗口内不会每 5 分钟触发浏览器检查。
  - 非 UI 任务不启动 Playwright。
  - 队列仍保留 UI 待办，不丢失。
- 测试命令：
  - `python3 scripts/agent.py status`
  - `python3 scripts/diagnose_throughput.py`
- 风险：可能延迟发现 UI 展示问题；生产翻译不依赖 UI 时可接受。
- 不做事项：不删除已有 inspection report。
- 建议 commit message：`chore: isolate production pipeline checks`

## P2

### P2-1：实现只读重复请求审计

- 对应问题：当前无法判断是否重复翻译同一内容。
- 目标：在 request_hash 可用后统计重复请求，不自动复用。
- 修改范围：`scripts/diagnose_throughput.py`、文档。
- 具体修改步骤：
  1. 汇总 request_hash 频次。
  2. 输出重复 top N，不显示正文。
  3. 按 run_id / stage / model 统计重复率。
- 验收标准：
  - 报告出现重复请求比例。
  - 不输出 prompt 或正文。
- 测试命令：
  - `python3 scripts/diagnose_throughput.py`
- 风险：hash 字段缺失时只能显示缺少数据。
- 不做事项：不启用自动跳过请求。
- 建议 commit message：`feat: audit duplicate model requests`

### P2-2：优化 draft batch sizing

- 对应问题：初翻 `MAX_SEGMENTS_PER_BATCH=8` 可能导致每章请求数偏高。
- 目标：按 token 估算动态组批，在安全 token 上限内减少请求数。
- 修改范围：`src/translation/draft_runner.py`、prompt builder、测试。
- 具体修改步骤：
  1. 根据 source char/token 估算构建 batch。
  2. 记录每章 batch 数和 tokens。
  3. 对 parse/validation fail 的 batch 拆小。
- 验收标准：
  - dry-run 显示平均每章请求数下降。
  - validation 失败时不写入成功译文。
- 测试命令：
  - `PYTHONPATH=src .venv/bin/pytest tests/test_translation_pipeline.py -q`
- 风险：大 batch 可能降低模型结构化输出稳定性。
- 不做事项：不取消 segment coverage 校验。
- 建议 commit message：`perf: tune draft batch sizing`

### P2-3：完善 refine validator

- 对应问题：refine 阶段只有解析覆盖检查，缺少质量/格式验证。
- 目标：把 refine 输出也纳入基础 validator，避免错误扩章。
- 修改范围：`src/translation/refine_runner.py`、`src/translation/validator.py`、测试。
- 具体修改步骤：
  1. 复用 segment coverage、non_empty、length_ratio。
  2. 添加 refined_text 不得为空、不得丢 segment_id。
  3. 失败写入 `validation_failed`，进入 retry_pending。
- 验收标准：
  - 模拟缺 segment 的 refine 输出不会写入 refined_text。
  - 诊断报告能统计 validation_failed。
- 测试命令：
  - `.venv/bin/pytest tests/test_refine_stage_c.py -q`
- 风险：门禁过严会增加 retry；先只加基础规则。
- 不做事项：不引入人工质量评分模型。
- 建议 commit message：`test: validate refine output coverage`

## P3

### P3-1：设计 LLM response cache

- 对应问题：重复请求无法复用，长篇成本和耗时不可控。
- 目标：在 request_hash 和质量状态稳定后，设计只对完全相同请求启用的 response cache。
- 修改范围：设计文档、后续 cache adapter。
- 具体修改步骤：
  1. 明确 cache key：source hash、prompt_version、model、glossary_version、style version。
  2. cache hit 只进入 extractor/validator，不直接进入 final。
  3. 先 dry-run 统计潜在 hit。
- 验收标准：
  - 文档明确 cache 不等于 TM，不绕过 Validator。
  - 有 cache invalidation 规则。
- 测试命令：
  - 文档审查 + 后续单测。
- 风险：错误复用会污染译文。
- 不做事项：本阶段不直接复用真实响应。
- 建议 commit message：`docs: design safe response cache`

### P3-2：生产吞吐 dashboard / HTML 报告

- 对应问题：Markdown 摘要够诊断，但不适合长期监控。
- 目标：基于诊断 JSON 生成只读 HTML 或 workbench 卡片。
- 修改范围：`frontend/` 或 `scripts/diagnose_throughput.py` 后续导出。
- 具体修改步骤：
  1. 读取 `workspace/diagnostics/throughput_metrics.json`。
  2. 展示章节/小时、失败率、active worker、in_progress run。
  3. UI 修改后用浏览器验证。
- 验收标准：
  - 页面无敏感内容。
  - 浏览器 smoke 通过。
- 测试命令：
  - `npm run test:ui`
- 风险：UI 工作会分散生产修复注意力。
- 不做事项：P0/P1 前不做。
- 建议 commit message：`feat: add throughput dashboard`

# Recommended Execution Order

## 下一轮建议执行

1. P0-3：先修复 checkpoint / run metadata / stage_state 对齐，弄清第 4 个 50 章是否可恢复。
2. P0-2：建立唯一 worker registry，阻止重复启动。
3. P0-1：改造 Stage C refine runner，扩大安全批量。
4. P0-4：把吞吐 gate 接入继续生产前检查。
5. P1-1、P1-2：补 timing 和 request_hash，形成可观测闭环。

## 暂不建议执行

- 不建议继续盲目跑 500/600 章。
- 不建议在 metadata 不一致时手工删除 lock 或 kill 进程。
- 不建议优先做 dashboard/UI。
- 不建议启用 response cache 自动复用。
- 不建议扩大真实 API 并发，直到 worker registry 和 cost guard 可验证。

## 如果继续慢，下一次应检查

- provider latency 是否集中在某个模型或某个时段。
- request_hash 重复率是否异常。
- validation_failed / parse_failed 是否集中在某些章节。
- 每章 segment 数和请求数是否异常高。
- checkpoint 写入频率是否拖慢 IO。
- agent 是否仍在生产窗口执行 UI/治理/CI 无关任务。
