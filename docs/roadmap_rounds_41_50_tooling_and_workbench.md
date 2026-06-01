# 工具链与 Review Workbench 路线图（Round 41–50）

本路线图承接 [`docs/roadmap_rounds_00_40.md`](roadmap_rounds_00_40.md) 的前 40 轮推进：Round 00–35 完成治理、共享核心、双向方向规则、Pipeline 骨架、CLI 与成本保护；Round 36–40 完成前端信息架构、静态 MVP、本地数据连接、编辑能力与短篇闭环验证。Round 41–50 聚焦 **Agent 工具链、协议门控、Playwright/MCP 浏览器验证、API 受控接入、向量库检查、质量审核工作台**，并在 Round 50 以 Agent 辅助的受控翻译试跑收束。每一轮开始前须读取 README、项目愿景、架构总览、治理规则、[`docs/agent_tooling_strategy.md`](agent_tooling_strategy.md) 与本路线图；不得越级执行，不得在未授权时处理真实版权长篇或调用真实 API。

---

## Round 41：Agent Gate MVP

### 轮次类型

tooling

### 背景

Round 00–40 已建立治理文档、协议对齐与工具策略，但 Agent 每轮仍依赖人工对照 checklist。`docs/agent_gate_and_protocol_check.md` 已规划统一入口 `scripts/agent_gate.py`，Round 02 仅做设计未实现。缺少确定性门控脚本会导致 secrets 泄露、原文/译文误提交、必读文档缺失等问题在实现轮被放大。

### 目标

实现 Agent Gate MVP：单一 CLI 入口，对仓库结构、必读文档、Git 忽略策略、敏感文件跟踪状态做确定性检查，输出本地报告并按 exit code 分级。

### 具体任务

1. 创建 `scripts/agent_gate.py`，支持 `--json`、`--strict` 参数与 `docs/reports/agent_gate_report.md` 输出。
2. 实现 `docs_exist`：检查 README、AGENTS.md、`project.yaml`、核心 docs（vision、architecture、governance_rules、index）。
3. 实现 `roadmap_exists`：检查 `docs/roadmap_rounds_00_40.md` 与本文件存在。
4. 实现 `gitignore_safe`、`env_not_tracked`、`input_sources_ignored`、`outputs_ignored`：确认 `.env` 未被跟踪、input/output 目录忽略策略生效。
5. 实现 `protocol_exists`、`protocol_alignment_exists`、`tooling_strategy_exists`、`mcp_plan_exists`、`frontend_plan_exists` 等文档存在性检查。
6. 实现 Git 状态摘要（未提交变更、疑似大文件、是否在 main 上）并写入报告。
7. 对齐 exit code：0=PASS、1=WARNING、2=BLOCKED；BLOCKED 条件包括 `.env` 被跟踪、必读 roadmap 缺失。
8. 在 `docs/agent_gate_and_protocol_check.md` 补充 MVP 已实现检查项清单与运行示例。
9. 添加 `tests/test_agent_gate.py`：至少覆盖 PASS/WARNING/BLOCKED 三种 exit code 的 fixture 场景。
10. 更新 `governance/round_state.yaml` 与 Round 41 本地报告。

### 产出文件

`scripts/agent_gate.py`、`tests/test_agent_gate.py`、更新后的 `docs/agent_gate_and_protocol_check.md`、`docs/reports/agent_gate_report.md`（本地 gitignore）、Round 41 轮次报告。

### 验收标准

1. `python3 scripts/agent_gate.py` 在当前仓库可运行并生成报告。
2. `.env` 被 Git 跟踪时 exit code 为 2（BLOCKED）。
3. 缺失 `docs/roadmap_rounds_41_50_tooling_and_workbench.md` 时至少 WARNING，strict 模式下 BLOCKED。
4. `--json` 输出机器可读结果，便于 CI 或 Agent 解析。
5. 脚本不调用 LLM、不读取 `.env` 内容、不访问外部 API。
6. pytest 覆盖核心检查项与 exit code 逻辑。
7. 报告路径在 `.gitignore` 中，不提交敏感扫描细节。

### 工具要求

- Python 3.10+、pytest。
- git CLI（`git status`、`git ls-files`、`git check-ignore`）。
- 每轮开始与结束运行 `python3 scripts/agent_gate.py`；exit 2 时停止推进。

### MCP / Playwright 要求

- 本轮不使用 Playwright 与 MCP。
- 若 Agent 环境自带 browser MCP，不得用于读取 `.env` 或仓库外路径。

### 安全要求

- 脚本只检查文件存在性与 Git 跟踪状态，不打印 `.env`、API Key 或真实原文/译文内容。
- 报告中的路径示例使用相对路径；疑似敏感文件只记录 basename 与 ignore 状态。
- 不得因 gate 失败而自动 `git add`、commit 或 push。

