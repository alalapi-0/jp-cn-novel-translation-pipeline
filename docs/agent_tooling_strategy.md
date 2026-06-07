# Agent Tooling Strategy

本文档定义未来推进轮 Agent 可用的工具分层、使用时机、验证方法与禁用条件。

## 工具分层

| 层级 | 代表工具 | 主要用途 |
|------|----------|----------|
| Repository Tools | git, gh, agent_gate, protocol checker | 仓库状态、合规、门控 |
| Development Tools | Python, Node, pytest, lint, static server | 实现、测试、本地预览 |
| Browser / Frontend Tools | Playwright, DOM/screenshot inspection | 前端 Workbench 可见性验证 |
| MCP Tools | Playwright MCP, GitHub MCP, SQLite MCP | Agent 增强操作（可选） |
| Model Provider Tools | fake, dry-run, OpenRouter, DeepSeek 等 | 翻译与 embedding 调用 |
| Data / Vector Tools | JSON/YAML inspector, Chroma/FAISS verifier | 数据与向量索引检查 |
| Review / QA Tools | 术语/角色/世界观一致性检查 | 质量与可复查性 |
| Git / Release Tools | git commit, gh pr | 版本与协作（需授权） |
| Safety Tools | secret scanner, cost guard, destructive guard | 安全边界 |

---

## Repository Tools

包括：git、git status、git diff、git log、git branch、GitHub CLI（若可用）、repo protocol checker、agent gate。

**规则：**

- 每轮开始必须 `git status`
- 每轮结束必须 `git status`
- 每轮 commit 前必须确认没有 `.env`、密钥、未授权原文/译文
- push 失败要记录，不要反复重试
- push 需用户明确授权（协议要求）

**验证：**

```bash
git status
git check-ignore -v .env 2>/dev/null || true
python3 scripts/agent_gate.py
python3 scripts/check_protocol_standard.py
python3 scripts/scan_repo_inventory.py   # Round 43 起
npm run check:tooling                    # 捆绑 gate + protocol + inventory + pytest
```

---

## Development Tools

包括：Python、Node.js、npm/pnpm/yarn、pytest、lint、type check、static file server、script runner。

**规则：**

- 当前早期不应引入过多依赖
- 实现轮才允许安装必要依赖，并写入文档说明原因
- 治理轮原则上不安装大型依赖
- 治理轮不写复杂业务代码

**验证：**

```bash
python3 --version
node --version 2>/dev/null || echo "node not installed"
pytest tests/ 2>/dev/null || echo "tests not ready"
```

---

## Browser / Frontend Tools

包括：Playwright、Playwright MCP、browser screenshot、DOM inspection、console log、network inspection、UI smoke test。

**规则：**

未来前端工作台出现后，Agent **不能只看代码**，必须打开页面验证。

**必须检查（Round 46 起）：**

1. 页面是否能启动
2. 页面是否能加载数据
3. 术语库页面是否显示
4. 人物表页面是否显示
5. 原文译文对照页面是否显示
6. 润色 diff 页面是否显示
7. 控制台是否严重报错
8. 关键按钮是否存在
9. 页面是否符合当前流程

**禁用：** 治理轮（Round 02）不安装 Playwright；前端未实现时不强行浏览器测试。

---

## MCP Tools

**规划 MCP：**

| MCP | 必须性 | 阶段 | Round 45 状态 |
|-----|--------|------|----------------|
| Playwright MCP (`@playwright/mcp`) | 前端验证轮推荐 | Round 45+ | 已配置；CLI fallback 已验证 |
| Filesystem MCP | 可选 | 环境支持时 | 已配置（workspace 根） |
| GitHub MCP | 可选 | PR/CI 轮 | 已配置（需 `GITHUB_TOKEN`） |
| SQLite MCP | 可选 | 使用 SQLite 后 | 未安装 |
| Browser MCP (`cursor-ide-browser`) | Round 46 增强 | Cursor 内置 | **已验证** snapshot/click/screenshot |
| chrome-devtools MCP | 可选 | UI 调试 | 已配置 |
| 自定义项目 MCP | 未来 | 按需 | — |

Round 45 验证清单：`docs/mcp_verification_checklist.md`。

**规则：**

- 不强制当前立刻安装所有 MCP
- 安装与验证安排见 `docs/mcp_playwright_setup_plan.md` 与 Round 41–50 路线图
- MCP 服务于实际推进，不为装工具而装工具
- MCP 失败时 fallback：Playwright 脚本、curl、静态 server、手动 DOM 检查
- MCP 不得读取 `.env` 或输出敏感信息
- MCP 不得自动公开发布译文
- MCP 不得绕过 Git 审查

## MCP 浏览器工具隔离规则

