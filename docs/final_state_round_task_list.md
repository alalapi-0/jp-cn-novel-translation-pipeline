# Final State Round Task List

> 最终成品轮次任务清单（FS-000 … FS-070），2026-06-10 治理轮创建。
> 锚点：`docs/product_final_state_spec.md`；总路线：`docs/final_state_implementation_roadmap.md`。
> Phase A 的 D-MR-008…137 与 Phase D 的 R-MR 批量执行细节见 `docs/translation_recovery_3ch_task_list.md`（继续有效）；本清单的 FS 轮负责工程能力建设与阶段闸门。
>
> 通用约定（适用所有轮次，不再逐轮重复）：
> - 每轮开始执行 `docs/next_agent_execution_protocol.md` 的标准流程。
> - 每轮结束运行 `python3 scripts/agent_gate.py --json`；代码/测试变更时 `npm run check:tooling`。
> - 禁止 `git add .`；commit 前 `git status --short && git diff --stat && git diff --check`。
> - 永不提交 `.env`、API Key、真实原文、真实译文、workspace 大型产物。
> - UI 轮必须真实浏览器 before/after 检查并保存记录到 `artifacts/`。
> - 真实 API 轮必须遵守 cost guard 与规格 §21/§22；不得自动更换生产模型。
> - 状态更新：完成后在本文件该轮末尾追加 `> ✅ 完成于 YYYY-MM-DD（commit/报告引用）`。

---

## Round FS-000：治理轮（本轮）

### 目标
保存最终规格，建立 Roadmap / Task List / 验收 / 防跑偏 / DoD / 推进协议体系，更新 AGENTS.md。
### 验收标准
8 份治理文档存在且互相引用一致；agent_gate 通过；治理产物已 commit。
### 产物
`docs/product_final_state_spec.md` 等 8 份文档。
### 下一轮衔接
FS-001 启动调度器主线。

---

# Stage S1：本地调度器主线

## Round FS-001：pause / lock 控制协议内核

### 目标
实现规格 §9.3 / §9.4 的 pause file 与 lock file 协议，作为后续调度器的依赖模块。
### 背景
`workspace/control/` 目录已存在但为空；throughput_gate 已能检测 stale lock，但无统一控制协议。
### 输入
`docs/product_final_state_spec.md` §9；`scripts/check_orphan_workers.py`。
### 要修改 / 新增的文件
`src/scheduler/__init__.py`、`src/scheduler/control.py`（pause 读写、lock 获取/释放/stale 判定）、`tests/test_scheduler_control.py`、`docs/examples/scheduler_paused.example.json`。
### 要执行的命令
`npm run test:py`；`python3 -c "from src.scheduler.control import ..."` 冒烟。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
否 / 否。
### 验收标准
pause file 含 `{"paused": true}` 时 `is_paused()` 为 True；lock pid 活跃时二次获取失败；stale lock 可安全清理；测试覆盖三种场景全部通过。
### 禁止事项
不得删除 `workspace/control/` 下未来的真实运行数据；不得提交真实状态文件（仅提交 example）。
### 产物
控制协议模块 + 测试 + 示例模板。
### 下一轮衔接
FS-002 status 脚本消费本模块。

> ✅ 完成于 2026-06-11（`src/scheduler/control.py` + `tests/test_scheduler_control.py` 18 用例全过；全套 220 passed；pause fail-safe / lock 互斥 / stale 清理 / 上下文管理器均覆盖）

## Round FS-002：local_scheduler_status.py

### 目标
实现规格 §9.2 的状态脚本，输出 JSON 全字段。
### 背景
现有 `throughput_gate.py` / `stage_state.json` / `micro_round_progress.json` 已含大部分原始数据，本轮做聚合。
### 输入
FS-001 控制模块；`workspace/stage_state.json`；`scripts/throughput_gate.py`；3ch roadmap 的 D-MR 队列定义。
### 要修改 / 新增的文件
`scripts/local_scheduler_status.py`、`src/scheduler/status.py`、`tests/test_local_scheduler_status.py`。
### 要执行的命令
`python3 scripts/local_scheduler_status.py --json`；`npm run test:py`。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
否 / 否。
### 验收标准
JSON 输出包含规格 §9.2 全部 13 个字段（current_phase…safe_to_run）；paused / lock / orphan 任一异常时 `safe_to_run=false`；fixture 测试通过。
### 禁止事项
不得读取全书正文计算进度（只用 metadata / progress 文件）。
### 产物
status 脚本 + 模块 + 测试。
### 下一轮衔接
FS-003 tick 脚本以 status 为决策输入。

> ✅ 完成于 2026-06-11（`src/scheduler/status.py` + `scripts/local_scheduler_status.py` + 19 用例；13 字段全输出；metadata 统计与 content 层 throughput_gate 双口径一致 = 223 章。**发现真实缺口 ch191-208**：run_20260607_095821 被 D-MR-003 重用导致 T-002 时代 191-208 数据丢失，status 正确输出 next_task=draft_gap_backfill range=191-202；FS-008 启动批量推进前必须先回填 191-208）

## Round FS-003：local_scheduler_tick.py（dry-run 骨架）

### 目标
实现单 tick 骨架：检查 pause → 获取 lock → 判定下一任务 → dry-run 占位执行 → 保存 progress / report → 释放 lock → 干净退出。
### 背景
规格 §9.1 要求每 tick 只执行一个主任务。
### 输入
FS-001 / FS-002 模块。
### 要修改 / 新增的文件
`scripts/local_scheduler_tick.py`、`src/scheduler/tick.py`、`tests/test_local_scheduler_tick.py`。
### 要执行的命令
`python3 scripts/local_scheduler_tick.py --dry-run`；连续两次并发调用验证 lock 互斥；`npm run test:py`。
### 是否允许真实 API
否（本轮仅 dry-run）。
### 是否涉及 Web UI / 浏览器检查
否 / 否。
### 验收标准
dry-run 退出码 0；paused 时退出且不执行任务；lock 被占时立即退出；tick 结束 `check_orphan_workers.py` 为 CLEAN；tick report 写入 `workspace/control/tick_reports/`（gitignore）。
### 禁止事项
不得在 tick 内启动 detached background worker；不得调用真实 API。
### 产物
tick 骨架 + 测试。
### 下一轮衔接
FS-004 接入真实任务决策表。

> ✅ 完成于 2026-06-11（`src/scheduler/tick.py` + CLI + 18 用例；真实仓库 dry-run exit 0 / paused skip / 3 次并发互斥 `['completed','skipped_lock_held']` / orphan CLEAN / report 落 `workspace/control/tick_reports/`；修复 acquire 竞态误报 stale；全套 257 passed）

## Round FS-004：tick 任务决策表与 run_micro_round 集成

### 目标
实现 Phase → 下一任务映射（下一个 D-MR / 一致性子任务 / baseline lock / R-MR / 终检子任务 / production candidate），并将 D-MR 分支接入 `run_micro_round.py`（supervised 子进程）。
### 背景
规格 §9.1 的六类任务；当前仅 D-MR 可真实执行，其余先占位返回 `not_implemented` 并阻止误执行。
### 输入
FS-003 骨架；`scripts/run_micro_round.py --help` 的参数契约。
### 要修改 / 新增的文件
`src/scheduler/task_planner.py`、`src/scheduler/tick.py`（更新）、`tests/test_scheduler_task_planner.py`。
### 要执行的命令
`python3 scripts/local_scheduler_tick.py --dry-run`（应显示 next task 为当前 D-MR）；`npm run test:py`。
### 是否允许真实 API
否（仍 dry-run；真实执行留给 FS-007）。
### 是否涉及 Web UI / 浏览器检查
否 / 否。
### 验收标准
决策表对 5 个 Phase 的 fixture 状态都能给出正确 next task；D-MR 分支 dry-run 能正确拼出 run_micro_round 命令行并透传 budget 参数；未实现分支显式报 `not_implemented` 而非静默跳过。
### 禁止事项
不得让 tick 并发执行多个任务。
### 产物
任务决策表 + 集成 + 测试。
### 下一轮衔接
FS-005 launchd 化。

> ✅ 完成于 2026-06-11（`src/scheduler/task_planner.py` 决策表覆盖 draft/gap、consistency、baseline_lock、refinement、final_review、production_candidate 全分支；未实现分支显式 `not_implemented`；D-MR/GAP 分支拼出 run_micro_round 命令行并透传 budget（`--max-api-calls` 等 5 项）；dry-run 命令强制 `--dry-run --no-real-api` 双保险；tick dispatcher 同步 supervised 子进程；真实仓库 tick：plan GAP-191-193、rc:0、exit 0；测试 17+21 用例；全套 277 passed）

## Round FS-005：launchd 集成

### 目标
提供 `scripts/local_scheduler_launchd.sh` 与 `scripts/launchd/com.lightnovel.translation.scheduler.plist.template`，支持安装 / 卸载 / 查看周期 tick。
### 背景
launchd 环境无用户 shell 环境变量，需要显式 PATH 与工作目录；日志须可读。
### 输入
FS-003 / FS-004 tick。
### 要修改 / 新增的文件
`scripts/local_scheduler_launchd.sh`、`scripts/launchd/com.lightnovel.translation.scheduler.plist.template`、日志落 `workspace/logs/scheduler/`（gitignore）。
### 要执行的命令
`bash scripts/local_scheduler_launchd.sh install --dry-run`、`status`、`uninstall`；手动 `launchctl kickstart` 一次 dry-run tick 验证。
### 是否允许真实 API
否（plist 默认带 `--dry-run`，真实模式需手动改装）。
### 是否涉及 Web UI / 浏览器检查
否 / 否。
### 验收标准
install/uninstall/status 三命令幂等；kickstart 后 tick 日志出现在 `workspace/logs/scheduler/` 且含时间戳与退出码；plist template 不含绝对的用户专属密钥信息。
### 禁止事项
不得默认安装为真实 API 模式；不得把 plist 写死 API Key。
### 产物
launchd 脚本 + 模板。
### 下一轮衔接
FS-006 Runbook 与 stale 治理。