### 不做事项

不实现 Protocol Checker（留给 Round 42）；不安装 Playwright；不调用真实 API；不修改 `governance/repo_protocol_standard.yaml` 本体；不批量扫描 `input_jp/`、`input_cn/` 正文内容。

### 下一轮衔接

进入 Round 42，实现 Repo Protocol Checker，与 agent_gate 形成「结构门控 + 协议合规」双层检查。

---

## Round 42：Repo Protocol Checker

### 轮次类型

protocol / tooling

### 背景

Agent Gate 侧重文件存在与 Git 安全；`governance/repo_protocol_standard.yaml` 与 `project.yaml` 中的必填字段、automation_policy、allowed_actions 仍需机器可读校验。`docs/agent_gate_and_protocol_check.md` 已规划 `scripts/check_protocol_standard.py`，避免 Agent 误读协议或跳过 override 记录。

### 目标

实现协议标准检查脚本：解析协议 YAML 与 `project.yaml`，输出合规报告，并与 agent_gate 检查项 ID 对齐。

### 具体任务

1. 创建 `scripts/check_protocol_standard.py`，读取 `governance/repo_protocol_standard.yaml` 与 `project.yaml`。
2. 校验协议版本字段、`automation_policy`、exit code 定义与文档引用路径是否存在。
3. 校验 `project.yaml` 必填字段（项目 id、协议版本、override 指针）与 `docs/repo_protocol_alignment.md` 一致性摘要。
4. 检查 `governance/round_state.yaml` 是否包含 `round_id`、`status`、`real_api_called` 等关键字段。
5. 检查 `governance/agent_policy.yaml`、`governance/file_role_map.yaml`、`governance/novel_pipeline_contract.yaml` 存在且可解析。
6. 输出 JSON/Markdown 报告至 `docs/reports/protocol_check_report.md`（本地 gitignore）。
7. 定义 exit code：与 agent_gate 一致（0/1/2）；协议文件缺失或 parse 失败为 BLOCKED。
8. 在 agent_gate 中可选调用 protocol checker（`--with-protocol`）或文档说明两脚本串联顺序。
9. 添加 `tests/test_check_protocol_standard.py`：有效/无效 fixture YAML。
10. 更新 `docs/repo_protocol_alignment.md` 中的脚本状态表（缺失 → 已实现）。

### 产出文件

`scripts/check_protocol_standard.py`、`tests/test_check_protocol_standard.py`、更新后的 `docs/agent_gate_and_protocol_check.md` 与 `docs/repo_protocol_alignment.md`、协议检查报告。

### 验收标准

1. 协议文件完整时 checker exit 0；故意删除必填键时 exit 1 或 2（文档约定一致）。
2. 报告列出 pass/warn/fail 项 ID，与 agent_gate 检查项命名可对齐。
3. 不修改协议 YAML 内容，只读校验。
4. alignment 文档中记录的 override 与 checker 警告一致。
5. pytest 通过；与 agent_gate 串联运行无冲突。
6. 脚本运行时间 < 5 秒（纯本地解析）。
7. 不依赖 LLM 或网络。

### 工具要求

- PyYAML 或仓库已有 YAML 解析方式；pytest。
- 推荐流程：`python3 scripts/agent_gate.py && python3 scripts/check_protocol_standard.py`。

### MCP / Playwright 要求

- 不使用。

### 安全要求

- 不将 `project.yaml` 中的 secrets 字段（若有）写入报告正文。
- checker 不得自动修复协议文件；修复须单独 commit 且用户授权。

### 不做事项

不实现 `check_repo_contract.py` 全量合约（可留后续）；不启动翻译；不安装 Node/Playwright。

### 下一轮衔接

进入 Round 43，对工具链环境做 inventory 审计，补齐 agent_gate 尚未覆盖的依赖与脚本清单。

---

## Round 43：Tooling Environment Audit

### 轮次类型

tooling

### 背景

Round 41–42 建立门控与协议检查，但 Python/Node 版本、pytest 可用性、前端目录状态、Prompt 模板数量、脚本清单仍分散。Agent 在 Round 44 安装 Playwright 前需要一份可再生的环境快照，避免「本机可跑、他处失败」。

### 目标

实现仓库 inventory 扫描与环境审计报告，形成工具链就绪度基线。

### 具体任务