1. light_novel 项目不得依赖全局共享 chrome-devtools profile。
2. chrome-devtools 必须优先使用项目独立 profile（`scripts/chrome_devtools_mcp_light_novel.sh`）。
3. 如果 chrome-devtools 出现 profile lock，优先切换 playwright。
4. 端口冲突和 profile 冲突不同；profile 冲突必须通过独立 user-data-dir/profile 解决。
5. 多 Agent 并行时，不要 kill 其他项目进程。
6. 前端页面检查优先使用 playwright，chrome-devtools 作为补充。
7. 后续推进轮开始时应运行 `python3 scripts/check_mcp_health.py`。

详见 `docs/mcp_isolation_strategy_light_novel.md`。

---

## Model Provider Tools

包括：fake provider、dry-run provider、DeepSeek 类、Grok 类、OpenAI、OpenRouter、local/cloud embedding provider。

**规则：**

| 轮次类型 | 真实 API |
|----------|----------|
| 治理轮 | 禁止 |
| 实现轮 | 先 fake provider |
| API 接入轮 | controlled run + cost guard |
| 翻译执行轮 | 允许真实批量（需预算与 checkpoint） |

所有真实调用必须有 cost guard（`REAL_API_TESTS_ENABLED`、`MAX_TEST_COST_USD`）。

---

## Data / Vector Tools

包括：JSON inspector、YAML validator、SQLite、Chroma、FAISS、vector index verifier、embedding metadata checker。

**Round 48 已实现：**

```bash
python3 scripts/vector_db_inspect.py              # 缺失索引 → exit 1 WARNING（软 fallback）
python3 scripts/vector_db_inspect.py --example    # 脱敏 fixture：metadata 缺失 + orphan 演示
python3 scripts/vector_db_inspect.py --json --sample 3
```

- Schema：`data/schemas/vector_index_metadata.schema.json`
- 样例：`data/examples/vector_index_mock.example.json`
- 工作目录：`workspace/vector_store/`（默认 gitignore）

**规则：**

- 向量库早期以设计与检查为主（Round 48 完成 inspect MVP）
- 生成 embedding 前必须有 schema、metadata、过滤条件与成本控制
- 不允许无脑 embedding 全部内容
- 治理轮不生成 embedding、不建真实向量库

**过滤与成本 guard（生成 embedding 前必填）：**

| 键 | 用途 |
|----|------|
| `project_id` | 限定项目范围 |
| `language_direction` | jp_to_cn / cn_to_jp |
| `chapter_id` | 按章批量与增量索引 |
| `text_type` | 原文/译文/术语上下文等 |
| `model` / `version` | 模型与 pipeline 版本，防 drift |

Bulk embed 须通过 `cost_guard` / `controlled_run`（Round 47）且 `--dry-run` 先过预算估算。

**Round 49/50 依赖：**

- Round 49（质量审核 Workbench）不依赖向量库；`context_retriever` 可先用 glossary/TM 规则子集。
- Round 50（e2e trial）可选启用 vector search；试跑前运行 `vector_db_inspect.py`，index 缺失仅 WARNING。
- 未来 `context_retriever`（Round 15+）将消费 `vector_store` adapter 与 stable metadata 字段。

---

## Review / QA Tools

包括：terminology consistency、character voice、world bible conflict、paragraph alignment、bilingual output、diff checker、format checker、citation/copyright checker。

**规则：**

这些工具未来比“单纯翻译”更重要。项目价值在于一致性与可复查性。详见 `docs/quality_review_workflow.md` 与 Round 49。

---

## Git / Release Tools

包括：git commit、git push、gh pr create、gh pr checks。

**规则：**

- commit 需用户或轮次 Prompt 明确要求
- push 需用户授权
- 使用 `gh` 处理 PR 时遵循仓库 commit 风格

---

## Safety Tools

包括：secret scanner、`.env` checker、copyright source checker、large file checker、API budget guard、destructive operation guard。

**每轮都应：**

- 避免提交敏感信息
- 避免提交真实版权原文（除非用户明确要求）
- 避免提交真实译文（除非用户明确要求）
- 记录 push 失败而非反复重试

**Agent Gate（Round 41）：** 统一入口 `scripts/agent_gate.py`，见 `docs/agent_gate_and_protocol_check.md`。

---

## 工具选用决策树

```
开始轮次
  → git status
  → 读 round_state + agent_policy
  → 治理轮? → 仅文档/轻量脚本，无 API，无 Playwright 安装
  → 实现轮? → fake provider + pytest
  → 前端轮? → static server + Playwright（Round 44+）
  → API 轮? → dry-run + cost guard
  → 翻译执行轮? → checkpoint + 真实 API（授权后）
  → 结束 → git status + 更新 round_state + 报告
```