> ✅ 完成于 2026-06-11（`local_scheduler_launchd.sh` install/--dry-run/uninstall/status/run-tick + plist 模板；真实 install→kickstart→tick 日志含时间戳与退出码（`workspace/logs/scheduler/scheduler_tick.log`，dry-run tick exit 0 plan GAP-191-193）→重复 install/uninstall 幂等→已卸载收尾；plist 固定 dry-run、无密钥、显式 PATH/WorkingDirectory）

## Round FS-006：local_scheduler_runbook.md 与 stale lock 治理

### 目标
编写规格 §9 要求的 runbook；清理当前已知 stale lock（`refine_stage_c_run_20260602_203645.lock`）与 `stage_state_stale` 警告。
### 背景
throughput_gate 当前 WARN：stale lock pid=17721、stage_state 指向无 worker 的 run。
### 输入
FS-001…FS-005 全部组件；`python3 scripts/throughput_gate.py --json` 输出。
### 要修改 / 新增的文件
`docs/local_scheduler_runbook.md`；必要时 `scripts/heal_stale_locks.py`（或扩展现有脚本）；更新 `workspace/stage_state.json` 指向。
### 要执行的命令
`python3 scripts/throughput_gate.py --json`（目标 decision=CLEAN 或仅 diagnostic 警告）；`python3 scripts/local_scheduler_status.py --json`。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
否 / 否。
### 验收标准
runbook 覆盖：安装、暂停、恢复、单次 tick、真实模式开关、stale lock 处理、故障排查；throughput_gate 不再报 stale_lock。
### 禁止事项
清 lock 前必须确认 pid 不活跃；不得删除 run 数据。
### 产物
runbook + 干净的 gate 状态。
### 下一轮衔接
FS-007 真实 smoke。

> ✅ 完成于 2026-06-11（`docs/local_scheduler_runbook.md` 9 节全覆盖验收清单；`scripts/heal_stale_locks.py`（dry-run 默认、活 pid 拒删、unknown_pid 仅报告）+ 7 用例；**根因修复**：stale lock 由 `tests/test_refine_stage_c.py` 子进程残留所致 → `refine_stage_c.py` 释放锁时 unlink；stage_state_production 对齐 run 真值（run_20260608_013940 实为 487/487 completed）；gate 不再报 stale_lock / stage_state_stale，仅剩 refine_pending + diagnostic checkpoint 等预期诊断；全套 284 passed）

## Round FS-007：调度器真实 API smoke tick

### 目标
以真实 API 执行一次完整 tick（推进当前 D-MR 的一部分，≤3 章 / 受 `--max-api-calls` 限制），验证调度器端到端可用。
### 背景
S1 收官轮；之后 Phase A 批量推进可交给调度器。
### 输入
FS-001…FS-006；`.env` 中的 API Key（仅环境变量读取）。
### 要修改 / 新增的文件
原则上无新代码；修复 smoke 暴露的问题。
### 要执行的命令
`python3 scripts/local_scheduler_tick.py --real-api --max-api-calls 5`（参数名以实际实现为准）；执行前后各跑 `check_orphan_workers.py --json` 与 `local_scheduler_status.py --json`。
### 是否允许真实 API
**是**（最小 smoke，受 max-api-calls 与 cost guard 限制）。
### 是否涉及 Web UI / 浏览器检查
否 / 否。
### 验收标准
tick 正常完成或安全中断；checkpoint / progress / report 落盘；无 orphan；成本记录在 tick report 中；smoke 结果写入轮次报告（不含正文）。
### 禁止事项
不得移除 max-api-calls 限制；不得连续多 tick 跑批（那是 S2 的事）。
### 产物
真实 smoke 报告；S1 完成结论。
### 下一轮衔接
FS-008 启动 Phase A 批量推进。

> ✅ 完成于 2026-06-11（`local_scheduler_tick.py --real-api --max-api-calls 5` 端到端成功：plan GAP-191-193 → run_micro_round 真实执行 → **新 run 目录** run_20260610_212507（不重用）→ 5/5 calls、100/307 segments、$0.0079、checkpoint+progress+log+metrics 落盘；前后 orphan CLEAN、lock 干净释放、status last_tick 更新；real 模式强制正数 max-api-calls（CLI+模块双层）；GAP round 接入 `micro_round_plan.gap_backfill_plan`（resume_run_id 恒空防目录重用）；全套 289 passed。**S1 本地调度器主线完成**）

---

# Stage S2：Phase A 初翻完成

## Round FS-008：Phase A 批量推进启动轮

### 目标
确认 D-MR-008 续跑点正确，启动"调度器 tick / supervised loop"批量推进模式，并定义批量期间的健康检查节奏。
### 背景
当前 D-MR-008 进行中（92/328 segments，run 已归档至 `workspace/archived_runs/`，需确认续跑来源）。
### 输入
S1 调度器；`docs/translation_recovery_3ch_task_list.md` D-MR 队列；归档 run 的 checkpoint。
### 要修改 / 新增的文件
必要的 checkpoint 续跑修复；`workspace/stage_state.json` 对齐。
### 要执行的命令
`python3 scripts/local_scheduler_status.py --json`；启动连续 supervised 推进（每 tick 一个 D-MR）。
### 是否允许真实 API
**是**（生产模型 deepseek/deepseek-v4-pro）。
### 是否涉及 Web UI / 浏览器检查
否 / 否。
### 验收标准
D-MR-008 从正确断点续跑且无重复翻译；连续 3 个 MR 无人工干预完成；每 MR 报告生成。
### 禁止事项
不得并发多 worker；不得切换模型；不得跳过 failed segment。
### 产物
批量推进运行中状态 + 启动报告。
### 下一轮衔接
按 3ch task list 持续执行 D-MR；每个 Milestone Block 结束插入 FS-009 健康检查。

> 🔄 启动于 2026-06-11（启动轮修复三项：①planner `find_resumable_run` 同 offset in_progress run 续跑注入 `--run-id`（防重复翻译；与禁止的"完成 run 目录重用"严格区分）②throughput_gate `offset_skip` 回填豁免（单 in_progress 低 offset → `backfill_in_progress` warn；多 in_progress 异 offset 仍 BLOCK）③run_micro_round 完成时写回 production stage_state + translate 锁释放即 unlink（stage_state_stale / stale_lock 根因清除）。GAP-191-193 完成（307 段，但因续跑 bug 重翻 100 段 ≈ $0.008 浪费，修复后不再发生；被取代 run 已标 aborted 归档）。进度 226/613。验收项"连续 3 MR 无干预"在后续 Block 执行中核对）
>
> ✅ 完成于 2026-06-11（**Block #1 收口：ch1-241 连续完成（241/613，39.31%），缺口 191-211 全部回填**。事故与修复：legacy run 自动 resume（`LEGACY_PARTIAL_RUN_ID`）+ hydrate 窗口重写导致 ①D-MR-001 假完成（0 调用）②legacy run segments 从 209-211 被改写为 206-208（209-211 受控记录丢失；draft md 无物理丢失）→ 三防线修复：移除 legacy 自动 resume；hydrate 拒绝跨 offset 重定向（"run 目录单窗口"原则）；round_done=False 时拒绝 completed 假成功。206-208 经核证为 T-002 真实成果有效保留；203-205（562 段 $0.036）与 209-211（342 段 $0.023）受控重翻完成。验收：✅续跑无重复翻译（修复后 find_resumable_run 测试覆盖）✅连续 5 MR 无人工干预（GAP-194/197/200 + D-MR-001/003）✅每 MR metrics+summary+tick report 生成。健康检查：6 run 全 completed、failed=0、gate 仅预期诊断警告；今日成本 $0.1558）
>
> ✅ Block #3 收口于 2026-06-11（第三棒接力：清交接 pause → D-MR-016 自 122/412 断点同 offset 续跑收尾 → D-MR-017（387 段）→ D-MR-018（310 段）→ D-MR-019（403 段，tick shell 被环境回收中断于 60/403：worker checkpoint 干净退出、清 stale lock 后 planner 同 run 同 offset 自动续跑无重复翻译，后续 slot 改单 tick 单 shell 模式）→ D-MR-020（251 段）。**进度 262/613（42.74%），ch1-262 连续**。健康检查：5/5 tick completed、orphan 全程 CLEAN、TOTAL failed=0、gate WARN 仅 refine_pending + diagnostic_*（预期）；Block 成本 ≈ $0.127（deepseek/deepseek-v4-pro）。批量等待间隙穿插完成 S3 四轮：FS-011/012/013/014（见各轮注记））
>
> ✅ Block #4 收口于 2026-06-11（单 tick 单 shell 模式：D-MR-021（272 段）→ D-MR-022（338 段）→ D-MR-023（跨 2 个 budget tick 同 offset 续跑，设计行为）→ D-MR-024。**进度 274/613（44.70%），ch1-274 连续**，next D-MR-025（275-277）。健康检查：5/5 tick completed、orphan 全程 CLEAN、TOTAL failed=0、gate WARN 仅预期诊断、blocks=[]；Block 成本 $0.1354（4 run checkpoint 实测），今日累计 ≈ $0.57。间隙穿插完成 S3 收官两轮 FS-015/016 → **S3 全 stage 完成**）
>
> ✅ Block #5 收口于 2026-06-11（D-MR-025 → 026 → 027 → 028 → 029 各一 tick 完成（5/5），15 章。**进度 289/613（47.15%），ch1-289 连续**，next D-MR-030（290-292）。健康检查：orphan 全程 CLEAN、TOTAL failed=0、gate WARN 仅预期诊断、blocks=[]；Block 成本 $0.1666，今日累计 ≈ $0.74）
>
> ✅ Block #6 收口于 2026-06-11（D-MR-030 → 031 → 032 → 033 → 034 各一 tick 完成（5/5），15 章。**进度 304/613（49.59%），ch1-304 连续**，next D-MR-035（305-307）。健康检查：orphan 全程 CLEAN、TOTAL failed=0、gate WARN 仅预期诊断、blocks=[]；Block 成本 $0.1368，今日累计 ≈ $0.88）
>
> ✅ Block #7 收口于 2026-06-11（第三棒接力续跑：接手时 D-MR-037 进行中 → 等 tick 完成 → D-MR-038 跨 2 tick 同 offset 续跑（731 段，设计行为）→ 5/5 tick slot 满。**进度 316/613（51.55%），ch1-316 连续**，next D-MR-039（317-319）。健康检查：orphan 全程 CLEAN、TOTAL failed=0、gate WARN 仅预期诊断、blocks=[]；Block 成本 $0.1599（035/036/037/038 checkpoint 实测），今日累计 ≈ $1.04）
>
> ✅ Block #8 收口于 2026-06-11（D-MR-039 → 040（跨 2 tick 同 offset 续跑）→ 041 → 042 各完成（5/5 tick slot）。**进度 328/613（53.51%），ch1-328 连续**，next D-MR-043（329-331）。健康检查：orphan 全程 CLEAN、TOTAL failed=0、gate WARN 仅预期诊断、blocks=[]；Block 成本 $0.1210，今日累计 ≈ $1.16）

