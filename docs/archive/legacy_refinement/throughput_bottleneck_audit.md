# Throughput Bottleneck Audit

## 1. 审计目标

本轮目标是诊断连续推进约两天只产出约 150 章的主要原因，并形成可执行的修正任务。审计范围限定为只读诊断、低风险统计脚本和文档产出；不继续翻译、不调用真实 API、不跑 500/600 章、不读取或打印 `.env` 内容。

## 2. 当前观察

- `scripts/diagnose_throughput.py` 只读统计到：运行目录 7 个，checkpoint 8 个，model_run 6795 个。
- 当前可观测进度：初翻完成 160 章，润色完成 150 章；其中 Stage B 50 章批次完成 3 个，共 150 章。
- `workspace/checkpoints/run_20260605_111734_draft_stage_b_50ch.json` 仍为 `in_progress`，已完成 3871 个 segment，但对应 `workspace/runs/run_20260605_111734_draft_stage_b_50ch` 缺少可用 `run_metadata.json` / `segments.json`。
- `workspace/stage_state.json` 仍停在 `refine_stage_c_pilot`、`status=in_progress`、`refine_blocked=true`，且指向较早的 `run_20260602_203645_draft_stage_b_50ch`。
- `workspace/.locks/` 下仍有 `refine_stage_c_run_20260602_203645_draft_stage_b_50ch.lock` 和 `translate_stage_b_stage_b_default.lock`。
- 日志显示多次重复启动链路：`pilot_batch_chain start` 重复出现，且有 `translate lock busy`、`refine lock busy`、`already running`、`refine batch FAILED`。

## 3. 数据来源

- 必读文件：`AGENTS.md`、`README.md`、`governance/repo_protocol_standard.yaml`、`docs/agent_operating_manual.md`、`docs/governance_rules.md`、`docs/agent_tooling_strategy.md`、`docs/mcp_playwright_setup_plan.md`、`workspace/stage_state.json`。
- 缺失文件：`agent.md`、根目录 `repo_protocol_standard.yaml`、`docs/priority_matrix.md`、`docs/roadmap_converged_core_first.md`。
- 相关文档：`docs/cache_checkpoint_translation_memory_design.md`、`docs/provider_adapter_reference_inspired.md`、`docs/api_provider_strategy.md`、`docs/extractor_validator_reference_inspired.md`、`docs/agent_workflow/runner_agent.md`、`docs/agent_workflow/quality_gate.md`。
- 运行产物：`workspace/runs/`、`workspace/checkpoints/`、`workspace/model_runs/`、`workspace/refine_batch_log.txt`、`workspace/pilot_batch_chain.log`、`workspace/production_pipeline.log`、`workspace/watchdog_poll.log`、`.agent_runtime/status.json`、`.agent_runtime/queue.jsonl`、`.agent_runtime/blockers.jsonl`。
- 新增诊断：`python3 scripts/diagnose_throughput.py` 生成 `docs/throughput_metrics_summary.md` 和 `workspace/diagnostics/throughput_metrics.json`。
- 启动检查：已运行 `pwd`、`git status --short`、`git branch --show-current`、`python3 scripts/agent_gate.py`。
- 工具约束说明：用户原意中的 `find` / `grep` 用 `Glob`、`rg`、`ReadFile`、`ls` 和只读 Python 统计等价完成；未使用 shell `find` / `grep` / `cat` / `head` / `tail`。

## 4. 总体吞吐指标

| 指标 | 当前值 |
| --- | --- |
| 可观测运行时长 | 66.47 小时 |
| Runner round | 10 |
| run 目录数 | 7 |
| checkpoint 数 | 8 |
| model_run 数 | 6795 |
| 初翻完成章节 | 160 |
| 润色完成章节 | 150 |
| 初翻完成 segment | 13887 |
| 润色完成 segment | 13193 |
| 章节/小时（按初翻完成章） | 2.41 |
| 章节/轮（按初翻完成章） | 16.0 |
| 成功 commit/push 数 | 缺少结构化数据 |

结论：用户观察的“约两天约 150 章”与本地运行产物一致。当前不是没有真实 API 运行，而是运行组织和 telemetry 设计无法把产出稳定推进到下一批。

