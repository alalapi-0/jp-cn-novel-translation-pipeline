# Repo Protocol Alignment

## 读取到的协议文件

| 路径 | 版本 | 行数 | 说明 |
|------|------|------|------|
| `<workspace>/novel-continuation-agent/governance/repo_protocol_standard.yaml` | 0.3.0 | 905 | 用户提供的完整通用协议（权威源，未修改） |
| `governance/repo_protocol_standard.yaml` | 0.3.0 | 905 | Round 02 已从权威源复制完整版 |
| `docs/archive/governance/repo_protocol_standard_truncated_backup.yaml` | 0.3.0 | 134 | 仓库原有截断版备份，仅含骨架 |

**判断**：原有仓库内协议**不完整**（约 15%），无法单独支撑 Agent Gate、Round 生命周期、MCP 安全等要求。Round 02 已备份截断版并复制完整协议，项目差异写入 `project.yaml` 与 `governance/novel_pipeline_contract.yaml`，**未改写协议正文**。

## 协议摘要

通用协议 v0.3.0 定义：

1. **权威层级**：`repo_protocol_standard.yaml` > `project.yaml` > `governance/round_state.yaml` > `agent_policy.yaml` > `file_role_map.yaml` > `AGENTS.md` > `README.md`
2. **Agent 阅读顺序**：协议 → 项目身份 → 策略 → 轮次状态 → 文件角色 → 流水线契约 → README → docs/index
3. **Round 生命周期**：intake → scan → plan → implement → validate → report → sync
4. **自动化门控（通用协议历史能力）**：`scripts/agent_gate.py` 可产生 exit 0/1/2；本项目现行覆盖禁止在真实工作树运行完整 gate
5. **安全**：不读 `.env`、不提交密钥、治理轮不调真实 API、不默认 commit/push
6. **浏览器验证**：Playwright 仅用于 UI 验证，产物进 `artifacts/`

## 与当前仓库一致的部分

- `README.md`、`docs/`、`prompts/`、`scripts/`、`governance/` 目录存在
- `.gitignore` 已忽略 `.env`、原文、译文、`docs/reports/*.md`
- 双向流水线目录结构（`input_jp/cn`、`output_jp/cn`、`directions/`）与协议兼容的 mixed_code_and_content 类型一致
- 治理轮不写业务代码、不调用 API 的安全意识与协议一致
- Round 00–40 路线图、Prompt 模板体系符合多 Agent  handoff 方向

## 当前仓库缺失的部分

| 协议要求 | Round 02 前状态 | Round 02 动作 |
|----------|----------------|---------------|
| `AGENTS.md` | 缺失 | 已创建 |
| `project.yaml` | 缺失 | 已创建 |
| `governance/round_state.yaml` | 缺失 | 已创建 |
| `governance/agent_policy.yaml` 等策略文件 | 缺失 | 已创建 |
| `governance/novel_pipeline_contract.yaml` | 缺失 | 已创建 |
| `docs/archive/` | 缺失 | 已创建 |
| 完整 `repo_protocol_standard.yaml` | 截断 | 已复制完整版 |
| `scripts/agent_gate.py` | 缺失 | Round 41 实现 |
| `scripts/check_protocol_standard.py` 等 | 缺失 | Round 42 实现 |
| `docs/protocols/`、`docs/integrations/` 等引用文档 | 缺失 | 软阻塞，按需创建 |

## 当前仓库可能冲突的部分

1. **Round 状态路径**：协议默认 `governance/round_state.yaml`；legacy 治理状态已归档至 `docs/archive/legacy_roadmaps/translation_pipeline_governance_round.yaml`。已在 `project.yaml` 记录 override。
2. **提交策略（历史）**：原 `governance_rules.md` 写“每轮结束应 commit/push”；协议 `commit_policy.default` 为“用户明确要求才 commit”。Round 02 当时曾修正为“用户或轮次 Prompt 明确要求时 commit”，push 需用户授权。该叙述保留 Round 02 的历史事实，但现行规则已由下方 `local_only` 项目覆盖取代，Round Prompt 不再具有任何 Git 授权效力。
3. **项目定位**：协议 `project_specific_extensions.current_reference_project` 偏中文生成仓库；本仓库定位为**中日互译流水线**。差异写入 `novel_pipeline_contract.yaml` 与 `project.yaml`，不修改协议正文。
4. **Round 编号**：旧 Round 00–50 / RM 编号仅作历史；当前推进以 `docs/final_state_round_task_list.md` 的 FS-v2 任务为准。
5. **本地 tracked 内容**：`input_jp/` 等目录在磁盘有原文但 `.gitignore` 应阻止提交；敏感索引检查必须使用 targeted/read-only check，完整 gate 只能在不得回写的一次性隔离临时副本中验证。