## Round FS-009：Phase A 周期健康检查轮（模板轮，可重复执行）

### 目标
每完成一个 Milestone Block（15 章）执行一次：失败重试清零、统计核对、成本核对、漏段抽查。
### 背景
防止批量期间问题堆积到收尾。
### 输入
最近 5 个 D-MR 报告；throughput_gate。
### 要修改 / 新增的文件
仅修复性变更；健康检查报告入 `workspace/round_reports/`。
### 要执行的命令
`python3 scripts/throughput_gate.py --json`；`python3 scripts/check_orphan_workers.py --json`；failed segment retry 命令；`npm run test:py`（如有代码修复）。
### 是否允许真实 API
是（仅 failed retry 与局部补翻）。
### 是否涉及 Web UI / 浏览器检查
否 / 否。
### 验收标准
该 Block 内 failed=0、validation_failed（blocking）=0；成本与预估偏差 <50% 或已记录原因。
### 禁止事项
不得为清零而删除 failed 记录。
### 产物
Block 健康检查报告。
### 下一轮衔接
继续下一 Block；全书完成后进入 FS-010。

## Round FS-010：Phase A 收尾与完成闸门

### 目标
确认全书 613 章 draft 完成，执行规格 §12.2 全部完成条件检查，导出 draft，生成 Phase A completion report。
### 输入
全部 D-MR 报告；`src/translation/exporter.py`。
### 要修改 / 新增的文件
`scripts/phase_a_completion_check.py`（若无）；Phase A completion report（脱敏统计版可提交）。
### 要执行的命令
`python3 scripts/phase_a_completion_check.py --json`；draft 导出命令；`python3 scripts/throughput_gate.py --json`。
### 是否允许真实 API
是（仅收尾补翻）。
### 是否涉及 Web UI / 浏览器检查
否 / 否。
### 验收标准
`docs/phase_acceptance_criteria.md` Phase A 节全部条件 PASS；completion report 列出 613 章逐章状态汇总（统计，不含正文）。
### 禁止事项
存在 failed / blocking validation_failed 时不得宣布 Phase A 完成。
### 产物
Phase A 完成报告 + draft 导出。
### 下一轮衔接
S6（Phase B 工具链）正式接管；S3/S4/S5 若未完成可继续并行。

---

# Stage S3：configs 资产层与术语库内核

## Round FS-011：configs/ 目录与五 YAML 模板

### 目标
建立规格 §10 的 `configs/` 目录：glossary / character_profile / style_profile / world_bible / model_profiles 五个 YAML 的 schema 与脱敏模板。
### 输入
规格 §7.8 / §7.9 / §7.10 字段定义；现有 `governance/novel_pipeline_contract.yaml`。
### 要修改 / 新增的文件
`configs/*.yaml`（模板）、`schemas/glossary.schema.json` 等、`tests/test_configs_schema.py`、`.gitignore`（如真实数据需另存）。
### 要执行的命令
`npm run test:py`；schema 校验脚本。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
否 / 否。
### 验收标准
五 YAML 通过各自 schema 校验；glossary schema 含规格 §7.8 全部 13 字段与 12 分类枚举；模板不含真实译名。
### 禁止事项
不得把含真实小说术语的完整 glossary 提交 Git（真实数据放 workspace 或经用户确认）。
### 产物
configs 模板层 + schema + 测试。
### 下一轮衔接
FS-012 迁移现有资产。

> ✅ 完成于 2026-06-11（S2 批量等待间隙穿插执行（Roadmap §3 允许）。新增 `configs/` 五 YAML 脱敏模板（glossary / character_profile / style_profile / world_bible / model_profiles + README 约定）+ `schemas/` 五 Draft7 JSON Schema + `scripts/validate_configs.py`（PASS，--json / --configs-dir 支持）+ `tests/test_configs_schema.py` 21 用例。验收：✅五 YAML 全过各自 schema ✅glossary schema required 含规格 §7.8 全部 13 字段、category 12 枚举（world_bible 14 枚举）✅模板全虚构（サンプル~ 断言；model_profiles 无密钥断言 + schema not/api_key 拒绝）。`.gitignore` 增 `workspace/configs/`（FS-012 真实数据落点）。全套 315 passed（基线 294+21））

## Round FS-012：现有翻译资产迁移

### 目标
把 `workspace/assets/translation_memory/` 等现有资产中的术语、角色信息迁移 / 映射到 configs 结构（真实数据存放于 workspace 侧，configs 提交模板）。
### 输入
FS-011 schema；现有资产文件。
### 要修改 / 新增的文件
`scripts/migrate_assets_to_configs.py`、迁移报告（统计版）。
### 要执行的命令
`python3 scripts/migrate_assets_to_configs.py --dry-run` → 确认后实跑；`npm run test:py`。
### 是否允许真实 API
否。
### 验收标准
迁移 dry-run 报告列出条目数 / 冲突数 / 丢弃字段=0；实跑后 glossary 加载器能读到全部迁移条目。
### 禁止事项
不得删除原资产文件；不得提交迁移后的真实术语数据。
### 产物
迁移脚本 + 报告 + workspace 侧真实 configs 数据。
### 下一轮衔接
FS-013 CRUD。

> ✅ 完成于 2026-06-11（S2 批量等待间隙穿插执行。`scripts/migrate_assets_to_configs.py`：7 个 TM 资产文件 → 82 term_candidates → 去重合并 64 条 glossary 条目（14 重复合并、4 冲突首译保留+notes 记录）、丢弃字段=0（kind/evidence 全量并入 description）；实跑写 `workspace/configs/glossary.yaml + character_profile.yaml`（角色骨架——legacy 资产无角色数据）+ 内置 verify（重载+schema 校验+条目数比对）=True；`validate_configs.py` 增 `--allow-missing`（真实目录部分文件场景）。验收：✅dry-run 报告条目/冲突/丢弃=0 ✅实跑后加载器读回全部 64 条且过 schema ✅源资产零修改（mtime+字节级测试断言）✅真实数据仅落 workspace/configs/（gitignore 验证）。迁移统计报告 `reports/asset_migration_report.json`（纯统计无术语内容）。测试 +9（全套 324 passed））

## Round FS-013：glossary CRUD 内核

### 目标
实现 `src/glossary/` 模块：增删改查、locked / approved_by_user / conflict 状态机、分类、搜索。
### 输入
FS-011 schema；FS-012 数据。
### 要修改 / 新增的文件
`src/glossary/store.py`、`src/glossary/models.py`、`tests/test_glossary_store.py`。
### 要执行的命令
`npm run test:py`。
### 是否允许真实 API
否。
### 验收标准
CRUD 全操作有测试；locked 术语不可被机器建议覆盖（测试验证）；updated_at 自动维护；并发写有文件锁保护。
### 禁止事项
delete 操作必须软删除或要求显式 force。
### 产物
glossary 内核 + 测试。
### 下一轮衔接
FS-014 导入导出。