1. 创建 `scripts/scan_repo_inventory.py`，生成 `governance/repo_inventory.generated.json`（可 gitignore 或提交摘要版）。
2. 扫描 `scripts/`、`tests/`、`prompts/`、`frontend/`、`governance/` 文件清单与大小摘要（不含正文内容）。
3. 检测 Python、Node、npm、pytest、git 是否可用及版本号（subprocess，不安装新依赖）。
4. 统计工具链 Prompt 模板数量（`prompts/` 下 round/tooling 相关）是否 ≥ 规划值。
5. 检查 `directions/jp_to_cn`、`directions/cn_to_jp`、`shared/` 文档与目录是否存在。
6. 检查 Playwright、MCP 是否已安装（仅报告，不强制安装）。
7. 输出人类可读 `docs/reports/tooling_environment_audit.md`：就绪项、缺失项、Round 44+ 阻塞项。
8. 将 inventory 关键字段（脚本数、测试数、frontend 是否存在）供 agent_gate 可选 WARNING 引用。
9. 添加轻量测试：inventory 脚本可运行且 JSON schema 稳定。
10. 更新 `docs/agent_tooling_strategy.md` 验证命令一节，引用 audit 脚本。

### 产出文件

`scripts/scan_repo_inventory.py`、`governance/repo_inventory.generated.json`（或 `.example.json`）、`docs/reports/tooling_environment_audit.md`、测试与文档更新。

### 验收标准

1. audit 脚本在无 Playwright 环境下仍可 exit 0 并标明 Playwright 未安装。
2. inventory JSON 包含 scripts、tests、prompts、frontend、docs 计数与 timestamp。
3. 报告明确 Round 44 前置条件（Node 或 Python 路线二选一）。
4. 不读取 `input_*`、`output_*` 内文件内容，仅统计路径与 ignore 状态。
5. agent_gate + protocol checker + inventory 三者可在一分钟内顺序跑完。
6. 发现 `.env` 被跟踪时在 audit 报告中 HIGH 标记（与 gate 一致）。
7. 更新 round_state 记录 audit 完成时间与 blockers 变化。

### 工具要求

- Python 3、git；可选 node/npm 检测。
- 审计轮不得 `pip install` 大型包，除非修复 audit 脚本本身所需最小依赖。

### MCP / Playwright 要求

- 仅检测是否安装，不配置 MCP。
- 文档中记录 Cursor / Claude Desktop MCP 配置入口指向 `docs/mcp_playwright_setup_plan.md`。

### 安全要求

- inventory 不哈希或上传文件内容；不列出 `.env` 键值。
- generated JSON 默认不提交含绝对路径的用户 home 信息（可脱敏）。

### 不做事项

不安装 Playwright；不创建向量库；不调用 API；不修改 frontend 业务代码。

### 下一轮衔接

进入 Round 44，在 audit 确认 Node/Python 路线后安装 Playwright 并搭建 smoke test 骨架。

---

## Round 44：Playwright Smoke Test Setup

### 轮次类型

frontend / tooling

### 背景

Round 36–40 应已交付可本地打开的前端 Workbench（静态或 Vite）。Agent 不能只看代码判断 UI；`docs/mcp_playwright_setup_plan.md` 约定 Round 44 为 Playwright 安装与 smoke test 搭建轮。Round 43 audit 应已确认 frontend 目录与启动方式。

### 目标

安装 Playwright（Node 或 Python 单一路线），建立 smoke test 目录与至少一条可运行的端到端冒烟用例，验证首页与核心路由可加载。

### 具体任务

1. 根据 `frontend/` 技术栈选择 Node 或 Python Playwright 路线（文档记录选择理由，避免双栈并存）。
2. 安装 Playwright 与 Chromium；将浏览器下载与 `artifacts/` 纳入 `.gitignore`。
3. 创建 `tests/ui/smoke.spec.ts`（或 `.py`）：启动 dev server 或使用 `webServer` 配置自动起服。
4. 用例覆盖：首页可打开、项目列表或 dashboard 可见、无 console error 级别 `error`（可配置允许列表）。
5. 用例覆盖：术语页、角色页、对照审核页路由可导航（mock 或 fixture 数据）。
6. 配置 `playwright.config`：headless、screenshot on failure、trace on retry、输出至 `artifacts/playwright/`。
7. 在 README 或 `docs/mcp_playwright_setup_plan.md` 补充本地运行命令：`npx playwright test` 或等价命令。
8. 添加 CI 可选 job 说明（不要求本轮必接 GitHub Actions，但文档预留）。
9. 运行 smoke 并保存失败截图至 artifacts（不提交 Git）。
10. 更新 agent_gate 或 audit：可选 WARNING「smoke test 未运行」仅在 strict 前端轮启用。

### 产出文件

Playwright 配置、`tests/ui/smoke.spec.ts`（或 Python 等价物）、`package.json` 或 `requirements-dev` 更新、`docs/mcp_playwright_setup_plan.md` 更新、smoke 运行说明、本地 artifacts（不提交 Git）。

### 验收标准