## 5. 分阶段吞吐指标

| 阶段 | 章节数 | 初翻完成章 | 润色完成章 | segment 数 | 初翻 segment | 润色 segment |
| --- | --- | --- | --- | --- | --- | --- |
| draft_stage_a_5ch | 15 | 10 | 0 | 1041 | 694 | 0 |
| draft_stage_b_50ch | 150 | 150 | 150 | 13193 | 13193 | 13193 |
| unknown | 0 | 0 | 0 | 0 | 0 | 0 |

阶段状态要求里的 `draft_stage_c_500ch`、`draft_stage_d_full`、`refine_stage_a_5ch`、`refine_stage_b_50ch`、`refine_stage_c_500ch`、`refine_stage_d_full` 没有对应结构化 run metadata。当前实际实现更接近 Stage A 5ch、Stage B 50ch、Stage C refine pilot（每次最多 30 segment）。

## 6. API / Provider 调用分析

| 指标 | 当前值 |
| --- | --- |
| provider 分布 | `openrouter=6792`，缺少数据 3 |
| model 分布 | `x-ai/grok-4.3=3568`，`deepseek/deepseek-v4-pro=3223`，`deepseek/deepseek-v4-flash=1`，缺少数据 3 |
| pipeline_stage 分布 | `refinement=3568`，`draft_translation=3223`，`openrouter_smoke=1`，缺少数据 3 |
| 平均 latency | 12292.69 ms |
| 最慢 latency | 216191 ms |
| token 总量 | 11066795 |
| model_run 估算 cost 总量 | 5.533398 USD |
| checkpoint 估算 cost 总量 | 部分 checkpoint 累计约 1.68 USD，run summary 当前聚合约 0.96 USD |

API 请求量偏大：150 个 Stage B 章节对应 6792 个真实 provider 记录，平均每章约 45 次模型调用。初翻侧 `MAX_SEGMENTS_PER_BATCH=8`，润色侧 `REFINE_BATCH_SIZE=4` 且 `STAGE_C_MAX_SEGMENTS=30`，这会把长篇处理拆成大量小请求。

## 7. Pipeline 环节耗时分析

| 环节 | 当前证据 |
| --- | --- |
| scan | 缺少计时 |
| parse | 缺少计时 |
| segment/chunk | 缺少计时 |
| context pack | 当前代码路径未体现真实 context pack 耗时 |
| prompt build | 缺少计时 |
| provider | 有 `latency_ms`，平均约 12.3 秒，最慢约 216 秒 |
| ResponseExtractor | 缺少计时 |
| Validator | 缺少计时 |
| quality review | `.agent_runtime/quality_reports` 为空，缺少质量轮耗时 |
| exporter | 缺少计时 |
| diff/change_log | 缺少计时 |
| git commit/push | 缺少结构化记录 |
| 前端/Playwright | inspection reports 13 个，但本轮非 UI 任务，不应成为继续翻译前置 |
| agent_gate | 本轮 `agent_gate` exit 1，WARNING；历史耗时缺失 |
| 测试/build | 缺少结构化耗时 |

结论：provider latency 是可见成本，但更大的工程问题是除 provider 外几乎没有 timing span，导致慢点只能从日志和脚本结构推断。

## 8. 失败、重试、重跑分析

- checkpoint 状态：`aborted=1`、`completed=6`、`in_progress=1`。
- Stage A 首次 run aborted：`OpenRouter network error: timed out`。
- `workspace/refine_batch_log.txt` 记录 `refine_stage_c already running`、`exit_fail batch 1`、`FAIL 137`。
- `workspace/pilot_batch_chain.log` 记录重复 `pilot_batch_chain start`、`translate lock busy`、`refine lock busy`，以及一次 `refine batch FAILED`。
- `workspace/production_pipeline.log` 中 `already running` 计数 204，说明外层 watchdog/runner 有大量重复启动或重复探测。
- `.agent_runtime/blockers.jsonl` 记录一次用户手动关闭 agent，后续再手动 unblock。

当前缺少统一 retry taxonomy，不能区分 429、timeout、API error、parse fail、validation fail、lock busy、manual stop 的比例。