> ✅ 完成于 2026-06-11（S2 批量等待间隙穿插执行。`src/glossary/`：models.py（GlossaryEntry 13 字段 + conflict/deleted 扩展态、12 分类校验、置信度域校验、异常族）+ store.py（YAML 后端 CRUD：add 唯一性/软删墓碑取代、get/entries/search 子串+分类+locked/approved/conflict 过滤、update 白名单字段+机器/人工通道、lock/unlock/approve/mark_conflict 状态机、suggest 机器建议入口、restore；并发=同进程 threading.Lock + 跨进程 O_EXCL lock file 超时重试，原子写 tmp+replace）。验收：✅CRUD 全操作 26 测试 ✅locked 拒绝机器 suggest/update/force-delete（人工可改、unlock 仅人工）✅updated_at 自动维护（created_at 不可改）✅并发 30 线程零丢失 + 外部锁持有者超时拒绝 ✅delete 默认软删 force 才物理删。store 输出过 glossary schema（含墓碑/conflict 扩展字段）；FS-012 真实数据加载冒烟通过。全套 350 passed（324+26））

## Round FS-014：glossary 导入导出（CSV / YAML / JSON）

### 目标
实现三格式导入导出与 roundtrip 保真，导入时报告新增 / 覆盖 / 冲突数量。
### 要修改 / 新增的文件
`src/glossary/io.py`、`tests/test_glossary_io.py`。
### 要执行的命令
`npm run test:py`。
### 是否允许真实 API
否。
### 验收标准
三格式 roundtrip 测试（导出→导入→比对无损）通过；导入冲突时 locked 术语保持不变并计入冲突报告。
### 禁止事项
导入不得静默覆盖 approved_by_user 术语。
### 产物
导入导出模块 + 测试。
### 下一轮衔接
FS-015 usage index。

> ✅ 完成于 2026-06-11（S2 批量等待间隙穿插执行。`src/glossary/io.py`：export_glossary / read_entries / import_glossary 三格式（CSV/YAML/JSON，.yml 别名）；CSV 空单元格=None 约定（nullable 字段无损）、aliases `|` 分隔、状态布尔列；ImportReport{total/added/updated/unchanged/skipped_locked/skipped_approved/conflicts[]}。验收：✅三格式 roundtrip 无损（导出→导入→to_dict 全等，参数化 3 格式）✅导入冲突时 locked 保持原译并入冲突报告（reason=locked + kept_target 证据）✅approved_by_user 永不静默覆盖（差异 → skipped_approved + 冲突报告；全等 → unchanged）。状态旗标（locked/approved/conflict）经 CSV roundtrip 保留。测试 +15（全套 365 passed））

## Round FS-015：term usage index 与冲突标记

### 目标
建立术语在章节中的使用索引（term → chapters / segments 命中统计），并实现"同源多译 / 同译多源"冲突标记。
### 输入
draft 输出与 segment 索引（只读 metadata 与命中统计，不全文入上下文）。
### 要修改 / 新增的文件
`scripts/build_term_usage_index.py`、`src/glossary/usage_index.py`、`tests/test_term_usage_index.py`。
### 要执行的命令
`python3 scripts/build_term_usage_index.py --chapter-range 1-50 --json`；`npm run test:py`。
### 是否允许真实 API
否（纯规则统计）。
### 验收标准
索引可增量更新；冲突统计与 fixture 预期一致；输出落 `workspace/indexes/`（gitignore）。
### 禁止事项
不得把全书正文加载进单一上下文（流式逐章处理）。
### 产物
usage index 工具 + 测试。
### 下一轮衔接
FS-016 prompt 接入；亦是 S6 entity index 的基础。

> ✅ 完成于 2026-06-11（S2 批量等待间隙穿插执行。`src/glossary/usage_index.py`：流式逐文件逐章扫描（永不全书入单一上下文），per-term source/target/co/divergent 命中统计（章节聚合 + 总计 + 限量 divergent segment_id 样本，索引零正文泄漏——测试断言）；冲突标记 divergent_translation（同源多译：divergent/source ≥0.3 且 source_hits≥2）+ shared_target（同译多源：glossary 内多 source 共享一 target）；增量=per-file (size,mtime) fingerprint 桶复用 + chapter 归属新文件优先（重翻取代归档贡献）。`scripts/build_term_usage_index.py`：--chapter-range/--runs-dir/--rebuild/--json。验收：✅增量更新（真实数据二跑 scanned=0 reused=32；改单文件只重扫 1）✅冲突统计与 fixture 预期一致（kingdom ratio=0.5、shared 公会双源断言）✅输出落 workspace/indexes/（gitignore 断言）。真实数据跑通：1-50 章 26 术语命中 16 冲突；全范围 41 章 64 术语 25 冲突。测试 +10（全套 375 passed））

## Round FS-016：prompt builder 接入 configs 资产

### 目标
初翻 / 润色 prompt builder 改为按规格 §22 注入：当前 batch 命中的 glossary 子集 + 涉及角色的 character notes，不注入全量资产。
### 输入
FS-013…FS-015；`src/translation/prompt_builder.py`、`refine_prompt_builder.py`。
### 要修改 / 新增的文件
上述 prompt builder、`tests/test_prompt_builder_assets.py`。
### 要执行的命令
`npm run test:py`；`python3 scripts/run_micro_round.py --dry-run --fake-provider`（验证注入内容）。
### 是否允许真实 API
否（dry-run / fake provider 验证）。
### 验收标准
注入的 glossary 条目 ⊆ 当前 batch 命中集合（测试断言）；context pack token 统计未超预算；fake provider 端到端通过。
### 禁止事项
不得注入全书 glossary / character profile / world bible。
### 产物
资产感知的 prompt builder + 测试。
### 下一轮衔接
S4 UI 基座（或继续 S2 批量推进）。

> ✅ 完成于 2026-06-11（S2 批量等待间隙穿插执行，**S3 资产层收官**。新增 `src/translation/configs_asset_context.py`：build_configs_asset_context 按当前 batch source_text 命中筛选 configs 资产（glossary source_term/alias 命中 + character name/alias 命中），locked > approved > 其余排序、[locked]/[approved] 旗标、紧凑角色行（译名/一人称/口癖/敬语/称呼≤2/禁止≤1）、max_terms/max_characters/char_budget 三重预算（超限 truncated 标记）、(size,mtime) 缓存、deleted 墓碑排除。接入：draft_runner compact 分支（TM hits + configs hits 叠加）、refine_prompt_builder 新 asset_context 参数 + refine_runner 注入。验收：✅注入条目 ⊆ batch 命中集合（50 条未命中术语零泄漏断言 + 别名命中 + 墓碑排除）✅context pack 预算受控（char_budget=60 截断断言 + max_terms cap）✅run_micro_round --dry-run --fake-provider plan 通过（272 段 14 batch est 29693 tok）。测试 +10（全套 385 passed））

---

# Stage S4：Web UI 基座与设计系统

## Round FS-017：UI 架构决策与布局壳

### 目标
确定多页 UI 架构（延续静态 HTML + `frontend/assets/` + workbench server，扩展统一侧边导航布局壳），输出架构决策记录。
### 背景
现有 4 页 Workbench 无统一导航；最终需 15 页。
### 输入
规格 §6–8；`docs/design/DESIGN.md`、`docs/design/stitch/`；现有 frontend。
### 要修改 / 新增的文件
`docs/design/ui_architecture_decision.md`、`frontend/assets/layout.js`（或等效壳实现）、改造 1 个现有页面接入壳验证。
### 要执行的命令
`npm run dev:frontend`；浏览器打开改造页 before/after 截图。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
**是 / 是**。
### 验收标准
布局壳含侧边导航（15 页占位，未实现页标灰）+ 顶栏（项目名 / 当前 Phase 占位）；改造页功能无回归（`npm run test:ui` 相关用例通过）；截图入 `artifacts/`。
### 禁止事项
一轮内不得改造全部旧页面；不得引入需要构建步骤的重型框架（保持静态栈，除非用户确认）。
### 产物
架构决策 + 布局壳 + 1 页接入。
### 下一轮衔接
FS-018 设计系统 CSS。

## Round FS-018：设计系统——色彩与状态标签

### 目标
实现规格 §8.2 / §8.3：统一色彩变量（成功绿 / 运行蓝 / 警告橙 / 错误红 / 暂停灰 / 人工紫 / 候选青）与 11 个标准状态标签组件。
### 要修改 / 新增的文件
`frontend/assets/design-system.css`、`frontend/assets/status-badge.js`。
### 要执行的命令
`npm run dev:frontend`；浏览器检查；`npm run test:ui`。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 验收标准
11 个状态徽章颜色 + 中文文本标签同时呈现（颜色非唯一信息源）；CSS 变量集中定义无散落硬编码色值（grep 验证）。
### 禁止事项
不得在各页面各自定义状态颜色。
### 产物
设计系统基础层。
### 下一轮衔接
FS-019 交互组件。

## Round FS-019：交互组件——反馈 / 确认 / 空状态 / loading

### 目标
实现规格 §8.4 反馈原则组件：toast、危险操作二次确认对话框、空状态、loading 骨架。
### 要修改 / 新增的文件
`frontend/assets/components.js`（toast / confirm / empty / loading）、组件样式入 design-system.css。
### 要执行的命令
`npm run dev:frontend`；浏览器逐组件验证；`npm run test:ui`。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 验收标准
confirm 组件强制两步（点击 + 输入确认词或显式二次按钮）；toast 自动消失且可堆叠；空状态含下一步指引文案。
### 禁止事项
危险操作不得用浏览器原生 `confirm()` 糊弄。
### 产物
组件库。
### 下一轮衔接
FS-020 styleguide。

## Round FS-020：styleguide 页面与视觉基线