1. 本地执行 smoke 至少 1 个 spec 通过（基于 mock/fixture，不依赖真实 API）。
2. 前端未启动时测试失败信息清晰，而非挂起超时。
3. `artifacts/` 已在 `.gitignore`。
4. smoke 不读取真实版权长篇；使用 `data/examples/` 或 frontend mock。
5. 失败时自动生成 screenshot/trace 路径写入控制台。
6. 文档说明 Node vs Python 选型与安装命令。
7. agent_gate 仍 exit 0（smoke 非 gate 硬阻塞，除非 `--strict-frontend` 约定）。

### 工具要求

- Node 18+ 或 Python 3.10+；npm/pip 安装 Playwright。
- 静态 server 或 Vite dev server；参见 `docs/frontend_workbench_plan.md` 页面清单。

### MCP / Playwright 要求

- 本轮以 **Playwright CLI** 为主，不要求 MCP 已配置。
- 文档记录 Round 45 将验证 MCP；CLI 为 MCP 失败时的 fallback。

### 安全要求

- smoke 测试 URL 限定 localhost；不访问外网翻译 API。
- 截图/trace 不得包含 API Key 或真实用户正文（使用 fixture）。

### 不做事项

不实现完整 UI 回归套件；不配置生产 MCP；不调用 Lark/OpenRouter 等远程服务；不修改 Round 36–40 已验收的业务逻辑除非修复阻塞 smoke 的 bug。

### 下一轮衔接

进入 Round 45，在 Cursor 等 Agent 环境中验证 Playwright MCP（或 browser MCP）与 CLI fallback 矩阵。

---

## Round 45：Playwright MCP Integration Plan / Validation

### 轮次类型

tooling

### 背景

Playwright CLI 适合 CI 与确定性回归；Agent 在 IDE 内需要 snapshot、click、screenshot 能力以完成 Round 46 的视觉验证。`docs/mcp_playwright_setup_plan.md` 列出 Option A–D；环境差异大，须在本轮做**验证**而非假设全部可用。

### 目标

完成 MCP 接入方案验证：记录当前 Agent 环境可用的 MCP 路线，执行最小 tool call，并与 Playwright CLI smoke 结果对照；更新 fallback 矩阵。

### 具体任务

1. 检测 Cursor / Claude Desktop / 本地 Agent 的 MCP 配置能力，选定 Option A–C 之一并文档化。
2. 执行最小验证：browser snapshot 首页、点击一个导航链接、截图保存至 `artifacts/mcp/`。
3. 对照 Round 44 smoke spec：MCP 所见 DOM 与 CLI 断言一致（项目列表、术语入口等）。
4. 验证 MCP 无法读取 `.env`：尝试访问应被拒绝或不在 tool 允许路径内。
5. 更新 `docs/mcp_playwright_setup_plan.md` 验证清单（Round 45 节）全部勾选或标记 N/A 及原因。
6. 编写 Agent 操作备忘：lock/navigate/snapshot 顺序（对齐 Cursor browser MCP 最佳实践）。
7. 若 MCP 不可用：明确 fallback 为 `npx playwright test tests/ui/smoke.spec.ts`，且不阻塞 Round 46（降级为 CLI + 人工截图）。
8. 在 `docs/agent_tooling_strategy.md` MCP 表更新「已验证 / 未验证 / fallback」状态。
9. 输出 `docs/reports/mcp_playwright_validation_report.md`（本地）。
10. 更新 round_state soft blockers（MCP 是否仍阻塞 Round 46）。

### 产出文件

更新后的 `docs/mcp_playwright_setup_plan.md`、`docs/agent_tooling_strategy.md`、MCP 验证报告、可选 Cursor MCP 配置示例（不含 secrets）。

### 验收标准

1. 验证报告包含：环境名称、MCP 类型、成功/失败步骤、fallback 命令。
2. 至少一种路径（MCP 或 CLI）可完成首页 snapshot + 导航。
3. MCP 安全规则 7 条在报告中逐条确认（见 mcp_playwright_setup_plan）。
4. artifacts 不提交 Git。
5. 不因 MCP 失败而修改 frontend 功能范围。
6. agent_gate + protocol checker 仍通过。
7. 文档明确 Round 46 最低要求：CLI smoke 必须通过；MCP 为增强。

### 工具要求

- Round 44 已安装的 Playwright；Cursor browser MCP 或等价物（若可用）。
- git、agent_gate、protocol checker。

### MCP / Playwright 要求

- **本轮核心**：MCP tool call 验证 + CLI 对照。
- 必须测试 snapshot、click（或 navigate）、screenshot 至少各一次。
- MCP 失败时记录 fallback，不得无限重试同一失败 action。

### 安全要求

- MCP 不得输出 API Key；不得读取 `.env` 后展示。
- 不得通过 MCP 自动 push、公开发布译文或删除 input 原文。
- 截图仅存 artifacts，不写入 prompts 或 commit。

