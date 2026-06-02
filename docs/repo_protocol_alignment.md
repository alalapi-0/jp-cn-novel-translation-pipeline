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

1. 用户本轮要求完成后 commit 并 push；协议要求 commit 需用户或轮次 Prompt 明确要求，push 需用户明确授权。本轮 Prompt 已明确要求 commit/push，但 push 若权限或网络失败，只记录原因，不反复尝试。
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
2. 运行或手动对照 `docs/agent_gate_and_protocol_check.md`。
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

1. 是否将 legacy `round_state/translation_pipeline_governance_round.yaml` 内容迁移合并到 `governance/round_state.yaml`（当前保留双轨）。
2. 本地 `input_jp/`、`output_cn/` 历史 tracked 文件是否需从 Git 历史中清理（当前依赖 `.gitignore`，未改历史）。
3. 协议引用的 `docs/protocols/generated_asset_lifecycle.md` 等待实现轮按需创建，或在本仓库用 `docs/quality_review_workflow.md` 作为 interim 引用。
