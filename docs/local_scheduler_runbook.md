# Local Scheduler Runbook（本地调度器运维手册）

> 对应规格：`docs/product_final_state_spec.md` §9；建设轮次：FS-001…FS-007（S1）。
> 适用对象：在本机维护翻译流水线调度器的用户与 Agent。
> 原则：**dry-run 是默认态；真实 API 模式永远是显式手动开启的例外。**

---

## 1. 组件总览

| 组件 | 文件 | 作用 |
| --- | --- | --- |
| 控制协议 | `src/scheduler/control.py` | pause file 读写、tick 互斥锁获取/释放/stale 判定 |
| 状态聚合 | `src/scheduler/status.py` + `scripts/local_scheduler_status.py` | 规格 §9.2 的 13 字段状态 JSON |
| 单次 tick | `src/scheduler/tick.py` + `scripts/local_scheduler_tick.py` | 一次"决策→执行→落盘"循环 |
| 任务决策表 | `src/scheduler/task_planner.py` | Phase → 下一任务映射 + run_micro_round 命令行渲染 |
| launchd 集成 | `scripts/local_scheduler_launchd.sh` + `scripts/launchd/*.plist.template` | 周期 tick 安装/卸载/状态 |
| 锁治理 | `scripts/heal_stale_locks.py` | dead-pid 残留锁清理（dry-run 默认） |

关键状态文件（均在 gitignore 内）：

```
workspace/control/scheduler_paused.json      # pause file（存在且 paused:true = 暂停）
workspace/control/scheduler_running.lock     # tick 互斥锁（JSON：pid/owner/host）
workspace/control/scheduler_tick_state.json  # last_successful_tick / last_blocked_reason
workspace/control/tick_reports/tick_*.json   # 每次 tick 的完整报告
workspace/logs/scheduler/scheduler_tick.log  # launchd 周期 tick 日志（含时间戳与退出码）
workspace/.locks/*.lock                      # translate/refine flock 残留文件
```

---

## 2. 安装与卸载（launchd 周期 tick）

```bash
# 预览将要发生什么（不落盘、不加载）
bash scripts/local_scheduler_launchd.sh install --dry-run

# 安装（默认 900 秒一个 dry-run tick；间隔可用 SCHEDULER_INTERVAL_SECONDS 覆盖）
bash scripts/local_scheduler_launchd.sh install
SCHEDULER_INTERVAL_SECONDS=600 bash scripts/local_scheduler_launchd.sh install

# 查看状态（plist 是否存在、launchd 是否加载、最近 tick 日志）
bash scripts/local_scheduler_launchd.sh status

# 立即触发一次（不等周期）
launchctl kickstart gui/$(id -u)/com.lightnovel.translation.scheduler

# 卸载（幂等：重复执行安全）
bash scripts/local_scheduler_launchd.sh uninstall
```

要点：

- plist 由模板渲染到 `~/Library/LaunchAgents/`，**不含密钥**；launchd 环境只有显式 PATH 与 WorkingDirectory。
- 安装后的 tick **固定 dry-run**（见 `cmd_run_tick`）；改真实模式见 §6。
- install 幂等：已加载时自动 bootout 再 bootstrap。

---

## 3. 暂停与恢复

暂停（任何真实 API 工作必须立即让位）：

```bash
python3 - <<'PY'
import sys; sys.path.insert(0, 'src')
from scheduler.control import request_pause
print(request_pause(reason="manual_maintenance", requested_by="user"))
PY
```

恢复：

```bash
python3 - <<'PY'
import sys; sys.path.insert(0, 'src')
from scheduler.control import clear_pause
print("cleared:", clear_pause())
PY
```

语义：

- pause file 存在且 `{"paused": true}` → tick 直接 `skipped_paused`（exit 0），不取锁、不执行任务。
- **损坏的 pause file 视为暂停**（fail-safe：拿不准就不花钱）。
- tick 在取锁后还会复查一次 pause（防"暂停请求落在取锁间隙"竞态）。

---

## 4. 单次 tick（手动）

```bash
# 标准 dry-run tick：决策 + run_micro_round --dry-run 批次规划，不调 API
python3 scripts/local_scheduler_tick.py --dry-run

# JSON 输出 + budget 透传（这些参数会出现在渲染的 run_micro_round 命令行里）
python3 scripts/local_scheduler_tick.py --dry-run --json --max-api-calls 5 --max-wall-time-minutes 30
```

退出码：

| 码 | 含义 | 处置 |
| --- | --- | --- |
| 0 | completed 或礼让（paused / lock 被占 / 有受控 worker） | 正常，无需处理 |
| 1 | 执行错误（子命令 rc≠0 / executor 异常） | 看 tick report 的 `execution` |
| 2 | blocked（stale lock / orphan worker） | 按 §7 / §8 处理后重试 |

每次 tick 都会写 `workspace/control/tick_reports/tick_*.json`（含 plan、命令行、执行结果、blocked_reason）。

---

## 5. 状态查看

```bash
python3 scripts/local_scheduler_status.py          # 人类可读
python3 scripts/local_scheduler_status.py --json   # 13 字段全量
python3 scripts/throughput_gate.py --json          # 内容层健康（章节统计、锁、checkpoint）
python3 scripts/check_orphan_workers.py --json     # worker 健康（必须 CLEAN）
bash scripts/local_scheduler_launchd.sh status     # launchd 视角
```

