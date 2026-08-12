# Agent 治理规则

## 每轮必须读取

每轮 Agent 必须先读取：

- `governance/repo_protocol_standard.yaml`
- `project.yaml`
- `AGENTS.md`
- `README.md`
- `docs/project_vision.md`
- `docs/architecture_overview.md`
- `docs/product_final_state_spec.md`
- `docs/final_state_implementation_roadmap.md`
- `docs/final_state_round_task_list.md`
- `docs/translation_production_protocol.md`
- `docs/translation_consistency_protocol.md`
- `docs/governance_rules.md`
- `docs/repo_protocol_alignment.md`
- `docs/agent_operating_manual.md`

如果这些 v2 文件不存在，先创建或补齐。旧 Round 路线图位于 `docs/archive/legacy_roadmaps/`，不得作为任务来源。

## 每轮必须声明

每轮报告必须声明：

1. 当前轮次。
2. 本轮类型：
   - `governance`
   - `implementation`
   - `translation_execution`
   - `review`
   - `frontend`
   - `api_integration`
   - `tooling`
   - `protocol_alignment`
3. 本轮目标。
4. 本轮不做事项。
5. 修改范围。
6. 验收标准。
7. 下一轮建议。

## 禁止事项

1. 不得提交 `.env`。
2. 不得提交 API Key。
3. 不得提交真实小说原文。
4. 不得把真实译文默认提交到公开仓库。
5. 不得跳过路线图乱做。
6. 不得把日译中和中译日逻辑混在一起。
7. 不得复制两套相同 shared core。
8. 不得写死模型供应商。
9. 不得在治理轮中启动真实翻译。
10. 不得在没有用户授权的情况下公开发布译文。
11. 不得直接复制参考仓库代码；只能迁移工程方法、架构方法和质量控制方法。
12. 不得把校验失败的模型输出写入 `translated` 或 `final`。
13. 不得绕过 provider adapter 直接在业务流程调用模型。
14. 不得让 exporter 调用模型或修改原文。

## 提交规则

本仓库采用 user-owned `local_only` Git 最终化策略。治理批准的 scoped candidate 默认停留在未 stage/commit/push 的本地工作树中；通用协议的 approved-round automatic stage/commit/push 在本仓库不适用。仅由已验证 scoped task / baseline-owned changes 产生的 dirty worktree warning 是预期、非阻断状态；真实 `FAIL` 或 `BLOCKED` 仍然阻断。

edit/build 请求和任何 Round Prompt 都不构成 Git 授权。只有用户在当前轮明确要求 commit 后，才可精确暂存本轮已批准路径并提交；禁止使用指向当前目录或全匹配路径的 `git add` 全量暂存形式。push 必须由用户在当前轮另行明确授权；push 失败后不得沿用旧授权重试。

无论是否获得 commit 授权，真实原文、真实译文、workspace runtime artifacts 和 secrets 永远不得提交。commit 前必须检查精确路径 diff 与 staged diff，确认没有任何上述内容。如果当前目录不是 Git 仓库，不得强行初始化 Git，应记录原因。

## Workspace 逐文件基线与门禁隔离

`project.yaml` 与 `governance/agent_policy.yaml` 必须维护语义一致的 `workspace_file_baseline` 机器策略：`root=workspace`、manifest 为 `.agent_runtime/inspection_reports/workspace_file_baseline.json`、verifier 为 `scripts/workspace_file_baseline.py`，并以 `per_file_sha256` 逐文件校验。

1. 任何已知或可能写入 `workspace` 的工具，运行前必须执行 `python3 scripts/workspace_file_baseline.py verify --json`，运行后必须再次执行同一命令。
2. 前置或后置 verify 发现 drift、返回非零或 verifier error 时均为硬阻断：立即停止并报告，不得继续工具链，也不得自动 `create` 或以 create/rebaseline 覆盖 drift。
3. `auto_rebaseline=false`。baseline `create` 与 rebaseline 都必须取得用户**当前轮明确授权**；历史授权、Round Prompt 与 edit/build 请求均无效。
4. 禁止在真实仓库工作树运行完整 `scripts/agent_gate.py`。真实工作树只可运行合同指定的 targeted/read-only checks；完整 gate 仅可在一次性隔离临时副本中运行。
5. 隔离副本产生的 `workspace/`、`reports/`、`.agent_runtime/` 等 workspace/reports/runtime outputs 不得写回真实仓库。

## 生产翻译 Worker 生命周期

