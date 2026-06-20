# Continuous Translation Execution Rules

> v2.0（2026-06-18）。旧 3 章 D-MR/R-MR autopilot 路线已归档；当前主线见 `docs/translation_production_protocol.md`。

## 执行单位

生产翻译执行单位由当前 v2 任务决定，可以是：

* 一个受控 chapter range；
* 一个 segment batch；
* 一个 scheduler tick 计划出的单任务。

不再把 3 章 R-MR 作为固定生产单位。

## Supervised Tick Loop（强制）

外部真实 API 翻译必须经 supervised mode + tick loop 运行，并满足：

1. pause file 不存在；
2. scheduler lock 可获取；
3. no active worker；
4. no orphan worker；
5. cost guard 生效；
6. budget 有上限；
7. 子进程绑定 `controller_pid` / `controller_run_id`。

Agent 额度翻译也必须返回控制权给 Agent，不得长时间无人监管。

## 禁止

* `nohup` / 裸 `&` / `disown` 启动无人监管真实 API 翻译；
* detached background worker 用于生产翻译；
* 自动进入 refinement / R-MR；
* 自动生成 production_candidate 作为终点；
* 绕过一致性检查直接写 final。

## Stop Signal

路径：`workspace/control/stop_requested.json`

Worker 在 batch 前/后、API call 前检查；controller 退出时写入并 SIGTERM 子进程。

## 衔接规则

```text
translation batch
→ report
→ consistency audit / local fix
→ baseline lock
→ singleton final export
```

无硬阻塞时可继续下一受控 batch；baseline lock、singleton final export、human_approved_final 等里程碑需明确记录。

## 需要用户确认

* 删除原文 / 大量译文；
* 覆盖人工校对；
* 外部发布；
* `human_approved_final`；
* 大幅提高 `MAX_TEST_COST_USD`；
* 并行多个真实 API worker；
* 更换生产模型。