`safe_to_run=false` 的 `blocked_reasons` 取值：`paused` / `lock_held` / `stale_lock` / `orphan_workers` / `active_workers`。

---

## 6. 真实模式开关（FS-007 起；默认关闭）

前置条件（全部满足才允许开）：

1. `python3 scripts/local_scheduler_status.py --json` → `safe_to_run=true`；
2. `python3 scripts/check_orphan_workers.py --json` → CLEAN；
3. pause file 不存在；
4. 环境变量有 API Key（只读环境变量，不读 `.env`）；
5. 显式 budget：`--max-api-calls` 或等效限制**必须**给出；
6. cost guard 生效（`MAX_TEST_COST_USD` / `agent_layer.yaml`）。

手动单次真实 tick（FS-007 已验收：2026-06-11 smoke 5 calls / 81 segs / $0.0079，GAP-191-193 起步）：

```bash
python3 scripts/local_scheduler_tick.py --real-api --max-api-calls 5
```

真实模式强制约束（代码层）：`--real-api` 不带正数 `--max-api-calls` 会被 CLI 与模块双层拒绝。

launchd 周期真实模式：**不要**直接改已安装的 plist；流程是
编辑 `scripts/local_scheduler_launchd.sh` 的 `cmd_run_tick`（把 `--dry-run` 换成 `--real-api --max-api-calls N`）→ `install`（重装）→ 严密观察首个周期日志。
回退：`uninstall` 或恢复脚本后重新 `install`。

**永不**：把真实模式设为默认、移除 budget 限制、在 pause file 存在时运行真实 API。

---

## 7. stale lock 处理

两类锁：

| 锁 | 路径 | 风格 | stale 判定 |
| --- | --- | --- | --- |
| 调度器 tick 锁 | `workspace/control/scheduler_running.lock` | JSON + pid | pid 不存活 |
| translate/refine 锁 | `workspace/.locks/*.lock` | flock + pid 残留文件 | pid 不存活（flock 随进程死亡自动释放，文件是残留物） |

处理流程（先看后删，绝不清活 pid 的锁）：

```bash
# 1. 干跑：列出 held / stale / unknown_pid
python3 scripts/heal_stale_locks.py --json

# 2. 确认 verdict=stale 的项后实删
python3 scripts/heal_stale_locks.py --apply --json

# 3. 复查
python3 scripts/throughput_gate.py --json   # 不应再报 stale_lock
```

规则：

- `held`（pid 存活）永不删除——heal 脚本层面拒绝；
- `unknown_pid`（文件里没有可解析 pid）不自动删，人工检查来源；
- tick 自身**永不**回收 stale 锁（遇到即 exit 2），回收动作只走本节流程；
- 历史案例（2026-06-11 FS-006）：`refine_stage_c_run_20260602_203645…lock` 的 dead-pid 残留由 `tests/test_refine_stage_c.py` 子进程产生，根因已修（`refine_stage_c.py` 释放锁时 unlink 文件）。

---

## 8. 故障排查

| 症状 | 可能原因 | 处置 |
| --- | --- | --- |
| tick `skipped_lock_held` 持续出现 | 另一 tick / launchd 周期正在跑 | `bash scripts/local_scheduler_launchd.sh status` 看 state；正常并发礼让无需处理 |
| tick `blocked_stale_lock`（exit 2） | 上次 tick 进程被强杀 | §7 流程 heal 后重试 |
| tick `blocked_orphan_workers`（exit 2） | 历史 worker 失去 controller | `python3 scripts/check_orphan_workers.py --json` 取证；按 worker runbook 回收；orphan 不清不得继续 |
| tick `skipped_active_workers` | 有受控 worker 在翻译 | 等它完成；这是正常让位 |
| tick `error`（exit 1）`dispatched_command_failed` | run_micro_round 失败 | 看 tick report `execution.stdout_tail` / `stderr_tail`；修复后重试 |
| status `last_blocked_reason=paused` 但已恢复 | 历史记录（最近一次非成功 tick 的原因） | 跑一次成功 tick 自动清零 |
| gate `stage_state_stale` | stage_state 指向无 worker 的 in_progress run | 核对该 run 的 `run_progress.json` 真值后对齐 status（参考 FS-006：013940 run 实际 487/487 completed，已对齐） |
| gate `refine_pending` | legacy checker 仍看到旧 refine 路线 | v2 主线已废弃 refine；以 `local_scheduler_status.py --json` 的 `final_ready` 和 singleton check 为准 |
| launchd job 不触发 | plist 未加载 / 电脑休眠 | `status` 检查 loaded；`launchctl kickstart` 手动触发验证 |
| 日志无输出 | LOG_DIR 不存在或权限 | `run-tick` 自动 mkdir；检查 `workspace/logs/scheduler/launchd_stderr.log` |

---

## 9. 安全边界（重申）

- pause file 优先级最高：存在即停一切真实 API。
- tick 单任务原则：一个 tick 只执行一个任务，永不并发 worker。
- 永不打印 / 提交 API Key；plist、日志、报告均不得含密钥。
- 永不自动标记 human_approved_final、自动发布、覆盖 baseline / 原文。
- orphan worker 未回收时不得开始新一轮真实 API 工作。
