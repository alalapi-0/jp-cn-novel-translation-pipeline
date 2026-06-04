# Continuous Multi-Agent Loop

## 目标

本协议定义后续 Cursor / Codex / 其他 Agent 如何复用仓库内状态、队列和检查入口，形成可暂停、可恢复、可审计的连续推进循环。本轮只建立基础设施，不实际启动多个 Agent。

## 基本循环

1. Runner Agent 执行 `python3 scripts/agent.py status`。
2. 若 `hard_blocked=true`，读取 `.agent_runtime/blockers.jsonl` 并停止。
3. 执行 `python3 scripts/agent.py next` 推进轮次。
4. 执行 `python3 scripts/run_real_api_smoke.py`；有明确授权时才执行 `--real`。
5. 读取 `.agent_runtime/queue.jsonl`。
6. 按任务类型分派：
   - `browser_inspection` → Browser Inspector Agent
   - `bugfix` / `test_fix` → Bugfix Agent
   - `quality_optimization` → Quality Optimizer Agent
   - `real_api_smoke` → Runner Agent
   - `documentation_sync` → Runner Agent 或文档 Agent
7. 页面相关任务执行 `python3 scripts/run_browser_inspection.py`。
8. 每轮结束更新 `governance/round_state.yaml`，检查 `git status` 和 `git diff`。
9. 用户或轮次 Prompt 明确要求时 commit；push 仍需明确授权。
10. 无硬阻塞时等待下一轮或按定时规则继续。

## 等待与自动继续

- `browser_check_interval_minutes` 存在于 `.agent_runtime/status.json`。
- Runner Agent 可比较 `last_browser_check_at` 与当前时间决定是否入队 `browser_inspection`。
- 等待任务时不占用真实 API。
- 缺少 API Key 时记录 `missing_api_key`，不阻断可 mock/dry-run 的工作。

## 队列规则

- 任务写入 `.agent_runtime/queue.jsonl`。
- 任务默认 `status=pending`。
- 任务必须包含 `id`、`type`、`priority`、`reason`、`created_at`、`updated_at`。
- 队列原因不得包含密钥、token、cookie 或真实 API 返回全文。

## 阻塞规则

- 硬阻塞通过 `python3 scripts/agent.py block --reason "..."` 写入。
- 解除阻塞通过 `python3 scripts/agent.py unblock`。
- 缺少 API Key 只有在当前轮唯一目标必须真实调用 API 且无替代时才 hard block。
- 推送权限缺失只在用户明确要求远程同步且无替代时 hard block。

## 安全规则

- 不读取 `.env` 内容。
- 不提交 `.env`、API Key、token、cookie。
- 不提交真实原文或真实译文。
- 不提交大体积浏览器 trace、截图、日志或真实 API 返回全文。
- GitHub 操作前必须 `git diff`。

## 验收标准

- 新 Agent 可以仅凭 `AGENTS.md`、本目录文档、`.agent_runtime/` 和脚本命令接管。
- 状态、队列、报告路径稳定。
- smoke、browser、quality、fix 四类运行产物有明确落点。
- 没有硬阻塞时可以继续下一轮；有硬阻塞时可解释原因并停止。
