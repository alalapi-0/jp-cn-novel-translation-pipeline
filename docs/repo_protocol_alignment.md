# Repo Protocol Alignment

## 读取到的协议文件

| 路径 | 版本 | 行数 | 说明 |
|------|------|------|------|
| `/Users/alalapi/PycharmProjects/novel-continuation-agent/governance/repo_protocol_standard.yaml` | 0.3.0 | 905 | 用户提供的完整通用协议（权威源，未修改） |
| `governance/repo_protocol_standard.yaml` | 0.3.0 | 905 | Round 02 已从权威源复制完整版 |
| `docs/archive/governance/repo_protocol_standard_truncated_backup.yaml` | 0.3.0 | 134 | 仓库原有截断版备份，仅含骨架 |

**判断**：原有仓库内协议**不完整**（约 15%），无法单独支撑 Agent Gate、Round 生命周期、MCP 安全等要求。Round 02 已备份截断版并复制完整协议，项目差异写入 `project.yaml` 与 `governance/novel_pipeline_contract.yaml`，**未改写协议正文**。

## 协议摘要

通用协议 v0.3.0 定义：

1. **权威层级**：`repo_protocol_standard.yaml` > `project.yaml` > `governance/round_state.yaml` > `agent_policy.yaml` > `file_role_map.yaml` > `AGENTS.md` > `README.md`
2. **Agent 阅读顺序**：协议 → 项目身份 → 策略 → 轮次状态 → 文件角色 → 流水线契约 → README → docs/index
3. **Round 生命周期**：intake → scan → plan → implement → validate → report → sync
4. **自动化门控**：`scripts/agent_gate.py`，exit 0/1/2
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

1. **Round 状态路径**：协议默认 `governance/round_state.yaml`；仓库另有 legacy `round_state/translation_pipeline_governance_round.yaml`。已在 `project.yaml` 记录 override，legacy 文件保留不删。
2. **提交策略**：原 `governance_rules.md` 写“每轮结束应 commit/push”；协议 `commit_policy.default` 为“用户明确要求才 commit”。Round 02 已修正治理规则为“用户或轮次 Prompt 明确要求时 commit”；push 仍需用户授权（协议 `approval_required`）。
3. **项目定位**：协议 `project_specific_extensions.current_reference_project` 偏中文生成仓库；本仓库定位为**中日互译流水线**。差异写入 `novel_pipeline_contract.yaml` 与 `project.yaml`，不修改协议正文。
4. **Round 编号**：用户 Step 4.2 与 Step 7 对 Round 41–43 语义略有不同；以 `docs/roadmap_rounds_41_50_tooling_and_workbench.md`（Step 7）为准。
5. **本地 tracked 内容**：`input_jp/` 等目录在磁盘有原文但 `.gitignore` 应阻止提交；Agent Gate 未来需验证 Git 索引不含敏感文件。

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
- `docs/roadmap_rounds_41_50_tooling_and_workbench.md`
- 工具链 Prompt 模板与 Round 41–50 任务书

## 后续轮次执行要求

1. **每轮开始**：按 `AGENTS.md` 阅读顺序读取；执行 `git status`；检查 `.env` 是否被跟踪。
2. **每轮结束**：更新 `governance/round_state.yaml`；必要时更新 `docs/reports/`；运行 `scripts/agent_gate.py`（Round 41 起）。
3. **协议检查**：Round 42 起运行 `scripts/check_protocol_standard.py`，输出合规报告。
4. **不得修改** `governance/repo_protocol_standard.yaml` 正文，除非同步 portable 标准本身；项目差异只写 `project.yaml` overrides。

## 不应立即强制执行的部分

- 完整 `skills/registry.json`、`agents/contracts/` 体系（本仓库尚未进入 Agent 运行时轮）
- Lark/Feishu 集成（协议 defer 至 Round 52+）
- 真实 embedding / 向量库 / 真实 API 调用
- Playwright / MCP 安装（Round 44–45）
- `governance/repo_inventory.generated.json` 自动生成（Round 43 审计后）

## 待人工确认事项

1. 是否将 legacy `round_state/translation_pipeline_governance_round.yaml` 内容迁移合并到 `governance/round_state.yaml`（当前保留双轨）。
2. 本地 `input_jp/`、`output_cn/` 历史 tracked 文件是否需从 Git 历史中清理（当前依赖 `.gitignore`，未改历史）。
3. 协议引用的 `docs/protocols/generated_asset_lifecycle.md` 等待实现轮按需创建，或在本仓库用 `docs/quality_review_workflow.md` 作为 interim 引用。