### 不做事项

不实现自定义项目 MCP server；不扩展 smoke 覆盖全部 17 个前端页面；不调用真实翻译 API。

### 下一轮衔接

进入 Round 46，基于已验证的 MCP 或 CLI，对 Review Workbench 核心页面做系统化视觉与交互验证。

---

## Round 46：Frontend Review Workbench Visual Verification

### 轮次类型

frontend

### 背景

Round 37–40 实现的前端需经浏览器验证而非代码审查 alone。`docs/agent_tooling_strategy.md` 规定 Round 46 起必须检查页面启动、数据加载、术语/角色/对照/diff 页、控制台错误与关键按钮。本 round 是前端治理的「可见性验收」。

### 目标

对 Review Workbench 核心页面执行自动化视觉与交互验证，产出 issue 列表与截图证据，确认与 `docs/frontend_workbench_plan.md` 一致。

### 具体任务

1. 启动 frontend dev server，确认 Project Home、Chapter Manager 可加载 fixture 项目数据。
2. 验证 Glossary Editor：术语列表渲染、锁定态显示、编辑保存（fixture 项目，非生产数据）。
3. 验证 Character Profile Editor 与 World Bible Editor 只读/编辑边界符合 Round 39 设计。
4. 验证 Side-by-side Translation Review：左右对照、segment 定位、issue 标记入口存在。
5. 验证 Refinement Comparison：diff 视图可打开，无阻塞性 JS 错误。
6. 验证 Issue Review Dashboard 与 Export Center 路由可达，版权/确认文案存在。
7. 收集 browser console：无未解释的 `error`；network 无意外外域 API（除 localhost）。
8. 使用 Playwright 扩展 smoke 或 MCP 手动脚本覆盖上述页面；失败项写入 `docs/reports/frontend_visual_verification_report.md`。
9. 对每个失败项标注：阻塞 / 非阻塞、建议修复轮次。
10. 更新 frontend README：本地启动、验证命令、fixture 数据路径。

### 产出文件

扩展的 UI 测试（可选 `tests/ui/workbench.spec.ts`）、视觉验证报告、截图（artifacts）、frontend 文档更新。

### 验收标准

1. Project Home、Glossary、Character、Side-by-side Review、Refinement Comparison 五类页面验证通过或 issue 已登记。
2. 控制台无未处理严重错误（已知 mock 警告可列入 allowlist）。
3. 页面加载的数据来自 fixture 或 `data/examples/`，非真实版权长篇。
4. Playwright smoke + workbench spec 本地可重复运行。
5. 验证报告与 frontend_workbench_plan 页面清单一一对应。
6. 锁定术语编辑保护在 UI 层有可见反馈（拒绝或提示）。
7. agent_gate exit 0；protocol checker exit 0。

### 工具要求

- Playwright CLI（必须）；MCP browser（推荐）。
- frontend dev server、fixture 数据、pytest（若后端 API 轻量联调）。

### MCP / Playwright 要求

- 必须打开真实浏览器上下文验证；禁止仅 grep 源码代替。
- 推荐流程：navigate → lock → snapshot → 关键 click → screenshot → unlock。
- 四类页面（术语、角色、对照、diff）必须各有至少一张截图或 snapshot 记录。

### 安全要求

- 验证不使用真实 API Key；provider 设置页仅检查 UI，不填入 secrets。
- 截图不含用户 home 路径敏感信息；不提交 artifacts。
- 不将 fixture 误当作可公开发布内容。

### 不做事项

不重构前端架构；不接入生产后端；不执行真实批量翻译；不跳过 Issue 直接标记「全部通过」。

### 下一轮衔接

进入 Round 47，在 UI 可验证基础上 hardened API dry-run 与 cost guard，为受控真实调用做准备。

---

## Round 47：API Dry-run and Cost Guard Hardening

### 轮次类型

api_integration

### 背景

Round 34 已规划成本记录与预算保护；Round 40 短篇闭环可能使用 fake provider。进入工具链后期需确保 **dry-run 默认、真实调用双开关、超限硬停止** 在 CLI 与 provider adapter 层一致。`docs/api_provider_strategy.md` 要求 `REAL_API_TESTS_ENABLED`、`MAX_TEST_COST_USD` 等 guard。

### 目标

强化 fake/dry-run provider、预算守卫与 model run metadata，使任何真实 API 调用必须显式授权且可审计。

### 具体任务