## 现行项目覆盖：user-owned local-only Git 最终化

`project.yaml` 的 `agent_policy_standard.git_finalization` override 取代通用 approved-round automatic stage/commit/push。Judge `PASS` 与 Governor `APPROVE` 只批准 verified scoped candidate 在本地工作树完成；不得自动 stage、commit、checkout、merge 或 push。

采用该覆盖是为了让用户保有仓库历史和远端发布的最终控制权，同时允许通过验证的本地任务不因预期 dirty worktree warning 而被误判为失败。edit/build 请求与 Round Prompt 均不提供 Git 权限；commit 和 push 必须分别取得用户当前轮明确授权，push 重试也需要新授权。真实原文、真实译文、workspace runtime artifacts 与 secrets 在任何授权下都永不提交；真实 `FAIL` / `BLOCKED` 仍然阻断。

## 现行项目覆盖：Workspace 逐文件基线与完整门禁隔离

`project.yaml` 和 `governance/agent_policy.yaml` 以语义一致的 `workspace_file_baseline` 策略保护 `workspace`：manifest 为 `.agent_runtime/inspection_reports/workspace_file_baseline.json`，verifier 为 `scripts/workspace_file_baseline.py`，算法为 `per_file_sha256`。

- 任何已知或可能写入 `workspace` 的工具，运行前必须先执行 `python3 scripts/workspace_file_baseline.py verify --json`，结束后必须再次执行同一 verify 命令。
- drift、verify 非零或 verifier error 均为硬阻断；立即停止并报告，不得自动 create，也不得以 create/rebaseline 覆盖 drift。
- `auto_rebaseline=false`；baseline create 或 rebaseline 只有在用户**当前轮明确授权**后才可执行，Round Prompt 与 edit/build 请求不能授权。
- 禁止在真实仓库工作树运行完整 `scripts/agent_gate.py`。真实工作树仅运行合同指定的 targeted/read-only checks；完整 gate 只能在一次性隔离临时副本中运行，且隔离副本产生的 `workspace/`、`reports/`、`.agent_runtime/` 等 workspace/reports/runtime outputs 不得写回。
- 受保护的通用协议仍保留其 portable automation、after-editing、validation、drift-detection 与 inventory update 默认值；`project.yaml` 以五条精确 `project_overrides` 覆盖这些字段。写入型 protocol/inventory/report maintenance 只在当前任务明确拥有时运行，不是隐式 live-tree 验证。

## 需要新增的治理规则

已写入 `docs/governance_rules.md` 追加章节：

- 工具链规则 10 条
- 通用协议规则 6 条

## 需要新增的目录或文档

Round 02 已新增或更新：

- `docs/agent_tooling_strategy.md`
- `docs/mcp_playwright_setup_plan.md`
- `docs/agent_operating_manual.md`
- `docs/agent_gate_and_protocol_check.md`
- `docs/final_state_implementation_roadmap.md`
- `docs/final_state_round_task_list.md`
- 工具链 Prompt 模板与 Round 41–50 任务书

## 后续轮次执行要求

1. **每轮开始**：按 `AGENTS.md` 阅读顺序读取；执行 `git status`；检查 `.env` 是否被跟踪。
2. **每轮验证**：真实工作树只运行合同指定的 targeted/read-only checks；已知或可能写入 `workspace` 的工具必须前后各执行 baseline verify。完整 `scripts/agent_gate.py` 只可在不得回写的一次性隔离临时副本中运行。
3. **协议检查**：Round 42 起提供 `scripts/check_protocol_standard.py`；因其会写合规报告，现行规则只允许在一次性隔离副本运行并禁止写回。真实工作树使用合同指定的 targeted/read-only checks。
4. **不得修改** `governance/repo_protocol_standard.yaml` 正文，除非同步 portable 标准本身；项目差异只写 `project.yaml` overrides。

## 参考仓库方法迁移与通用协议的关系

本轮参考仓库方法迁移属于项目级业务方法治理，不属于通用协议正文变更。AiNiee、GalTransl、TranslateBooksWithLLMs、epub-translator-oomol、SakuraLLM、LiteraryTranslation、LunaTranslator、BallonsTranslator、epub-translator-slyh 的经验只转化为当前项目的文档、方法栈、数据契约、路线图和后续 Prompt，不复制参考仓库代码，也不改变 `governance/repo_protocol_standard.yaml` 的权威层级。