### 目标
建立 `frontend/styleguide.html` 陈列全部设计系统元素，作为后续 UI 轮的视觉基线与回归参照。
### 要修改 / 新增的文件
`frontend/styleguide.html`、`tests/ui/styleguide.spec.ts`（截图基线）。
### 要执行的命令
`npm run dev:frontend`；`npm run test:ui`；截图入 `artifacts/`。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 验收标准
styleguide 含全部状态徽章 / 按钮 / 卡片 / 表格 / toast / confirm / 空态 / loading；Playwright 截图测试通过且无 console 错误。
### 禁止事项
styleguide 不进入主导航生产入口（开发者入口即可）。
### 产物
视觉基线页 + 截图测试。
### 下一轮衔接
FS-021 状态字典。

## Round FS-021：状态标签字典前后端统一

### 目标
建立状态枚举唯一来源（如 `src/shared/status_enums.py` + 生成 `frontend/assets/status-enums.js`），消除各处叫法不一。
### 要修改 / 新增的文件
状态枚举模块、生成脚本、`tests/test_status_enums.py`；替换现有页面 / 脚本中的硬编码状态串（grep 清单驱动）。
### 要执行的命令
`grep -rn` 审计旧状态串；`npm run test:py`；`npm run test:ui`。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 验收标准
规格 §8.3 的 11 个状态有唯一定义；前端枚举由后端生成（或共享 JSON），CI 校验两侧一致。
### 禁止事项
不得为兼容保留旧叫法别名超过一轮。
### 产物
统一状态字典。
### 下一轮衔接
FS-022 后端 API 基座。

## Round FS-022：workbench server API 基座扩展

### 目标
为 UI MVP 准备后端：统一 JSON 响应 / 错误格式、`/api/` 路由注册机制、scheduler status / glossary / 报告列表三类只读端点打底。
### 输入
`src/workbench/server.py`；FS-002 status 模块；FS-013 glossary 内核。
### 要修改 / 新增的文件
`src/workbench/server.py`、`src/workbench/api_v2.py`（或等效）、`tests/test_workbench_api_v2.py`。
### 要执行的命令
`npm run dev:frontend` 后 curl 各端点；`npm run test:py`。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
是（network 面板确认请求） / 是。
### 验收标准
`GET /api/scheduler/status`、`GET /api/glossary/terms`、`GET /api/reports` 返回统一包络格式；错误返回含 code / message / hint；测试覆盖。
### 禁止事项
端点不得返回 API Key 明文；不得返回全书正文。
### 产物
API 基座 + 测试。
### 下一轮衔接
S5 各页面轮。

---

# Stage S5：Web UI MVP

> 本 Stage 每轮通用要求：中文界面；复用 FS-017…FS-021 设计系统；危险操作走 confirm 组件；每轮 `npm run dev:frontend` + 浏览器 before/after + console / network 检查 + `npm run test:ui` 新增用例；截图入 `artifacts/`。

## Round FS-023：Dashboard 总览页

### 目标
实现规格 §7.1 Dashboard：项目状态全字段 + 8 个操作按钮（未实现功能按钮置灰并标注所属轮次）。
### 输入
FS-022 `/api/scheduler/status`；stage_state；成本统计。
### 要修改 / 新增的文件
`frontend/dashboard.html`、`frontend/assets/dashboard.js`、后端聚合端点、`tests/ui/dashboard.spec.ts`。
### 要执行的命令
`npm run dev:frontend`；`npm run test:ui`。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 验收标准
显示规格 §7.1 全部 19 项状态字段（无数据项显示明确空态而非空白）；当前 Phase / next task / active worker / orphan / 成本与 `local_scheduler_status.py --json` 输出一致（Playwright 断言）。
### 禁止事项
不得用假数据填充状态字段。
### 产物
Dashboard 页 + 测试。
### 下一轮衔接
FS-024 控制台。

## Round FS-024：Pipeline 控制台页

### 目标
实现规格 §7.5：暂停 / 恢复 / 单次 tick / 查看 worker / lock / checkpoint / launchd 状态；危险操作二次确认。
### 输入
FS-001 控制协议；FS-003 tick；FS-022 API 基座。
### 要修改 / 新增的文件
`frontend/pipeline.html` + js、后端控制端点（写 pause file、清 stale lock、触发 dry-run tick）、`tests/ui/pipeline.spec.ts`。
### 要执行的命令
`npm run dev:frontend`；`npm run test:ui`。
### 是否允许真实 API
否（UI 触发的 tick 本轮限 dry-run；真实模式开关留给 FS-029 后联调）。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 验收标准
点击暂停后 `workspace/control/scheduler_paused.json` 真实写入且 UI 显示反馈（规格 §8.4）；清 stale lock 需二次确认；Playwright 覆盖暂停→恢复全流程。
### 禁止事项
停止真实 worker / 清 lock / 重跑不得单击直达。
### 产物
控制台页 + 控制端点 + 测试。
### 下一轮衔接
FS-025 章节管理。

## Round FS-025：章节管理页

### 目标
实现规格 §7.6：613 章列表、15 项状态列（未实现阶段列显示 not_started）、8 类过滤器、分页 / 虚拟滚动。
### 输入
segment / run progress 数据；FS-015 usage index（术语冲突数列）。
### 要修改 / 新增的文件
`frontend/chapters.html` + js、`GET /api/chapters` 端点（分页）、`tests/ui/chapters.spec.ts`。
### 验收标准
过滤器组合可用；章节状态与 throughput_gate 统计一致（抽样断言）；600+ 行渲染无明显卡顿（分页或虚拟化）。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 禁止事项
端点不得一次返回全部章节正文。
### 产物
章节管理页 + 测试。
### 下一轮衔接
FS-026 术语库页。

## Round FS-026：术语库页（查看 / CRUD）

### 目标
实现规格 §7.8 的查看、新增、编辑、删除、锁定 / 解锁、人工确认、分类筛选、搜索。
### 输入
FS-013 glossary 内核；FS-022 端点。
### 要修改 / 新增的文件
`frontend/glossary.html` + js、glossary 写端点、`tests/ui/glossary.spec.ts`。
### 验收标准
13 字段完整呈现与编辑；locked 术语编辑需先解锁（UI 强制）；删除走二次确认；CRUD 操作后列表即时刷新且有 toast 反馈。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 禁止事项
不得绕过 FS-013 内核直接改 YAML。
### 产物
术语库页 + 测试。
### 下一轮衔接
FS-027 导入导出 UI。

## Round FS-027：术语库导入 / 导出 UI

### 目标
CSV / YAML / JSON 三格式上传导入（含冲突预览：新增 / 覆盖 / 冲突数量）与下载导出。
### 输入
FS-014 io 模块。
### 要修改 / 新增的文件
glossary 页扩展、导入导出端点、`tests/ui/glossary_io.spec.ts`。
### 验收标准
导入前显示预览统计并需确认；冲突项（locked / approved 被覆盖）默认跳过且单独列出；导出文件可被 FS-014 重新导入（roundtrip）。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 禁止事项
导入不得静默覆盖 approved 术语。
### 产物
导入导出 UI + 测试。
### 下一轮衔接
FS-028 项目设置页。

## Round FS-028：项目设置页

### 目标
实现规格 §7.2：项目元信息、语言方向、输入输出目录、导出格式开关、自动进阶开关、成本上限、batch 参数。
### 输入
现有项目配置存储（project_registry / stage_state / configs）。
### 要修改 / 新增的文件
`frontend/settings-project.html` + js、设置读写端点与持久化、`tests/ui/settings_project.spec.ts`。
### 验收标准
规格 §7.2 全部 19 项可读写并持久化；成本上限 / batch 参数变更被调度器与 micro round 真实消费（测试或 dry-run 验证）；非法值有校验提示。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 禁止事项
目录设置不得允许指向仓库外任意路径并写入。
### 产物
项目设置页 + 测试。
### 下一轮衔接
FS-029 API 设置页。

## Round FS-029：API / 模型设置页

### 目标
实现规格 §7.3：provider / base URL / Key 状态检测（脱敏 sk-****abcd）/ 各阶段模型 / 采样参数 / rate limit / cost guard / 连接测试 / smoke test 按钮。
### 输入
`src/providers/`、model_router、`run_real_api_smoke.py`。
### 要修改 / 新增的文件
`frontend/settings-api.html` + js、key 状态检测端点（只返回是否存在 + 脱敏尾号）、连接测试端点、`tests/ui/settings_api.spec.ts`。
### 要执行的命令
`npm run dev:frontend`；`npm run test:ui`；可选 `python3 scripts/run_real_api_smoke.py --real`（最小 smoke）。
### 是否允许真实 API
是（仅连接测试 / 最小 smoke，用户在 UI 主动触发）。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 验收标准
完整 Key 永不出现在响应 / DOM / 日志（Playwright 断言 network 响应）；连接测试结果含模型名与延迟；更换生产模型操作被阻止并提示需用户确认（规格 §21.3）。
### 禁止事项
不得提供"显示完整 Key"功能；不得把 Key 写入前端可读配置。
### 产物
API 设置页 + 测试。
### 下一轮衔接
FS-030 报告与导出入口。

## Round FS-030：报告页 + 导出入口页（MVP 版）

