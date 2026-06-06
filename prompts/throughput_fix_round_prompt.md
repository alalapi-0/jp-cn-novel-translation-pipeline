# Throughput Fix Round Prompt

你是当前仓库 `/Users/alalapi/PycharmProjects/light_novel` 的吞吐修复执行 Agent。必须使用简体中文产出。

## 本轮目标

先执行 `docs/throughput_optimization_task_list.md` 中的 P0/P1 修正任务，修复连续推进吞吐慢、metadata 不一致、重复 worker 和缺少 telemetry 的问题。

## 明确禁止

- 不要继续盲目翻译。
- 不要启动 500/600 章大规模真实 API。
- 不要跑完整长篇。
- 不要读取或打印 `.env` 内容。
- 不要提交 `.env`、API key/token/cookie、真实原文、真实译文、pyc、大型缓存或 workspace 运行产物。
- 不要在没有 worker registry 和 throughput gate 的情况下扩大并发。
- 不要为了 UI 展示启动 Playwright；除非本轮修改了前端。

## 必读文件

1. `AGENTS.md`
2. `README.md`
3. `governance/repo_protocol_standard.yaml`
4. `docs/agent_operating_manual.md`
5. `docs/governance_rules.md`
6. `docs/agent_tooling_strategy.md`
7. `docs/throughput_bottleneck_audit.md`
8. `docs/throughput_optimization_task_list.md`
9. `docs/throughput_metrics_summary.md`
10. `workspace/stage_state.json`
11. `workspace/diagnostics/throughput_metrics.json`（若存在）

缺失文件记录为 soft blocker，不要停止。

## 开始前必须执行

```bash
pwd
git status
git branch --show-current
python3 scripts/agent_gate.py
python3 scripts/diagnose_throughput.py
```

如果 `agent_gate` 返回 WARNING，记录原因；只有 FAIL 或安全风险才停止。

## 优先执行顺序

### 第一优先：P0-3

修复 checkpoint、run_metadata、stage_state 对齐。

- 让 in-progress run 能被诊断脚本识别 stage、offset、completed_segments、pending_segments、next_action。
- 增加 progress metadata，避免只有 checkpoint 没有 run artifacts。
- 不要手工改真实译文内容。

### 第二优先：P0-2

建立唯一 worker registry。

- 防止重复启动同一 translate/refine worker。
- 不自动 kill 用户进程。
- stale lock 只报告或在确认 pid 不存在后按安全流程处理。

### 第三优先：P0-4

新增或扩展 throughput gate。

- 在继续生产前检查 in-progress checkpoint、缺失 artifacts、stage_state 卡旧 run、残留 lock。
- 当前状态应明确提示“不建议继续 500/600 章”。

### 第四优先：P0-1

改造 Stage C refine runner。

- 先用 dry-run fixture 验证可处理超过 30 segment。
- 真实 API 默认必须被 cost guard 阻止。
- 保留失败拆小和 checkpoint。

### 第五优先：P1-1 / P1-2

补最小 timing instrumentation、model_run started_at / request_hash。

- 不记录正文、译文、prompt 全文或敏感 header。
- 诊断报告能展示缺失数据减少。

## 验收标准

- `python3 scripts/diagnose_throughput.py` 通过。
- 新增或修改的测试通过；如果环境缺依赖，记录原因。
- `python3 scripts/agent_gate.py` 至少无 FAIL；WARNING 需说明。
- `docs/throughput_metrics_summary.md` 更新。
- 不调用真实 API；如误触 cost guard，应停止并报告。
- `git diff` 中不包含 `.env`、密钥、真实原文/译文、大型 workspace 产物。

## 建议提交范围

只提交本轮相关源码、测试、文档和 prompt。不要使用 `git add .`。

建议提交信息按实际任务选择，例如：

- `fix: align pipeline progress metadata`
- `fix: prevent duplicate pipeline workers`
- `feat: add throughput safety gate`
- `feat: record pipeline timing events`

## 最终报告格式

最终回复必须包含：

1. 本轮修复了哪些 P0/P1 项。
2. 当前诊断指标变化。
3. 运行的测试命令和结果。
4. 仍不建议继续做的事。
5. 下一轮建议。