1. 审计现有 provider adapter：默认路径是否为 fake/dry-run；列出所有可能触发真实 HTTP 的入口。
2. 实现或加固环境开关：`REAL_API_TESTS_ENABLED`、`MAX_TEST_COST_USD`、`MAX_TOKENS_PER_RUN`（名称与文档统一）。
3. 确保 CLI（`translate-one`、`translate-batch` 等）在未授权时只输出 dry-run 摘要，不发起网络请求。
4. 统一 model run metadata 写入：provider、model、stage、estimated/actual tokens、status、error_type（不含 Key 与长正文）。
5. 超限场景测试：预算用尽时 exit 非零并写 cost report，不 silent fail。
6. 更新 `.env.example`：只列变量名与说明，无示例 Key。
7. 添加 `tests/test_cost_guard.py`、`tests/test_dry_run_provider.py` 覆盖开关组合。
8. 文档更新 `docs/api_provider_strategy.md` 与 operating manual 中的 API 轮 checklist。
9. agent_gate 可选检查：`.env.example` 存在且无 `=` 后真实 Key 模式。
10. 输出 `docs/reports/api_dry_run_hardening_report.md` 列举入口矩阵（CLI/脚本/frontend）。

### 产出文件

加固后的 provider/cost guard 代码、测试、`.env.example` 更新、API 硬化报告、文档更新。

### 验收标准

1. 默认配置下运行 translate 相关 CLI 无 outbound HTTP（可用 mock socket 或 provider 计数断言）。
2. `REAL_API_TESTS_ENABLED=1` 且无 Key 时失败明确，不泄露环境变量值。
3. 超 `MAX_TEST_COST_USD` 时停止后续调用并生成 cost report。
4. model run log 不含完整 Key 与超长原文。
5. pytest 覆盖 dry-run/on/budget-exceeded 至少各一例。
6. agent_gate 与 protocol checker 通过。
7. 前端 Provider Settings 仍不存储 Key 明文。

### 工具要求

- pytest、fake provider、可选 httpx mock。
- agent_gate、protocol checker；**禁止**本轮默认 openrouter/deepseek 真实调用。

### MCP / Playwright 要求

- 不使用；若验证 Provider Settings UI，仅用 Playwright 确认「无 Key 输入持久化」字段行为。

### 安全要求

- 日志、报告、test fixture 均不得含真实 API Key。
- 真实 API 试调用仅能在 Round 50 且用户明确授权后进行。
- 错误信息不打印 Authorization header。

### 不做事项

不进行大规模真实翻译；不升级 provider 列表到生产 SLA；不修改协议 YAML 本体。

### 下一轮衔接

进入 Round 48，在 API 受控前提下建设向量库**检查**工具（非无脑 embedding 全书）。

---

## Round 48：Vector DB Inspection Tools

### 轮次类型

tooling / data

### 背景

shared core 设计含 embedding adapter 与 vector store；Round 40 可能已用 fixture 生成小规模索引。Agent 需要 inspect 工具确认 metadata、维度、条目数与过滤条件，而非直接 embedding 全部章节。`docs/agent_tooling_strategy.md` 规定向量库早期以设计与检查为主。

### 目标

提供向量索引与 embedding metadata 的检查 CLI/脚本，支持 JSON 报告与抽样验证，不强制新建生产级向量库。

### 具体任务

1. 创建 `scripts/inspect_vector_store.py`（或等价模块）：支持 Chroma/FAISS/本地 JSON index 至少一种后端（与项目当前实现一致）。
2. 输出：条目数、collection 名、embedding 维度、metadata 键集合、缺失字段统计。
3. 支持按 `project_id`、`chapter_id`、`language_direction` 过滤统计（与 schema 对齐）。
4. 支持抽样 N 条记录打印**脱敏**摘要（id、长度、hash 前缀，不打印全文）。
5. 检测 orphan 索引（manifest 无对应 source）与 duplicate id。
6. 若 Round 40 无真实索引，用 `data/examples/` 生成最小 fixture index 供测试。
7. 添加 `tests/test_inspect_vector_store.py` 基于 temp 目录 fixture。
8. 文档：何时允许生成 embedding、成本控制与过滤条件（写入 `docs/agent_tooling_strategy.md` Data/Vector 节）。
9. agent_gate 不强制向量库存在；存在时 WARNING 检查 metadata schema 漂移。
10. 输出 `docs/reports/vector_store_inspection_report.md`（基于 example 项目）。

### 产出文件

`scripts/inspect_vector_store.py`、测试、example index fixture、检查报告、文档更新。

### 验收标准

1. 对空/缺失索引给出明确 exit 1 与说明，不 crash。
2. 对 fixture index 输出正确计数与 metadata 摘要。
3. 脚本不触发新 embedding API 调用（除非 `--regenerate-fixture` 显式文档化且默认 off）。
4. 脱敏输出不含完整章节正文。
5. pytest 通过。
6. 与 shared_core_design 中 vector store adapter 字段一致。
7. agent_gate exit 0。

### 工具要求