### 目标
报告页：列出 round / consistency / cost / worker / scheduler 报告，支持按阶段 / round / 时间过滤与 Markdown 查看。导出入口页：draft 导出（现有 exporter 能力）+ 后续导出项占位。
### 输入
`workspace/round_reports/`；`reports/`；exporter。
### 要修改 / 新增的文件
`frontend/reports.html`、`frontend/export.html`（改造现有）、对应端点、`tests/ui/reports.spec.ts`。
### 验收标准
报告列表与磁盘真实文件一致；过滤器可用；导出触发后显示路径与文件列表（规格 §8.4）；MVP 八页全部入侧边导航且可互相跳转。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 禁止事项
报告查看不得渲染含真实正文的大文件全文（截断 + 提示）。
### 产物
报告页 + 导出入口；**Web UI MVP 完成闸门**（对照 `phase_acceptance_criteria.md` Web UI MVP 节逐条核对并出报告）。
### 下一轮衔接
S6 Phase B 工具链（若 Phase A 已完成）或继续 S2。

---

# Stage S6：Phase B 一致性检查工具链

## Round FS-031：chapter manifest builder（Level 0）

### 目标
构建全书章节 manifest：chapter_id / 标题 / 段数 / segment 数 / draft 状态 / 来源 run / 哈希。
### 要修改 / 新增的文件
`scripts/build_chapter_manifest.py`、`src/consistency/manifest.py`、`tests/test_chapter_manifest.py`；输出 `workspace/manifests/chapter_manifest.json`（gitignore）。
### 要执行的命令
`python3 scripts/build_chapter_manifest.py --json`；`npm run test:py`。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
否 / 否。
### 验收标准
613 章全覆盖；漏章 / 重复章被显式列出；增量重建只处理变更章节。
### 禁止事项
不得将正文写入 manifest。
### 产物
manifest 工具 + 测试。
### 下一轮衔接
FS-032 segment index。

## Round FS-032：segment index builder（Level 0–1）

### 目标
构建 segment 级索引：segment_id ↔ 章节 / 段落映射、源文长度、译文长度、状态；检测漏段与错位。
### 要修改 / 新增的文件
`scripts/build_segment_index.py`、`src/consistency/segment_index.py`、`tests/test_segment_index.py`。
### 验收标准
漏段 / 错位检测对人工构造的 fixture 100% 召回；全书索引构建峰值内存可控（流式）。
### 是否允许真实 API
否。
### 产物
segment index + 测试。
### 下一轮衔接
FS-033 entity index。

## Round FS-033：entity index builder（Level 1）

### 目标
从 draft 抽取实体索引：人名 / 地名 / 组织 / 技能 / 道具 / 称号的 source→target 出现映射与频次。
### 输入
FS-015 usage index 基础；规则 + 词典启发式（不调模型）。
### 要修改 / 新增的文件
`scripts/build_entity_index.py`、`src/consistency/entity_index.py`、`tests/test_entity_index.py`。
### 验收标准
fixture 上同源多译 / 同译多源可检出；高频未收录术语 top-N 列表生成；输出落 `workspace/indexes/`。
### 是否允许真实 API
否。
### 产物
entity index + 测试。
### 下一轮衔接
FS-034 冲突统计。

## Round FS-034：glossary conflict audit（Level 2）

### 目标
将 entity index 与 glossary 比对，输出冲突统计：违反 locked 术语、未收录高频实体、多译冲突，并区分 blocking / non-blocking。
### 要修改 / 新增的文件
`scripts/audit_glossary_conflicts.py`、`src/consistency/conflict_audit.py`、`tests/test_conflict_audit.py`。
### 验收标准
blocking 判定规则文档化（locked / approved 术语被违反 = blocking）；统计可复现（同输入同输出）；报告含逐冲突的章节 / segment 定位。
### 是否允许真实 API
否。
### 产物
冲突审计 + 测试。
### 下一轮衔接
FS-035 残留与结构审计。

## Round FS-035：source residual / 漏段 / 错位 / 格式审计

### 目标
整合源语言残留启发式（控制误判率）、漏段、章节错位、格式异常四类结构性审计为一个 audit 入口。
### 输入
FS-032 索引；现有 validator 的 source_residual 启发式（按 P1 清单修正误判）。
### 要修改 / 新增的文件
`scripts/audit_draft_structure.py`、`tests/test_draft_structure_audit.py`。
### 验收标准
四类问题各有 fixture 测试；误判样本回归集（已知误判不再误报）；输出按严重程度分级。
### 是否允许真实 API
否。
### 产物
结构审计工具 + 测试。
### 下一轮衔接
FS-036 fix plan。

## Round FS-036：local fix plan 与局部重译计划（Level 3 / 5）

### 目标
将 FS-034 / FS-035 的 blocking 问题汇成 local fix plan：可规则修正项（术语替换）生成补丁计划；需重译项生成局部重译任务清单（segment 粒度），并可被调度器消费。
### 要修改 / 新增的文件
`scripts/build_local_fix_plan.py`、`scripts/apply_term_fixes.py`（dry-run 优先）、`src/scheduler/task_planner.py`（接入 consistency 子任务分支）、tests。
### 要执行的命令
`python3 scripts/build_local_fix_plan.py --json`；`python3 scripts/apply_term_fixes.py --dry-run`。
### 是否允许真实 API
否（重译执行在 FS-037 / 调度器轮）。
### 验收标准
fix plan 列出影响章节 / segment / 术语 / 修正方式；apply dry-run 显示逐处 diff；应用后不触碰原文与 checkpoint 历史。
### 禁止事项
规则替换不得用于非确定性修改（那类必须进重译清单）。
### 产物
fix plan 工具链。
### 下一轮衔接
FS-037 模型仲裁与 Phase B 收尾。

## Round FS-037：Level 4 模型仲裁与 Phase B 完成闸门

### 目标
对规则无法判定的冲突小规模调用模型仲裁（限额）；执行局部重译；生成 full draft consistency report；核对 Phase B 完成标准。
### 是否允许真实 API
**是**（仲裁 + 局部重译，受 max-api-calls / cost guard 限制）。
### 要修改 / 新增的文件
`scripts/arbitrate_conflicts.py`、consistency report 生成器；报告（统计版）入 `workspace/consistency_audit/`。
### 验收标准
`phase_acceptance_criteria.md` Phase B 节全部 PASS：blocking conflicts=0、报告完整、索引齐备。
### 禁止事项
仲裁不得演变为全文重审；单轮仲裁调用数有硬上限。
### 产物
Phase B 完成报告。
### 下一轮衔接
FS-038 baseline lock。

---

# Stage S7：Phase C baseline lock

## Round FS-038：baseline lock 与只读保护

### 目标
生成 `draft_full_baseline/`（全书 draft 快照）+ `draft_full_baseline_metadata.json`（哈希 / 章节清单 / 来源 run / consistency report 引用），并实现写保护（管线代码拒绝写 baseline 路径 + 文件系统只读位）。
### 要修改 / 新增的文件
`scripts/lock_baseline.py`、`src/translation/` 写路径守卫、`tests/test_baseline_lock.py`。
### 要执行的命令
`python3 scripts/lock_baseline.py --dry-run` → 实跑；`npm run test:py`。
### 是否允许真实 API
否。
### 验收标准
metadata 含全章节哈希；任何管线写 baseline 的尝试抛错（测试验证）；Phase A/B 未完成时 lock 脚本拒绝执行。
### 禁止事项
不得提交 baseline 正文到 Git。
### 产物
baseline + 保护机制。
### 下一轮衔接
FS-039 go decision。

## Round FS-039：baseline go decision 与 Phase D handoff

### 目标
生成 `draft_full_baseline_go_decision.md`（引用 Phase A/B 报告逐条核对规格 §14.3），并写 Phase D handoff（R-MR 队列起点、模型 profile、checker 清单）。
### 验收标准
go decision 逐条对照 §14.3 且结论明确；scheduler task planner 的 phase 判定切换到 refinement。
### 是否允许真实 API
否。
### 产物
go decision + handoff；**Phase C 完成**。
### 下一轮衔接
FS-040 润色工具链。

---

# Stage S8：Phase D 润色工具链与 R-MR 推进

## Round FS-040：R-MR 队列规划器

### 目标
把 3ch roadmap 的 R-MR-001…148 队列接入 task planner：从 baseline 读取输入、按 3 章 micro round 规划润色批次。
### 要修改 / 新增的文件
`scripts/plan_refine_micro_rounds.py`（或扩展现有 planner）、task planner R-MR 分支、tests。
### 验收标准
R-MR 队列与 baseline 章节清单一致；dry-run 输出首个 R-MR 的批次计划。
### 是否允许真实 API
否。
### 产物
R-MR 规划器。
### 下一轮衔接
FS-041 refine runner supervised 化。

## Round FS-041：refine runner supervised 化与 checkpoint 对齐

### 目标
将 `src/translation/refine_runner.py` 对齐 micro round 体系：supervised、checkpoint、budget、compact progress，与 `run_micro_round.py --phase refine`（新增）集成。
### 要修改 / 新增的文件
`run_micro_round.py`（phase 扩展）、refine_runner、tests。
### 要执行的命令
`python3 scripts/run_micro_round.py --phase refine --dry-run --fake-provider`。
### 是否允许真实 API
否（fake provider 验证）。
### 验收标准
refine micro round dry-run 端到端通过；中断后续跑不重复润色；输入严格来自 baseline（只读）。
### 禁止事项
refine 不得写 baseline；不得重新翻译（prompt 层约束 + 校验）。
### 产物
supervised refine runner。
### 下一轮衔接
FS-042 diff / change_log。

## Round FS-042：diff 与 change_log 生成

### 目标
每个 R-MR 自动生成 baseline vs refined 的 segment 级 diff 与结构化 change_log（修改类型 / 比例统计）。
### 要修改 / 新增的文件
`src/refinement/diff_builder.py`、`scripts/build_refine_diff.py`、tests。
### 验收标准
diff 比例统计可复现；change_log 含 per-segment 修改类别；产物落 run 目录（gitignore）。
### 是否允许真实 API
否。
### 产物
diff 工具链。
### 下一轮衔接
FS-043 三 checker。