## 本轮方法迁移必须遵守的协议要求

1. 权威顺序仍为 `governance/repo_protocol_standard.yaml` > `project.yaml` > `governance/round_state.yaml` > policy YAML > `AGENTS.md` > `README.md`。
2. 真实 API、真实翻译、embedding、向量库和复杂前端实现不得在治理轮执行。
3. `.env`、真实原文、真实译文、敏感日志和用户隐私不得提交。
4. 项目特有差异写入 `project.yaml`、`governance/novel_pipeline_contract.yaml` 或本对齐文档。
5. 参考方法新增文档必须进入 `docs/` 和 `docs/index.md`，后续 Prompt 进入 `prompts/`。

## 当前仓库与协议一致的部分

当前仓库已经具备 `governance/`、`docs/`、`docs/archive/`、`prompts/`、`scripts/`、`src/`、`tests/` 等协议推荐结构。`input_jp/`、`input_cn/`、`output_cn/`、`output_jp/` 和 `workspace/` 已由 `.gitignore` 与 `governance/file_role_map.yaml` 标记为需保护或中间产物目录。

本轮引入的 stable ID、JSONL 中间态、Prompt Version、ModelRun、Checkpoint、Provider Adapter 和 Exporter 原则与协议的“可机读、可审计、可回退、避免 secrets”目标一致。

## 当前仓库与协议可能冲突的部分

1. **历史轮次快照**：当时用户要求完成后 commit 并 push，且当时规则仍将 Round Prompt 视为 commit 权限来源；该轮 Prompt 因而记录了 commit/push 请求，push 失败只记录原因、不反复尝试。本条仅保留当轮历史语境，不授予当前或未来轮次任何 Git 权限；现行 `local_only` 规则要求 commit 与 push 分别由用户在当前轮明确授权。
2. RM 路线新增一套编号，可能与既有 Round 00-50 混淆。因此 RM 文件必须明确 `RM` 只表示 Reference Method Absorption，不取代原路线。
3. 参考方法可能诱导提前实现真实 API、EPUB、Workbench、OCR 或多 provider routing；本轮只写文档，不执行这些功能。

## 本轮允许调整的范围

- 新增参考方法文档。
- 更新 README、docs 导航、治理规则、操作手册和核心设计文档。
- 新增 RM-01 到 RM-40 路线图。
- 新增 RM-01 到 RM-10 Prompt 草案。
- 更新 `governance/round_state.yaml` 记录本轮状态。

## 本轮禁止破坏的内容

- 不修改 `governance/repo_protocol_standard.yaml` 正文。
- 不读取或提交 `.env`。
- 不修改真实原文或真实译文。
- 不启动真实翻译、真实 API、embedding 或向量库。
- 不删除历史文档、legacy round state 或 archive 文件。
- 不把 `JP_TO_CN` 与 `CN_TO_JP` 混成不可分辨的一套规则。

## 后续 Agent 必须遵守的协议检查项

1. 先读取 `AGENTS.md`、协议、项目身份、治理规则和当前轮 Prompt。
2. 手动对照 `docs/agent_gate_and_protocol_check.md` 并运行合同指定的 targeted/read-only checks；该历史文档不授予在真实工作树运行完整 gate 的权限。
3. 确认 `.env` 未被跟踪。
4. 确认真实原文和真实译文未进入 Git diff。
5. 确认 RM 轮次与 Round 00-50 不混用。
6. 确认校验失败不写入 final。
7. 确认 provider 只能通过 adapter/registry 调用。
8. 确认 exporter 是最终阅读文件唯一生成入口。

## 不应立即强制执行的部分

- 完整 `skills/registry.json`、`agents/contracts/` 体系（本仓库尚未进入 Agent 运行时轮）
- Lark/Feishu 集成（协议 defer 至 Round 52+）
- 真实 embedding / 向量库 / 真实 API 调用
- Playwright / MCP 安装（Round 44–45）
- `governance/repo_inventory.generated.json` 自动生成（Round 43 审计后）

## 待人工确认事项

1. 是否将已归档 legacy `docs/archive/legacy_roadmaps/translation_pipeline_governance_round.yaml` 内容迁移合并到 `governance/round_state.yaml`。
2. 本地 `input_jp/`、`output_cn/` 历史 tracked 文件是否需从 Git 历史中清理（当前依赖 `.gitignore`，未改历史）。
3. 协议引用的 `docs/protocols/generated_asset_lifecycle.md` 等待实现轮按需创建，或在本仓库用 `docs/quality_review_workflow.md` 作为 interim 引用。
