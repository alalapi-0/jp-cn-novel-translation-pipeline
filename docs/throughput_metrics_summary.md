# Throughput Metrics Summary

## 当前统计时间

- 生成时间：2026-06-06T08:29:53.997864+00:00
- 统计方式：只读扫描 `workspace/runs`、`workspace/checkpoints`、`workspace/model_runs`、`.agent_runtime` 与轻量日志；不调用真实 API，不读取 `.env`，不输出正文/译文。

## 当前进度表

| 指标 | 值 |
| --- | --- |
| 总体运行轮数 | 10 |
| 运行目录数 | 7 |
| checkpoint 数 | 8 |
| model_run 文件数 | 6795 |
| 章节总数（run 内观测） | 165 |
| 初翻完成章节 | 160 |
| 润色完成章节 | 150 |
| 初翻完成 segment | 13887 |
| 润色完成 segment | 13193 |
| 观测运行时长（小时） | 66.47 |
| 章节/小时（按初翻完成章） | 2.41 |
| 章节/轮（按初翻完成章） | 16.0 |
| 成功 commit/push 数 | 缺少数据（需从 git log/remote 或自动化状态补采） |

## 每阶段吞吐表

| 阶段 | 章节数 | 初翻完成章 | 润色完成章 | segment 数 | 初翻 segment | 润色 segment |
| --- | --- | --- | --- | --- | --- | --- |
| draft_stage_a_5ch | 15 | 10 | 0 | 1041 | 694 | 0 |
| draft_stage_b_50ch | 150 | 150 | 150 | 13193 | 13193 | 13193 |
| unknown | 0 | 0 | 0 | 0 | 0 | 0 |

## API 指标表

| 指标 | 值 |
| --- | --- |
| provider 分布 | openrouter=6792, 缺少数据=3 |
| model 分布 | deepseek/deepseek-v4-flash=1, deepseek/deepseek-v4-pro=3223, x-ai/grok-4.3=3568, 缺少数据=3 |
| pipeline_stage 分布 | draft_translation=3223, openrouter_smoke=1, refinement=3568, 缺少数据=3 |
| status 分布 | ok=6792, 缺少数据=3 |
| 平均 latency_ms | 12292.69 |
| 最慢 latency_ms | 216191 |
| token 总量 | 11066795 |
| 估算 cost_usd 总量 | 5.533398 |
| 缺少 started_at 的 model_run | 6795 |
| 缺少 request_hash 的 model_run | 6795 |

### Provider 调用分布

| provider | model_run 数 |
| --- | --- |
| openrouter | 6792 |
| 缺少数据 | 3 |

### Pipeline Stage 调用分布

| pipeline_stage | model_run 数 |
| --- | --- |
| draft_translation | 3223 |
| openrouter_smoke | 1 |
| refinement | 3568 |
| 缺少数据 | 3 |

## Pipeline 耗时表

| 环节 | 当前数据 |
| --- | --- |
| scan | 缺少数据 |
| parse | 缺少数据 |
| segment/chunk | 缺少数据 |
| context pack | 缺少数据 |
| prompt build | 缺少数据 |
| provider | model_run latency 可用：avg=12292.69ms max=216191ms |
| ResponseExtractor | 缺少数据 |
| Validator | 缺少数据 |
| quality review | 缺少数据 |
| exporter | 缺少数据 |
| diff/change_log | 缺少数据 |
| git commit/push | 缺少数据 |
| 前端/Playwright | inspection_reports=13；缺少单次耗时 |
| agent_gate | 本轮运行产生 WARNING；缺少历史耗时 |
| 测试/build | 缺少结构化耗时 |

## 结论

- 当前最明确的卡点不是单一模型慢，而是 Stage C 每次最多 30 segment、每批 4 segment、串行执行，并且重试/锁/agent 轮次管理混在终端脚本里。
- 真实运行产物存在，但 telemetry 粒度不足，无法可靠回答 scan/parse/validator/git/CI 等分环节耗时；下一步应先补最小计时与错误 taxonomy。
- `workspace/stage_state.json` 仍显示 refine in_progress / refine_blocked=true，说明阶段状态没有稳定收敛到可继续扩章的状态。

## 下一步建议

- 先执行 P0：修复 Stage C 小批量串行瓶颈、统一 checkpoint/run telemetry、阻止多终端重复 worker。
- 暂停盲目继续 500/600 章，直到吞吐指标脚本能稳定显示章节/小时、失败率、重跑率和每环节耗时。
- 为 provider、extractor、validator、exporter 添加轻量 timing span，不改译文内容。

## 缺失数据与补采任务

- model_runs 缺少 started_at，无法精确计算每次请求完整耗时区间
- run_metadata.started_at 在写产物时生成，不能代表真实 run 开始时间
- 缺少 scan/parse/context_pack/prompt_build/validator/exporter/git/CI 的分环节计时
- 缺少每章请求数和 retry/error taxonomy 的统一结构化字段
- 缺少 push 成功次数的结构化记录，只能从 git/终端记录间接判断