## Round FS-043：over-refinement / terminology / character voice checkers

### 目标
实现三个规则 checker：过度润色（diff 比例 / 长度膨胀阈值）、术语保持（locked 术语在 refined 中不被改写）、角色语气（character_profile 关键标记词保持）。
### 要修改 / 新增的文件
`src/refinement/checkers.py`、`scripts/check_refinement_quality.py`、tests。
### 验收标准
三 checker 各有正反 fixture；blocking 判定标准文档化；接入 R-MR 收尾自动执行。
### 是否允许真实 API
否。
### 产物
质量 checker 套件。
### 下一轮衔接
FS-044 真实 R-MR 推进。

## Round FS-044：R-MR 批量推进启动轮

### 目标
真实 API 执行 R-MR-001 起步（先 1–2 个 MR 验证质量），确认 checker 与报告链路后进入批量推进（调度器接管）。
### 是否允许真实 API
**是**（refinement_primary；更强模型需用户确认后才切换）。
### 要执行的命令
调度器 tick 或 `run_micro_round.py --phase refine --real-api`；前后 orphan / gate 检查。
### 验收标准
首 2 个 R-MR 完成且三 checker 无 blocking；diff / change_log / round report 齐备；成本记录在案。
### 禁止事项
首轮验证未过不得批量推进。
### 产物
R-MR 推进运行态。
### 下一轮衔接
按 R-MR 队列批量执行（周期插入 FS-009 式健康检查）；完成后 FS-045。

## Round FS-045：Phase D 收尾与 refined full candidate 闸门

### 目标
全书 refined 完成核对（规格 §15.2 全条件）、refined export、`refined_full_candidate/` 生成。
### 验收标准
`phase_acceptance_criteria.md` Phase D 节全部 PASS。
### 是否允许真实 API
是（仅收尾修补）。
### 产物
Phase D 完成报告 + refined candidate。
### 下一轮衔接
FS-046 终检。

---

# Stage S9：Phase E 终检与 production_candidate

## Round FS-046：final review index 与 diff ratio audit（Level 0–2）

### 目标
构建 refined metadata / diff index，统计修改比例分布，标记异常章节（过大 / 过小 / 长度漂移）。
### 要修改 / 新增的文件
`scripts/build_final_review_index.py`、tests；输出 `workspace/final_review/`。
### 验收标准
异常判定阈值文档化；全书统计报告生成（无正文）。
### 是否允许真实 API
否。
### 下一轮衔接
FS-047。

## Round FS-047：过度润色候选定位与三方对比展开（Level 3–4）

### 目标
对异常章节做 source / draft / refined 三方局部展开，规则识别：信息增删、伏笔提前解释、暧昧强行明确化候选。
### 要修改 / 新增的文件
`scripts/expand_review_candidates.py`、tests。
### 验收标准
仅展开候选 segment（progressive disclosure，展开比例记录在报告）；候选清单含定位与理由。
### 是否允许真实 API
否。
### 下一轮衔接
FS-048。

## Round FS-048：semantic drift / terminology break 模型审查（Level 4–5）

### 目标
对规则无法判定的候选小规模模型审查（审查模型 profile，限额）。
### 是否允许真实 API
**是**（限额审查）。
### 要修改 / 新增的文件
`scripts/model_review_candidates.py`、审查记录（统计版）。
### 验收标准
每条审查结论含 segment 定位 / 问题类型 / 建议处置；调用数 ≤ 预算且记录成本。
### 禁止事项
不得借审查之名全文重读。
### 下一轮衔接
FS-049。

## Round FS-049：终检 local fix plan 执行（局部重润色）

### 目标
对确认问题执行局部重润色 / 修正，复检通过。
### 是否允许真实 API
是（仅 fix plan 范围内）。
### 验收标准
fix plan 全项闭环；复检 blocking quality issue=0。
### 产物
修正记录 + 复检报告。
### 下一轮衔接
FS-050。

## Round FS-050：production_candidate 生成

### 目标
生成 `production_candidate/` + `production_candidate_metadata.json` + `production_candidate_go_decision.md`，对照规格 §16.3 / §17。
### 要修改 / 新增的文件
`scripts/build_production_candidate.py`、tests。
### 验收标准
metadata 含版本链（draft→baseline→refined→candidate 哈希引用）；go decision 明确"未标记 human_approved_final、未发布"；写保护同 baseline。
### 是否允许真实 API
否。
### 禁止事项
**绝对不得**标记 human_approved_final；不得提交正文。
### 产物
production_candidate；**自动化生产流程主链贯通**。
### 下一轮衔接
S10–S13 补全 UI 与同步主线。

---

# Stage S10：角色 / 世界观 / 翻译记忆 UI

## Round FS-051：角色设定页

### 目标
实现规格 §7.9：角色列表 + 14 项字段编辑（别名 / 译名 / 称呼关系 / 第一人称 / 口癖 / 敬语 / 性格 / 风格 / 禁止事项 / 出场章节 / 关系 / 备注）。
### 输入
configs/character_profile + FS-013 式 CRUD 内核（本轮补 character store）。
### 要修改 / 新增的文件
`frontend/characters.html` + js、`src/glossary/character_store.py`（或独立模块）、端点、`tests/ui/characters.spec.ts`。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 验收标准
全字段 CRUD；改动被 prompt builder 消费（dry-run 验证注入变化）；出场章节联动章节页跳转。
### 禁止事项
不得在本轮重写 prompt 注入策略（沿用 FS-016）。
### 产物
角色设定页。
### 下一轮衔接
FS-052。

## Round FS-052：世界观 / 设定页

### 目标
实现规格 §7.10：14 类世界观条目的分类管理与编辑。
### 要修改 / 新增的文件
`frontend/world.html` + js、world_bible store + 端点、`tests/ui/world.spec.ts`。
### 验收标准
条目分类 / 搜索 / CRUD 可用；与 glossary 关联条目可互相跳转。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 产物
世界观页。
### 下一轮衔接
FS-053。

## Round FS-053：翻译记忆页

### 目标
实现规格 §7.11：TM 条目查看（source / draft / refined / user revised / final + change reason + applied_* 标记）与搜索过滤。
### 输入
`workspace/translation_memory/`；现有 TM 资产模块。
### 要修改 / 新增的文件
`frontend/tm.html` + js、TM 查询端点、`tests/ui/tm.spec.ts`。
### 验收标准
规格 §7.11 全 12 字段呈现；按 applied 状态过滤；大数据量分页。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 产物
TM 页。
### 下一轮衔接
S11 对照页。

---

# Stage S11：译文对照阅读页

## Round FS-054：对照页基础（双栏 + 段落对齐）

### 目标
实现规格 §7.7 基础：原文 + 初翻双栏、段落级对齐、segment_id 显示、章节跳转、搜索。
### 要修改 / 新增的文件
`frontend/reader.html` + js、章节内容端点（按章按需加载）、`tests/ui/reader.spec.ts`。
### 验收标准
对齐以 segment_id 为准（错位时显式标红而非静默错排）；长章节滚动流畅；阅读排版舒适（行宽限制、留白，规格 §8.1）。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 禁止事项
不得一次加载全书。
### 产物
对照页基础。
### 下一轮衔接
FS-055。

## Round FS-055：多模式对照与高亮

### 目标
支持规格 §7.7 全部 6 种栏组合（含润色 / 用户修改稿栏）；术语命中高亮、角色名高亮、栏间 diff 显示。
### 验收标准
6 模式切换无刷新丢位；术语高亮数据来自 usage index；diff 高亮与 FS-042 diff 一致。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 产物
完整对照视图。
### 下一轮衔接
FS-056。

## Round FS-056：审阅标记与备注

### 目标
段落 / segment 级：标记问题（重译 / 润色 / 术语问题）、人工备注、标记已审阅；标记数据进入章节页统计与 fix plan 输入。
### 要修改 / 新增的文件
review 标记存储（`workspace/review/`）、端点、UI、`tests/ui/reader_review.spec.ts`。
### 验收标准
标记持久化且刷新后保留；"需要重译"标记可被 FS-036 fix plan 工具消费；标记操作有 toast 反馈。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 产物
审阅标记系统。
### 下一轮衔接
S12 用户修改稿同步。

---

# Stage S12：用户修改稿同步主线

## Round FS-057：修改稿解析与自动对齐内核

### 目标
实现规格 §19.2：上传文本（单章 / 多章 / 全书）解析为段落，并按 chapter_id / paragraph_id / 文本相似度自动对齐到 segment_id。
### 要修改 / 新增的文件
`src/user_revision/parser.py`、`src/user_revision/aligner.py`、`tests/test_user_revision_align.py`。
### 验收标准
对未改动文本对齐率 100%（fixture）；轻度修改（润色级）对齐率 ≥95%；无法对齐项明确输出为 unaligned 列表而非强行匹配。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
否 / 否。
### 禁止事项
对齐失败不得猜测覆盖（规格 §19.2）。
### 产物
对齐内核。
### 下一轮衔接
FS-058。

## Round FS-058：人工对齐模式