- Python；项目已选 vector backend 库；pytest。
- 可选：JSON/YAML validator。

### MCP / Playwright 要求

- 不使用。

### 安全要求

- 检查工具只读；不提供 `--delete-all` 无确认标志。
- 不将向量条目全文写入报告；不提交 example index 若含真实正文。

### 不做事项

不对真实长篇全书做 embedding；不选型替换 vector backend；不启动 Milvus/Pinecone 等外部服务。

### 下一轮衔接

进入 Round 49，将质量审核 workflow 与 Workbench UI 结合，形成可复查的 auto-review 工作台能力。

---

## Round 49：Translation Quality Auto-review Workbench

### 轮次类型

review / frontend

### 背景

`docs/quality_review_workflow.md` 定义 24 类 issue 与 schema；Round 38–39 前端已能展示 issue 与对照。项目价值在于一致性与可复查性，需在 Workbench 中集成**机器审核输出 + 人工确认**流程，而非自动覆盖译文。

### 目标

实现或接通质量 auto-review 工作台：从 pipeline 生成 ReviewIssue，在前端集中展示、筛选、标记状态，并与术语/角色/世界观锁定规则联动。

### 具体任务

1. 实现或完善 review stage：对 fixture 译文运行术语/角色/段落对齐/日文残留等规则子集（可先 deterministic + fake review provider）。
2. 输出符合 quality_review_workflow schema 的 `ReviewIssue` JSON 至项目 workspace。
3. Frontend Issue Review Dashboard：按 severity、issue_type、chapter 筛选；支持 status 流转（open → resolved）。
4. Side-by-side Review 页高亮 issue 对应 segment；点击 issue 跳转对照位置。
5. 锁定术语/角色冲突类 issue 禁止一键自动改译文，仅 suggested_fix 展示。
6. CLI `review` 子命令与 Workbench 读取同一 issue 文件，避免双源。
7. 添加测试：issue 生成、schema 校验、frontend 数据绑定（组件或 e2e 轻量）。
8. 文档更新 quality_review_workflow：哪些维度本轮 machine、哪些留 Round 50+。
9. Playwright spec：打开 Dashboard，可见至少 3 类 issue 类型（fixture）。
10. 输出 `docs/reports/quality_workbench_integration_report.md`。

### 产出文件

review 规则/adapter 代码、issue JSON fixture、Dashboard 与对照联动、测试、Playwright spec 扩展、集成报告。

### 验收标准

1. fixture 项目运行 review 后生成 ≥5 条可定位 issue（含 chapter_id + segment_id）。
2. Workbench 可列表、筛选、更新 issue status 并写回本地 JSON。
3. 不自动覆盖 TranslationDraft/RefinedTranslation 正文。
4. locked term 相关 issue 无「自动应用修复」按钮或等价保护。
5. schema 校验失败时 CLI exit 非零。
6. Playwright 验证 Dashboard 与 Side-by-side 联动基本路径。
7. agent_gate、cost guard 测试仍通过；review 默认 dry-run/fake。

### 工具要求

- Python review 模块、pytest、frontend dev server、Playwright。
- JSON schema 校验（若项目已引入）。

### MCP / Playwright 要求

- Dashboard 与 Side-by-side 须浏览器验证；推荐扩展 `tests/ui/workbench.spec.ts`。
- MCP 可用于快速复现 issue 跳转路径（可选）。

### 安全要求

- issue 中的 source_text/target_text 使用 fixture 或用户授权样例；报告不提交真实长篇。
- review provider 若接真实 API，须 Round 47 cost guard 双开关，默认 off。

### 不做事项

不宣称「全自动质量合格」；不批量关闭 issue 无人工确认；不实现版权/公开发布 checker 全量。

### 下一轮衔接

进入 Round 50，在 gate、UI、review、cost guard 就绪后做 Agent 辅助的受控翻译试跑。

---

## Round 50：End-to-end Agent-assisted Controlled Translation Trial

### 轮次类型

e2e validation

### 背景

Round 40 已完成短篇闭环；Round 41–49 补齐工具链、浏览器验证、API 守卫、向量检查与质量工作台。Round 50 是在**用户明确授权**下，由 Agent 按 operating manual 编排一次受控试跑：范围限定、checkpoint、成本上限、人工审核点，验证全栈可协作而非生产批量。

### 目标

完成一次 Agent 辅助的受控翻译试跑（建议：单项目、1–3 章 fixture 或用户指定授权样章），贯穿 scan → context → translate → review → refine → export → Workbench 复查，并产出可审计报告。

### 具体任务