1. 外部真实 API 必须使用 **supervised tick loop**；每个 tick 归还 Agent 控制权；长 foreground worker 已废弃。
2. Agent 额度翻译必须按 `docs/translation_production_protocol.md` 写入同构中间态。
3. Agent 停止 → 翻译 worker 必须停止（`workspace/control/stop_requested.json` + SIGTERM）。
4. 禁止无人监管后台真实 API worker（禁止对生产翻译使用 `nohup` / detached background worker）。
5. 生产续跑入口以 v2 任务清单为准；不得自动进入 R-MR。
6. 每个受控 batch 完成后生成报告、修复、测试、提交（授权时）并进入下一任务。
7. 全书一致性检查采用 **渐进式披露**，不得全文硬扫。见 `docs/translation_consistency_protocol.md`。
8. 模型切换须先 A/B（`scripts/model_ab_test.py`）；DeepSeek 保留 fallback。

## 工具链规则

1. 治理轮不默认安装大型工具（Playwright、向量库、重型 MCP 等）。
2. 实现轮可以安装必要依赖，但必须写入文档说明原因。
3. 前端轮必须逐步引入 Playwright（Round 44 起搭框架，Round 46 起浏览器验证）。
4. MCP 接入必须先写安装和验证计划（见 `docs/mcp_playwright_setup_plan.md`）。
5. MCP 不可替代 Git 审查。
6. MCP 不可读取并输出敏感信息。
7. 真实 API 轮必须启用 dry-run 和 cost guard。
8. 向量库轮必须先有 metadata 和过滤设计（Round 48）。
9. Review Workbench 不能只看代码；Round 46 起必须浏览器验证。
10. 每个工具都必须有 fallback 或硬阻塞判断（见 `docs/agent_tooling_strategy.md`）。

## MCP / Browser Tools Runbook

当前项目的 MCP / 浏览器工具使用规则以以下文件为准：

- `docs/runbooks/mcp_browser_tools_runbook.md`

后续 Agent 在涉及工具、前端、浏览器、MCP、Playwright、Chrome DevTools 时必须先读取该 Runbook。

## 工具隔离原则

1. Playwright 是默认浏览器自动化工具。
2. chrome-devtools 需要项目独立 profile 后再作为补充工具。
3. chrome-devtools profile 冲突时不得阻塞任务，应 fallback 到 Playwright。
4. 端口冲突时自动换端口，不 kill 其他项目进程。
5. 多 Agent 并行时不得共享默认 Chrome profile。

## MCP 浏览器工具隔离规则

1. light_novel 项目不得依赖全局共享 chrome-devtools profile。
2. chrome-devtools 必须优先使用项目独立 profile。
3. 如果 chrome-devtools 出现 profile lock，优先切换 playwright。
4. 端口冲突和 profile 冲突不同；profile 冲突必须通过独立 user-data-dir/profile 解决。
5. 多 Agent 并行时，不要 kill 其他项目进程。
6. 前端页面检查优先使用 playwright，chrome-devtools 作为补充。
7. 后续推进轮开始时应运行 MCP 健康检查。

## 通用协议规则

1. 每轮必须检查是否存在 `governance/repo_protocol_standard.yaml`。
2. 如果存在，必须读取并遵守；项目差异通过 `project.yaml` overrides 记录。
3. 如果协议与仓库规则冲突，必须记录于 `docs/repo_protocol_alignment.md`，不得静默覆盖。
4. 不得擅自修改协议本体；升级须备份并写迁移报告。
5. 协议对齐报告有变更时必须更新 `docs/repo_protocol_alignment.md`。
6. Round 41–42 曾将 `scripts/agent_gate.py` 与 `scripts/check_protocol_standard.py` 纳入协议检查；这是历史实现记录，不授予在真实工作树运行完整 gate 的当前执行权限。现行执行边界以“Workspace 逐文件基线与门禁隔离”为准。

## 参考方法吸收规则

1. RM 轮次表示 Reference Method Absorption，不覆盖既有 Round 00–50。
2. stable ID、JSONL 中间态、Prompt Version、ResponseExtractor、Validator、Provider Adapter 和 Exporter-only 是后续实现轮默认约束。
3. `JP_TO_CN` 与 `CN_TO_JP` 必须保持方向分离，共享逻辑进入 shared core。
4. Checkpoint、LLM Response Cache、Translation Memory 必须分开设计和实现。
5. Web Review Workbench、EPUB、OCR、漫画处理、多 provider routing、真实 embedding 属于后续扩展，不得提前塞入 MVP 主线。