### 目标
为 unaligned 项提供 UI 人工对齐：左侧系统 segment、右侧用户段落，手动连线 / 拆分 / 合并 / 标记跳过。
### 要修改 / 新增的文件
`frontend/upload-align.html` + js、对齐会话端点、`tests/ui/manual_align.spec.ts`。
### 验收标准
人工对齐结果与自动对齐合并为完整映射；会话可中断恢复；未完成对齐不得进入下一步。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 产物
人工对齐模式。
### 下一轮衔接
FS-059。

## Round FS-059：revision diff 与 sync plan 生成器

### 目标
实现规格 §19.3：基于对齐映射生成 diff，分类识别（术语 / 人名 / 风格 / 信息增删），生成 sync plan（12 项内容齐全）。
### 要修改 / 新增的文件
`src/user_revision/diff.py`、`src/user_revision/sync_plan.py`、`scripts/build_sync_plan.py`、tests。
### 验收标准
sync plan 含规格 §19.3 全部 12 项；术语修改识别与 glossary 比对联动；plan 为纯计划（生成时零副作用）。
### 是否允许真实 API
否。
### 产物
sync plan 生成器。
### 下一轮衔接
FS-060。

## Round FS-060：上传页与 sync plan 确认 UI

### 目标
实现规格 §7.12 上传页：上传 → 解析统计反馈 → 对齐结果 → diff 预览 → sync plan 展示 → 分项确认（术语 / 角色 / TM / 重译计划各自可勾选）。
### 要修改 / 新增的文件
`frontend/upload.html` + js、上传与 plan 端点、`tests/ui/upload.spec.ts`。
### 验收标准
上传后显示解析数量（规格 §8.4）；sync plan 确认是显式分项操作 + 整体二次确认；未确认前无任何数据被写入。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 禁止事项
不得提供"一键全部同步且跳过预览"。
### 产物
上传与确认 UI。
### 下一轮衔接
FS-061。

## Round FS-061：同步执行引擎

### 目标
实现规格 §19.4：确认后的 sync plan 写入 translation memory / glossary / character profile / local fix plan / revised output / audit report。
### 要修改 / 新增的文件
`src/user_revision/sync_executor.py`、tests（重点：禁写路径测试）。
### 验收标准
同步产物全部落规定路径；对原文 / baseline / production_candidate 的写尝试被代码层拒绝（测试验证）；audit report 记录每项变更来源。
### 是否允许真实 API
否。
### 禁止事项
**绝对禁止**覆盖原文、baseline、production_candidate、human_approved_final。
### 产物
同步执行引擎。
### 下一轮衔接
FS-062。

## Round FS-062：局部重译 / 重润色计划接入与全书一致性同步

### 目标
sync plan 产生的重译 / 重润色任务接入调度器（task planner 新分支）；术语级修改触发受影响章节的一致性复检（基于 usage index 定位，非全书扫描）。
### 是否允许真实 API
是（仅 plan 范围内的局部重译 / 重润色）。
### 验收标准
端到端演练：上传修改稿 → plan → 确认 → 同步 → 局部重译完成 → 一致性复检通过 → revised output 可在对照页第 4 栏查看。
### 产物
**用户修改稿同步主线贯通**。
### 下一轮衔接
S13 导出。

---

# Stage S13：导出系统完整化

## Round FS-063：导出内核（双语 MD / TXT / EPUB / package）

### 目标
扩展 exporter：纯译文 MD、双语对照 MD、TXT、EPUB、production candidate package（含 glossary / character / world / TM / 报告，规格 §7.14）。
### 要修改 / 新增的文件
`src/translation/exporter.py` 扩展或 `src/export/`、EPUB 依赖（requirements 记录）、tests。
### 验收标准
各格式产物可打开且抽样章节内容正确；package 文件清单与 metadata 一致；产物路径在 gitignore 内。
### 是否允许真实 API
否。
### 产物
导出内核。
### 下一轮衔接
FS-064。

## Round FS-064：导出页完整 UI

### 目标
实现规格 §7.14 导出页：全部导出项 + 导出前置信息（版本 / candidate 状态 / human_approved_final 状态 / blocking issue / P2 backlog / 路径 / 文件列表）。
### 验收标准
存在 blocking issue 时导出 production package 需显式警告确认；导出完成显示路径与文件列表。
### 是否允许真实 API
否。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 产物
完整导出页。
### 下一轮衔接
S14 打磨。

---

# Stage S14：Web UI Final 打磨

## Round FS-065：全站一致性审计与修复

### 目标
审计 15 页：状态标签 / 色彩 / 按钮 / 中文文案 / 空态 / loading / 反馈是否全部走设计系统；输出 UI gap report 并修复 P1 项。
### 要执行的命令
`npm run test:ui`；逐页 Playwright 截图对比。
### 验收标准
gap report 中 P1=0；任何页面无硬编码状态串 / 色值（grep 验证）。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 产物
一致性审计报告 + 修复。
### 下一轮衔接
FS-066。

## Round FS-066：响应式与可访问性基础

### 目标
主要页面在 1280 / 1024 宽度可用；键盘可达性（焦点顺序 / Esc 关闭对话框）；表单 label 关联；对比度达标。
### 验收标准
Playwright 在两种视口跑通核心流程；axe 类基础检查无 critical。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 产物
响应式与 a11y 基线。
### 下一轮衔接
FS-067。

## Round FS-067：全量 Playwright 用户视角测试套件

### 目标
将零散 spec 整合为用户旅程套件：导入 → 配置 → 启动（dry-run）→ 监控 → 审阅 → 标记 → 上传修改 → 同步（fixture）→ 导出。
### 验收标准
`npm run test:ui` 全套通过且包含至少 1 条跨页完整旅程；CI 可重复执行（fixture 驱动、不依赖真实 API）。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 产物
完整 UI 测试套件。
### 下一轮衔接
FS-068。

## Round FS-068：P2 视觉 backlog 清理

### 目标
处理积累的 P2 视觉 / 信息密度 / 阅读体验项（来自各轮报告与 FS-065 gap report 的 P2 区）。
### 验收标准
backlog 逐项处置（修复或显式 defer 并记录理由）。
### 是否涉及 Web UI / 浏览器检查
是 / 是。
### 产物
打磨完成的 UI；**Web UI Final 闸门**（对照 acceptance criteria Web UI Final 节）。
### 下一轮衔接
S15 验收。

---

# Stage S15：端到端 DoD 验收

## Round FS-069：DoD 27 项逐条核对与缺口修复

### 目标
对照规格 §25 逐条核对 27 项，列出缺口并修复（小缺口当轮修，大缺口开补充轮）。
### 要执行的命令
全部 gate / status / 测试命令；`npm run test:ui`；`npm run test:py`。
### 验收标准
27 项核对表每项有证据链接（命令输出 / 报告 / 截图）。
### 是否允许真实 API
是（仅验证性 smoke）。
### 产物
DoD 核对表。
### 下一轮衔接
FS-070。

## Round FS-070：最终验收报告与状态冻结

### 目标
生成最终验收报告：版本链、成本总账、报告索引、已知 P2 backlog、human_approved_final 等待用户确认的说明。
### 验收标准
报告齐备；项目状态标记为"自动化生产流程完成，等待人工最终审阅"；**未标记 human_approved_final，未发布**。
### 禁止事项
不得自动标记 human_approved_final；不得对外发布。
### 产物
最终验收报告。
### 下一轮衔接
人工最终审阅（用户主导）；后续维护轮按需开启。

---

# 附：轮次状态总表

| 轮次 | Stage | 状态 |
| --- | --- | --- |
| FS-000 | S0 治理 | completed（2026-06-10） |
| FS-001 | S1 调度器 | completed（2026-06-11） |
| FS-002 | S1 调度器 | completed（2026-06-11） |
| FS-003 | S1 调度器 | completed（2026-06-11） |
| FS-004 | S1 调度器 | completed（2026-06-11） |
| FS-005 | S1 调度器 | completed（2026-06-11） |
| FS-006 | S1 调度器 | completed（2026-06-11） |
| FS-007 | S1 调度器 | completed（2026-06-11，S1 收官） |
| FS-008 | S2 Phase A | completed（2026-06-11；批量推进中：328/613（53.51%），ch1-328 连续，next D-MR-043） |
| FS-009 | S2 Phase A | recurring（Block #1…#8 已执行 2026-06-11；每 Block 重复） |
| FS-010 | S2 Phase A | not_started |
| FS-011 | S3 资产层 | completed（2026-06-11，批量间隙穿插） |
| FS-012 | S3 资产层 | completed（2026-06-11，批量间隙穿插） |
| FS-013 | S3 资产层 | completed（2026-06-11，批量间隙穿插） |
| FS-014 | S3 资产层 | completed（2026-06-11，批量间隙穿插） |
| FS-015 | S3 资产层 | completed（2026-06-11，批量间隙穿插） |
| FS-016 | S3 资产层 | completed（2026-06-11，批量间隙穿插；**S3 全 stage 完成**） |
| FS-017…FS-022 | S4 UI 基座 | not_started |
| FS-023…FS-030 | S5 UI MVP | not_started |
| FS-031…FS-037 | S6 Phase B | not_started |
| FS-038…FS-039 | S7 Phase C | not_started |
| FS-040…FS-045 | S8 Phase D | not_started |
| FS-046…FS-050 | S9 Phase E | not_started |
| FS-051…FS-053 | S10 资产 UI | not_started |
| FS-054…FS-056 | S11 对照页 | not_started |
| FS-057…FS-062 | S12 用户同步 | not_started |
| FS-063…FS-064 | S13 导出 | not_started |
| FS-065…FS-068 | S14 UI Final | not_started |
| FS-069…FS-070 | S15 验收 | not_started |