1. 试跑前：`agent_gate`、`check_protocol_standard`、Playwright smoke 全部 PASS；用户确认范围、预算、provider。
2. 设定 checkpoint：每阶段（extract、translate、review、refine）后写 `ProjectState` 与 cost 摘要，失败可 resume。
3. 使用 `REAL_API_TESTS_ENABLED=1` 与 `MAX_TEST_COST_USD` 执行有限章节真实调用（或用户指定继续 fake 则文档说明）。
4. Agent 按 prompt 模板执行：不跳 gate、不跳过 review issue 人工确认节点。
5. 生成 embedding/向量（若在本范围）仅针对试跑章节，并用 Round 48 inspect 工具验收 metadata。
6. 在 Workbench 完成对照审核与 issue 处理演示；Export Center 导出双语/报告（本地 workspace）。
7. 运行 quality auto-review，对比 Round 49 baseline，记录新增 issue 类型与误报。
8. 收集全链路 artifacts：gate 报告、cost report、Playwright 截图、vector inspect、试跑时间线。
9. 编写 `docs/reports/round_50_controlled_trial_report.md`：范围、成本、问题、是否建议进入长篇试跑。
10. 更新 `governance/round_state.yaml`：`real_api_called`、`full_translation_executed` 等字段如实记录；提出 Round 51+ 路线建议（性能、多项目、服务端化）。

### 产出文件

试跑项目 workspace 输出（gitignore 内）、controlled trial 报告、cost/issue/export 产物、更新的 round_state、可选 PR 说明（需用户授权 commit/push）。

### 验收标准

1. 端到端阶段均有 checkpoint 记录，中断后可从最近 checkpoint 说明恢复步骤。
2. 实际 API 花费 ≤ 用户批准的 `MAX_TEST_COST_USD`；超限时试跑已停止。
3. 无 `.env`/Key/未授权原文泄露到 Git 或报告。
4. Workbench 可查看试跑项目核心页面；Playwright smoke 仍 pass。
5. ReviewIssue 可追溯；最终 export 与 issue 状态一致。
6. trial 报告含 go/no-go 建议与阻塞项清单。
7. agent_gate strict 模式通过或 WARN 项已在报告中解释。

### 工具要求

- 全工具链：agent_gate、protocol checker、inventory audit、Playwright、CLI pipeline、cost guard、vector inspect、review workbench。
- git status 开始与结束；commit/push 仅用户明确要求。

### MCP / Playwright 要求

- 试跑过程中至少一次 MCP 或 CLI 浏览器复查对照页与 Dashboard。
- 失败时保留 trace；不删除 input 原文。

### 安全要求

- 试跑范围必须在 operating manual 允许动作内； copyrighted 长篇默认禁止除非用户书面授权。
- 所有真实 API 调用记录 model run metadata；报告脱敏。
- Agent 不得自动 push、公开发布或覆盖 locked 术语/已完成 human_reviewed 段落。

### 不做事项

不进入生产级全书批量；不默认开启无预算 API；不跳过人工审核直接标记 final；不删除 Round 40/49 已有 fixture 除非迁移文档化。

### 下一轮衔接

根据 trial 报告分支：长篇受控试跑、并发与性能优化、多项目管理、后端 API 服务化、或 CI 集成 Playwright/agent_gate——写入后续路线图（Round 51+）或用户决策 backlog。

---

## 附录：Round 41–50 与前置轮关系

| Round | 依赖前置 | 核心产出 |
|-------|----------|----------|
| 41 | Round 02 gate 文档 | `scripts/agent_gate.py` |
| 42 | 41 | `scripts/check_protocol_standard.py` |
| 43 | 41–42 | `scripts/scan_repo_inventory.py` |
| 44 | 36–40 frontend、43 audit | Playwright smoke |
| 45 | 44 | MCP 验证报告 |
| 46 | 37–40、44–45 | 前端视觉验证报告 |
| 47 | 34、40 | cost guard 硬化 |
| 48 | 02 vector 设计、40 可选索引 | vector inspect 工具 |
| 49 | quality_review、38–39 UI | auto-review Workbench |
| 50 | 41–49、40 | 受控试跑报告 |

**必读交叉引用：**

- 工具分层与决策树：[`docs/agent_tooling_strategy.md`](agent_tooling_strategy.md)
- Playwright/MCP 安装与 fallback：[`docs/mcp_playwright_setup_plan.md`](mcp_playwright_setup_plan.md)
- Gate 与协议检查流程：[`docs/agent_gate_and_protocol_check.md`](agent_gate_and_protocol_check.md)
- 前端页面与数据流：[`docs/frontend_workbench_plan.md`](frontend_workbench_plan.md)
- 前端实现轮次：[`docs/roadmap_rounds_00_40.md`](roadmap_rounds_00_40.md) Round 36–40
- API 与 cost：[`docs/api_provider_strategy.md`](api_provider_strategy.md)
- 质量审核：[`docs/quality_review_workflow.md`](quality_review_workflow.md)