## 9. 质量门禁分析

- `draft_quality_report.json` 对已完成 Stage B run 显示 `passed=true`、`stage_c_eligible=true`。
- `src/translation/validator.py` 目前只做非空、segment 覆盖、多余 segment、长度比等基础校验；未实现文档要求的 locked terms、placeholder、source residual、alignment 等完整门禁。
- `src/translation/refine_runner.py` 的 refine 阶段只通过 `extract_translations` 检查解析与覆盖，缺少独立的 refine validator 和质量失败 taxonomy。
- 当前不是“质量门禁过严导致无法推进”，反而更像“门禁过粗且 telemetry 不足”：失败时只留下较短 abort reason，成功时缺少足够质量指标，无法判断是否应该扩到 500/600 章。

## 10. Git / CI / 文件体积分析

- 初始工作树已经很脏，本轮遵守安全规则，只计划提交本轮新增文档、诊断脚本和测试。
- 运行产物很大但被 gitignore 隐藏：`workspace/model_runs` 约 6798 个目录项，`workspace/manifests` 约 128 个目录项，`workspace/runs` 有真实运行目录。
- `agent_gate` 本轮 WARNING，主要原因包括 working tree dirty 与 vector index warning，不是直接翻译吞吐瓶颈。
- 成功 commit/push 数缺少结构化数据；`.agent_runtime/status.json` 仅有 `last_successful_commit=1ba100e` 和 `last_push_branch=main`，不能还原两天内 commit/push 成功次数。

## 11. MCP / Playwright / 前端检查开销分析

- `.agent_runtime/inspection_reports` 有 13 个浏览器检查报告，`.agent_runtime/real_api_reports` 有 10 个真实 API smoke 报告。
- 本轮未修改 UI，不需要启动前端或 Playwright。
- 浏览器检查本身不是 150 章卡点的主因，但自动推进里 `browser_check_interval_minutes=5` 会产生频繁检查任务；如果翻译 worker 与检查任务争用 agent 注意力，会降低有效推进效率。

## 12. 并发与资源利用分析

- 翻译与润色靠 shell 脚本串行编排，锁粒度粗：`translate_stage_b_stage_b_default.lock` 和每个 refine run lock。
- `pilot_batch_chain.sh` 在完成或等待某个 offset 后才进入下一步，Stage B 批次之间没有安全并发。
- Stage C refine 的硬限制是每次最多 30 segment；内部每批 4 segment 串行调用。按当前完成 13193 个润色 segment 估算，需要数百次 refine CLI 调用和数千次 provider 调用。
- 日志证明存在多终端重复 worker 和锁等待，说明“并发不足”和“并发不安全”同时存在：系统没有一个权威调度器，只能靠锁和手动脚本避免冲突。

## 13. 主要卡点排名

### Bottleneck 1：Stage C refine 粒度过小且串行

- 证据：`STAGE_C_MAX_SEGMENTS=30`、`REFINE_BATCH_SIZE=4`；model_run 中 `refinement=3568`；日志中大量 `eligible` 每次下降 30。
- 影响：润色 150 章产生数千次请求和大量 CLI 循环，吞吐被小批量固定上限卡死。
- 根因：pilot 阶段限制未随生产批次调整，缺少“批次内安全扩大”和“按 token/章节动态分批”策略。
- 建议修正：把 Stage C 从固定 30 segment pilot 改成受控批次 runner，支持 dry-run 估算、按 token 上限自动组批、可配置 limit、失败批次拆小，不再要求每 30 segment 重新启动 CLI。

### Bottleneck 2：多 worker 重复启动与锁等待消耗推进时间

- 证据：`pilot_batch_chain.log` 多次重复 `pilot_batch_chain start`；`production_pipeline.log` 有 204 次 `already running`；`.locks` 中仍有 translate/refine lock。
- 影响：agent/终端把大量时间用于“发现已有进程、等待锁、重复 drain offset”，有效工作时间下降，也增加误判和人工干预风险。
- 根因：缺少唯一调度器和 worker registry；自动推进、watchdog、手动终端同时尝试启动相同任务。
- 建议修正：实现单一 `workspace/pipeline_state.json` 或扩展 `.agent_runtime/status.json`，记录 active worker、pid、阶段、heartbeat、run_id、offset；启动前先读 registry，禁止重复启动同阶段 worker。

### Bottleneck 3：checkpoint 与 run metadata 不一致

- 证据：`run_20260605_111734_draft_stage_b_50ch` checkpoint `in_progress` 且 completed_segments=3871，但 run 目录缺少可统计 metadata/segments；`stage_state.json` 仍指向旧 refine run。
- 影响：系统无法可靠判断第 4 个 50 章是否可恢复、是否可润色、是否已失败，导致推进停在 150 章附近。
- 根因：checkpoint 在 segment 级持续保存，但 run artifacts 只在正常结束或某些 abort 路径写出；stage_state 被后续 refine pilot 覆盖，缺少当前全局阶段视图。
- 建议修正：每 N 个 segment 写一次轻量 run progress；checkpoint、run_metadata、stage_state 使用同一 source of truth；诊断脚本作为 gate 前置检查。

### Bottleneck 4：缺少分环节 timing 与错误 taxonomy

- 证据：model_run 有 latency，但缺少 started_at、request_hash；scan/parse/prompt/extractor/validator/export/git/CI 均缺少耗时；错误只散落在日志。
- 影响：每次慢只能人工读日志，无法自动判定是 provider 慢、validator 慢、retry 多、锁等待还是 agent 做了无关事。
- 根因：早期只记录 provider 结果，未建立 pipeline span 和统一 error_type。
- 建议修正：新增只读/低侵入 timing instrumentation：`pipeline_events.jsonl`，字段包含 run_id、stage、step、started_at、finished_at、duration_ms、status、error_type、count，不保存正文。

### Bottleneck 5：真实 API 小测、浏览器检查和治理任务混入生产推进节奏

- 证据：`.agent_runtime/status.json` 中 `browser_check_interval_minutes=5`；real_api_reports=10、inspection_reports=13；runner round=10，但章节/轮只有 16。
- 影响：连续推进并非全部用于翻译/润色，有一部分 round 在修 UI、跑 smoke、处理工作台状态和治理检查。
- 根因：Runner Agent 职责包含浏览器检查、真实 API smoke、队列分派和生产推进，没有按生产窗口隔离。
- 建议修正：生产翻译窗口内只允许 pipeline worker + 最小 health check；UI/Playwright 和治理任务进入独立队列，不阻塞章节推进。

### Bottleneck 6：缺少 LLM response cache / request_hash 可用性

- 证据：6795 个 model_run 全部缺少 `request_hash`，model_run 文件也缺少 started_at。
- 影响：无法判断重复请求比例，也无法安全跳过同 prompt/同 segment 的重复调用。
- 根因：真实 provider 写入 model_run 时没有落 request_hash，缓存设计仍停留在文档阶段。
- 建议修正：先记录 request_hash，不立即启用复用；经过验证后再引入只读 cache hit 统计和显式 cache policy。

## 14. 非卡点说明

- `agent_gate` WARNING 不是主要吞吐卡点；本轮报告显示 fail=0、warn=2。
- 浏览器验证不是本轮必要工作；本轮未修改 UI，不需要启动前端。
- 当前没有证据显示 Git push/CI 是 150 章上限的直接原因；相关数据缺失，应补采但不应先优化。
- 当前没有证据显示质量门禁过严；更明显的问题是 refine 阶段门禁和 telemetry 不足。
- 当前不建议直接提升到 500/600 章，因为第 4 个 50 章仍 `in_progress` 且 run metadata 不完整。

## 15. 结论

连续推进慢的主因不是“API 完全没跑”，而是生产调度仍停留在 pilot 脚本形态：小批量串行、重复启动、锁等待、checkpoint/run metadata 不一致、分环节 telemetry 缺失。立即继续跑 500/600 章会扩大不可观测状态和重复调用风险。下一轮应先执行 P0/P1 修正：扩大并规范 Stage C runner、建立唯一 worker registry、修复 checkpoint/run metadata 对齐、补 timing/error taxonomy，再恢复小规模受控推进。
