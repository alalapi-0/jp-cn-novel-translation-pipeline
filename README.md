# 中日文小说互译生产流水线

本仓库用于规划和逐步建设一个面向长篇小说与轻小说的中日文互译生产流水线。它不再只是一次性的“日文小说翻译成中文”任务目录，而是面向长期项目管理、双向翻译、术语一致性、角色语气控制、世界观设定管理、检索增强、批量初翻、二次润色和人工审核工作台的治理仓库。

当前仓库处于最终成品路线的 **Phase A 全书初翻阶段**。截至 2026-06-11 的治理复核，连续完成 355/613 章，下一安全 micro round 为 `D-MR-052`（356–358 章）；S1 本地调度器与 S3 配置/术语资产内核已完成。它仍不是公开 SaaS 或自动发布工具。

最终目标与当前唯一主路线：

- `docs/product_final_state_spec.md`
- `docs/final_state_implementation_roadmap.md`
- `docs/final_state_round_task_list.md`
- `docs/next_agent_execution_protocol.md`

## 快速开始（本地工作台）

全新 clone 后按以下步骤启动静态审核工作台并跑 smoke：

```bash
# 1. Node 依赖（Playwright UI 测试 + MCP 检查）
npm ci

# 2. Python 虚拟环境与单元测试（避免 PEP 668 系统 Python 限制）
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pytest tests/ -q
# 或：npm run test:py

# 3. 启动前端 + Workbench API（默认端口 5174）
npm run dev:frontend
# 浏览器打开 http://127.0.0.1:5174/
```

**真实 API 小规模测试**（在已激活的 venv 中；可从 repo 根目录 `.env` 读取未设置的 Key，不打印 Key 值）：

```bash
# 方式 A：repo/.env 中配置 OPENROUTER_API_KEY、REAL_API_TESTS_ENABLED=true、MAX_TEST_COST_USD>0（如 0.01）
.venv/bin/python3 scripts/run_real_api_smoke.py --real --json

# 方式 B：显式 export
export OPENROUTER_API_KEY=your_key_here
export REAL_API_TESTS_ENABLED=true
.venv/bin/python3 scripts/run_real_api_smoke.py --real
# 无 Key 时：.venv/bin/python3 scripts/run_real_api_smoke.py --status-only
```

`npm run dev:frontend` 启动时也会加载 `.env` 中**未设置**的变量，首页 API 状态卡片会区分 **Key 是否已配置** 与 **Workbench 页面真实 API 是否可调用**（后者还需 `MAX_TEST_COST_USD>0`）。

**Model Router（统一 LLM 入口）：**

所有真实模型调用应通过 `model-router` 层，业务代码不直接依赖具体供应商 SDK。详见 [`model-router/README.md`](model-router/README.md)。

```python
import sys
from pathlib import Path
sys.path.insert(0, str(Path("model-router/src").resolve()))
from model_router import chat, ChatOptions

result = chat(
    [{"role": "user", "content": "Reply exactly: smoke_ok"}],
    ChatOptions(profile="fast", max_tokens=32),
)
# result.content / result.provider / result.model / result.usage
```

配置：`model-router/config/models.yaml` + `.env` 中的 `MODEL_ROUTER_DEFAULT_PROFILE` 与各 `*_API_KEY`。Pipeline 的 `get_provider(ProviderMode.REAL)` 已桥接到 Router。

**工具链门控与 UI 测试：**

```bash
npm run test:py        # 推荐：自动使用 .venv/bin/python -m pytest
npm run test:ui        # Playwright（自动起 5174 dev server）
npm run check:tooling  # 内含 pytest + MCP 检查
```

勿直接 `python3 -m pytest`（系统 Python 可能缺依赖）；若无 `.venv`，`npm run test:py` 会提示创建虚拟环境。

审核工作台默认 **不自动通过** segment（`AUTO_APPROVE=false`）；自动推进试验可在 URL 加 `?auto_approve=1`。

**翻译记忆/资产沉淀：**

重启或重试翻译任务前，可把 Workbench 已审核通过内容沉淀为本地资产。默认 `agent` 模式不调用外部 API：

```bash
python3 scripts/build_translation_assets.py --project-id demo-jp-cn
python3 scripts/translate.py --phase draft --stage stage_a --limit-chapters 1 \
  --asset-context workspace/assets/translation_memory/demo-jp-cn.json
```

导出中心也提供“翻译记忆资产”入口。详见 [`docs/translation_memory_assets.md`](docs/translation_memory_assets.md)。

## 当前阶段

当前主线为 Phase A 初翻批量推进，同时允许按总路线与 S2 交错完成工程轮。真实 API 是生产能力的一部分，只能由允许真实 API 的轮次在 pause/lock/orphan/cost guard 全部通过后使用。治理轮默认不启动真实翻译。

## 当前 Workbench 功能状态（现有能力 vs 最终路线）

| 能力 | 当前可用 | 最终路线待实现 |
|---|---|---|
| Quickstart 生成 | 支持 dry-run 与真实 API 小样本；带请求幂等与生成任务状态查询 | Dashboard、项目/API 设置、Pipeline 控制台与调度器 UI |
| 审核状态 | `review_state` 持久化（approved/rejected/pending） | 更完整的人审流转（指派、批注、审计轨迹） |
| 导出 | 支持 `approved`（默认）/`draft` 模式，导出前合并审核状态 | 多格式导出、发布前质量门禁与签出流程 |
| 质量 Issue | 支持 quality-review API + fixture fallback，页面显示数据源 | 多轮对比、自动修复建议回写和闭环追踪 |
| 真实 API 错误处理 | 返回脱敏错误码与可行动提示（鉴权/额度/限流/超时/网络/参数） | 细粒度 provider 诊断面板与错误统计看板 |
| 测试体系 | Python 单测 + Playwright UI smoke；重点场景已做隔离 | 全链路稳定回归、并行/分片执行与 flaky 追踪 |

## 支持方向

- `JP_TO_CN`：日文小说到中文小说翻译。
- `CN_TO_JP`：中文小说到日文小说翻译。

两个方向共享文件扫描、章节解析、术语库、角色设定、世界观设定、翻译记忆、embedding、向量库、模型 provider 抽象和审核框架；方向专属规则放在 `directions/jp_to_cn/` 与 `directions/cn_to_jp/`。

## 当前已完成内容

- 已存在早期日译中项目结构：`input_jp/`、`output_cn/`、`notes/`、`docs/`、`prompts/`。
- 已存在术语、人物、风格、翻译规则和进度类 notes。
- 已存在早期翻译流水线、术语系统和 embedding memory 相关文档。
- 本轮治理将保留旧结构，并在其上补齐双向流水线规划。

## 最终路线

项目按 FS Round 推进，核心路线见 `docs/final_state_implementation_roadmap.md` 与 `docs/final_state_round_task_list.md`：

1. 本地调度器与 Phase A 全书初翻。
2. 配置/术语资产与 Web UI 基座、MVP。
3. Phase B 一致性检查与 Phase C baseline lock。
4. Phase D 全书润色与 Phase E 终检。
5. production_candidate、用户修改稿同步、完整导出。
6. 15 页最终 Web UI、Playwright 用户旅程与项目级 DoD 验收。

## 目录说明

- `input_jp/`：日文原文输入目录。真实版权文本默认不提交。
- `output_cn/`：中文译文输出目录，包含 translated、bilingual、review 等子目录。真实译文默认不提交。
- `input_cn/`：中文原文输入目录。真实版权文本默认不提交。
- `output_jp/`：日文译文输出目录，包含 translated、bilingual、review 等子目录。
- `notes/`：早期项目级术语、人名、风格、规则、进度记录。
- `docs/`：架构、治理、路线图、数据 schema、流程设计文档。
- `prompts/`：后续治理轮、实现轮、翻译执行轮、审核轮、前端轮、API 接入轮 Prompt。
- `shared/`：未来共享核心能力说明与实现位置。
- `directions/`：不同语言方向的规则和 Prompt。
- `workspace/`：中间数据、解析结果、context pack、model run、embedding 和向量索引的本地工作区。
- `data/`：项目级结构化数据、schema 和样例。
- `src/`：翻译、调度、质量检查、Workbench 后端与资产模块。
- `frontend/`：当前 4 页 Workbench；最终路线将扩展到规格定义的 15 页。
- `scripts/`：已有脚本与后续轻量工具脚本。
- `tests/`：未来测试用例。

## 如何放入日文原文

将日文原文放入 `input_jp/`，并优先使用 `.md` 或 `.txt`。真实原文默认不提交到仓库。后续执行轮应先生成 manifest，再进行章节解析和段落切分；治理轮不得读取或处理正文。

## 如何放入中文原文

将中文原文放入 `input_cn/`，并优先使用 `.md` 或 `.txt`。真实原文默认不提交到仓库。中译日流程必须使用 `CN_TO_JP` 方向规则，不得混用 `JP_TO_CN` Prompt。

## 为什么需要术语库

长篇小说会反复出现人物、地点、组织、技能、制度、称号和口头禅。术语库用于记录 source text、target text、状态、首次出现位置、例句、冲突和锁定规则，保证全书译名一致。

## 为什么需要角色设定

角色设定用于维护姓名、别名、称呼关系、说话风格、第一人称、敬语等级和典型台词。它的目标不是写百科，而是防止初翻和润色阶段把不同角色处理成同一种声音。

## 为什么需要世界观设定

世界观设定用于保存地点、组织、制度、魔法、技能、历史、种族、伏笔等来自原文的证据化信息。它帮助模型理解上下文，但不能替代原文，也不能提前解释伏笔。

## 为什么需要 embedding

Embedding 用于检索相似段落、术语上下文、角色台词、世界观证据、翻译记忆和润色前后对比。向量库是检索辅助，不替代术语库、角色表、世界观设定或人工确认规则。

## 为什么初翻和润色要分开

初翻优先完整、忠实、不漏译、术语和人名一致；润色优先自然、风格统一、保留信息和修正机翻腔。二者分离可以降低成本、减少不可控重写，并保留可复查的 change log。

## 为什么未来需要前端

前端工作台用于让用户创建项目、选择方向、配置模型、查看章节、审核术语、维护角色和世界观、对照原文译文、处理冲突、启动润色和导出结果。前端目标是提升审核效率，不是炫酷展示。

## 安全与版权提醒

- 本项目不是盗版发布工具。
- 不鼓励未经授权公开发布受版权保护的原文或译文。
- 真实原文和真实译文默认不提交。
- `.env`、API Key、账号、用户隐私和敏感请求头不得提交。
- 日志和 metadata 不得输出完整 API Key。

## 后续 Agent 必读文档

每轮 Agent 应先读取：

- `docs/product_final_state_spec.md`
- `docs/next_agent_execution_protocol.md`
- `docs/final_state_implementation_roadmap.md`
- `docs/final_state_round_task_list.md`
- `governance/repo_protocol_standard.yaml`
- `project.yaml`
- `AGENTS.md`
- `README.md`
- `docs/project_vision.md`
- `docs/architecture_overview.md`
- `docs/roadmap_rounds_00_40.md`
- `docs/roadmap_rounds_41_50_tooling_and_workbench.md`
- `docs/governance_rules.md`
- `docs/repo_protocol_alignment.md`
- `docs/agent_operating_manual.md`
- `docs/current_repository_audit.md`

## Agent 工具链与推进方式

本项目是**中日文互译生产流水线**，不是单纯翻译脚本。后续 Agent 按 Round 推进，类型包括治理、实现、翻译执行、审核、前端、API 接入与工具链轮。工作方式见 `docs/agent_operating_manual.md` 与 `docs/agent_tooling_strategy.md`；每轮开始/结束 checklist 与硬软阻塞定义亦在该手册中。

Round 41 起将实现 `scripts/agent_gate.py` 作为统一门控入口。

## 通用协议对齐

仓库采用可移植治理标准 `governance/repo_protocol_standard.yaml`（v0.3.0）。对齐情况、冲突与迁移计划见 `docs/repo_protocol_alignment.md`。项目差异写入 `project.yaml` 与 `governance/novel_pipeline_contract.yaml`，不擅自改写协议正文。

## MCP / Browser Tools Runbook

当前项目的 MCP / 浏览器工具使用规则以以下文件为准：

- `docs/runbooks/mcp_browser_tools_runbook.md`

后续 Agent 在涉及工具、前端、浏览器、MCP、Playwright、Chrome DevTools 时必须先读取该 Runbook。

### 工具隔离原则

1. Playwright 是默认浏览器自动化工具。
2. chrome-devtools 需要项目独立 profile 后再作为补充工具。
3. chrome-devtools profile 冲突时不得阻塞任务，应 fallback 到 Playwright。
4. 端口冲突时自动换端口，不 kill 其他项目进程。
5. 多 Agent 并行时不得共享默认 Chrome profile。

工具状态快照：`docs/tooling_current_status.md`。

## Cursor Browser UI Workflow

Cursor Agent 做 UI 优化、浏览器验收时须使用 **普通前台 Agent**（禁用 Multitask）。详见 `docs/cursor_browser_ui_runbook.md` 与 `docs/runbooks/mcp_browser_tools_runbook.md`。

### 1. 如何检查 MCP

```bash
npm run check:cursor-mcp
# 或
bash scripts/check_cursor_mcp_status.sh
npm run check:mcp
python3 scripts/check_mcp_health.py
npm run check:stitch
```

**注意：** CLI 检查通过 ≠ 当前 Agent 对话已暴露工具；见 `docs/cursor_tool_registry_check.md`。

### 2. 为什么需要重启 Cursor

- 批准 MCP 后，**旧对话线程**可能仍看不到工具
- **Multitask 子 Agent** 可能不继承 Workspace MCP
- **新建普通 Agent 对话**最稳定；必要时 **完全退出 Cursor** 后重开仓库

### 3. UI 优化标准流程

1. 启动项目（`npm run dev:frontend`）
2. 打开页面并截图（before）
3. Stitch 设计或读取 `docs/design/stitch/`
4. 修改代码（每轮一个 UI 切片）
5. 再打开页面并截图（after）
6. console / network 检查
7. 运行测试（`npm run test:ui` 等）
8. commit / push（用户授权后）

Prompt 模板：`docs/prompts/CURSOR_UI_IMPLEMENTATION_PROMPT.md`

### 4. 微信页面特殊说明

本项目为本地 Web Workbench，**通常不涉及**微信公众号页面。若未来有微信任务：

- 已登录页面操作必须使用 **wechat-chrome-session**
- 不允许用 Playwright 新开页面替代
- 遇到扫码 / 风控停止，等待用户手动处理

## Stitch Design MCP

[Google Stitch](https://stitch.withgoogle.com/) 为本项目提供 **UI 设计能力**：生成 Dashboard、审核台、导出页、Debug 面板等原型，供 Cursor 实现时参考。

| 角色 | 职责 |
|------|------|
| **Stitch** | 设计输入：原型、HTML、截图 |
| **Cursor** | 按设计落地 `frontend/` |
| **Codex** | 用户视角测试，只报问题不改代码 |

### 配置

1. 获取 Stitch API Key，**仅**在本机设置：`export STITCH_API_KEY=your_key_here`（见 `.env.example` 占位符，**勿提交 `.env`**）
2. `.cursor/mcp.json` 已包含 `stitch` server（本地 stdio proxy：`scripts/stitch_mcp_proxy.mjs`）
3. **Reload Window** 后在 Cursor Settings → MCP 确认 `stitch` 已启用
4. 检查：`npm run check:stitch`

### 设计文档与产物路径

- 总览：`docs/design/DESIGN.md`
- Stitch 用法：`docs/design/stitch/README.md`
- 任务模板：`docs/design/stitch/UI_TASKS.md`
- Prompt 模板：`docs/design/stitch/PROMPT_TEMPLATES.md`
- 导出：`docs/design/stitch/exports/`、`screenshots/`、`reviews/`

### 工作流摘要

1. 按 `UI_TASKS.md` 选定页面 → 用 Stitch 生成 screen
2. 导出 HTML/截图到 `docs/design/stitch/`
3. Cursor 拆任务实现静态前端（**禁止**无审查覆盖业务代码）
4. `npm run test:ui` 或 Playwright / chrome-devtools MCP 验收

### 安全与常见问题

- **不要**提交 `.env` 或把 Key 写入 `.cursor/mcp.json` / 文档
- Stitch 负责设计，不负责翻译 API 或删除项目文件
- 无 Key 时：用 `PROMPT_TEMPLATES.md` 文字模板继续，并记录 MCP soft blocker
- MCP 未连接：重启 Cursor 并确认 `npm ci` 已安装 `@google/stitch-sdk`

详见 `docs/design/stitch/STITCH_MCP_SETUP.md`、`AGENTS.md`（Stitch Design MCP 章节）。

## Workspace MCP Servers

当前项目需要以下 Workspace MCP Servers：

- `chrome-devtools`
- `context7`
- `filesystem`
- `github`
- `playwright`
- `stitch`

说明：

1. **`.cursor/mcp.json`** 是当前项目的 Workspace MCP 配置。
2. Cursor 可能需要**重启或重新加载窗口**（Reload Window）后才能识别新配置。
3. **GitHub MCP** 需通过环境变量 `GITHUB_TOKEN` 提供 token（映射为 `GITHUB_PERSONAL_ACCESS_TOKEN`），**不允许**写进仓库。
4. **Stitch MCP** 需通过 `STITCH_API_KEY` 环境变量认证，**不允许**写进仓库。
5. **filesystem MCP** 只授权当前项目目录（`${workspaceFolder}`）。
6. 可运行 `npm run check:mcp`、`npm run check:stitch`、`python3 scripts/check_mcp_health.py` 检查配置。

**MCP 浏览器隔离：** chrome-devtools 使用项目 wrapper（`scripts/chrome_devtools_mcp_light_novel.sh`）与独立 profile；冲突时优先 playwright。见 `docs/mcp_isolation_strategy_light_novel.md`。

使用说明见 **`docs/agent_skills/mcp_usage_skill.md`**、**`docs/mcp/README.md`**。MCP 与 Playwright 是**增强工具**；安装时机、验证步骤、fallback 与安全规则见 `docs/mcp_playwright_setup_plan.md`。

## 参考仓库方法吸收

本项目只借鉴 AiNiee、GalTransl、TranslateBooksWithLLMs、epub-translator-oomol、SakuraLLM、LiteraryTranslation、LunaTranslator、BallonsTranslator、epub-translator-slyh 等参考仓库的工程方法，不直接复制参考仓库代码。

参考方法吸收文档见 `docs/reference_repo_methodology_integration.md`、`docs/current_project_method_stack.md` 与 `docs/reference_inspired_pipeline_design.md`。这些文档用于把成熟工程套路转化为当前项目自己的 stable ID、JSONL 中间态、Prompt 契约、Validator、Provider Adapter、Exporter 和 Review Workbench 路线。

## 当前项目采用的核心工程套路

当前项目采用 `parser -> JSONL intermediate -> context pack -> prompt builder -> provider adapter -> response extractor -> validator -> status update -> exporter` 的主链路。共享能力落在 shared core，`JP_TO_CN` 与 `CN_TO_JP` 方向规则保持分离。

## 稳定 ID 与 JSONL 中间态

后续实现应以 `paragraph_id` 和 `segment_id` 作为段落与分段的稳定标识。原文目录保持只读，翻译、校验、重试、人工审核和润色状态进入 JSONL 中间态，最终阅读文件由 exporter 生成。

## 动态术语、角色与世界观注入

翻译时只注入当前 batch 命中的 glossary、character profile 与 world bible 条目，不全量塞表。`approved` 与 `locked` 资产优先，`candidate` 只作参考，`spoiler-sensitive` 世界观设定不得提前注入。

## Prompt 分层与版本化

Prompt 应拆分为 system base、direction rules、style profile、glossary block、character block、world bible block、context block、source block、output contract 和 validation reminder。每次模型调用都必须记录 `prompt_version`。

## ResponseExtractor 与 Validator

模型输出必须先经过 ResponseExtractor 解析为结构化结果，再由 Validator 检查 segment 覆盖、locked 术语、占位符、语言残留、长度比例、段落对齐和 Prompt 契约。

## 为什么校验失败不能写入译文

`validation_failed`、`failed` 和解析失败结果只能保存 raw output、validation errors、review issues 和 retry 状态，不能写入成功译文或 final。这样可以避免模型坏输出污染中间态与最终导出。

## Checkpoint、LLM Cache、Translation Memory 的区别

Checkpoint 解决“任务中断后从哪里继续”；LLM Response Cache 解决“相同请求是否避免重复调用 API”；Translation Memory 解决“已确认历史译法如何复用”。三者不得混用。

## Provider Adapter 与多模型路线

所有模型调用都必须经过 provider adapter / registry。MVP 先使用 fake provider 与 dry-run provider，真实 OpenAI-compatible、DeepSeek、Grok、OpenRouter、Anthropic、Gemini 等接入必须有用户授权、预算保护、model run metadata 和敏感信息脱敏。

## Exporter-only 输出原则

Exporter 是唯一负责生成最终阅读文件的模块。Exporter 不调用模型，不修改原文，不导出 `validation_failed` 到 final，并保留 `paragraph_id` 以支持审核回链。

## 后续 RM-01 到 RM-40 路线

参考仓库方法吸收后的 40 轮推进路线见 `docs/roadmap_rounds_reference_method_01_40.md`。RM 轮次只表示 Reference Method Absorption，不取代既有 Round 00–50 路线。

## 后续推进轮如何工作

1. 读取 `AGENTS.md` 与当前 Round Prompt。
2. 执行 `git status`，确认安全边界。
3. 只做当前 Round 范围内任务，不越级。
4. 更新 `governance/round_state.yaml` 与本地报告。
5. 用户或 Prompt 要求时再 commit；push 需用户授权。

## Continuous Agent Foundation

本仓库现在提供一套项目内连续 Agent 推进基础设施，供 Cursor / Codex / 其他 Agent 后续复用。状态、队列和阻塞记录位于 `.agent_runtime/`。

查看状态：

```bash
python3 scripts/agent.py status
```

进入下一轮：

```bash
python3 scripts/agent.py next
```

加入任务：

```bash
python3 scripts/agent.py enqueue --type bugfix --reason test_failure
python3 scripts/agent.py enqueue --type browser_inspection --reason periodic_check
python3 scripts/agent.py enqueue --type quality_optimization --reason low_quality_result
```

运行真实 API 小测入口：

```bash
python3 scripts/run_real_api_smoke.py
python3 scripts/run_real_api_smoke.py --real
```

运行浏览器检查：

```bash
python3 scripts/run_browser_inspection.py
```

真实 API Key 规则：

- 只从环境变量读取。
- 不提交 `.env`。
- 不打印 Key。
- 缺 Key 时 dry-run 或 `missing_api_key`，不阻断可替代流程。
- 不把 mock / dry-run 伪装成真实 API。

后续 Cursor 使用方式：

- Cursor 读取 `AGENTS.md` 和 `docs/agent_workflow/`。
- Cursor 使用 MCP 做页面和浏览器检查。
- Cursor 根据 `.agent_runtime/queue.jsonl` 触发修复或优化任务。
- 流程 bug 写入 `bugfix` 队列。
- 质量差写入 `quality_optimization` 队列。
- 页面问题写入 `browser_inspection` 队列。

## 当前不能做的事情

- 不启动真实长篇翻译（除非进入授权后的翻译执行轮）
- 不调用真实翻译 API（治理轮与未授权实现轮）
- 不生成 embedding、不建真实向量库（Round 48 之前）
- 不安装 Playwright/MCP（Round 44 之前，除非用户明确要求）
- 不提交 `.env`、真实原文、真实译文

## 下一轮建议

建议进入 **Round 41：Agent Gate MVP**（实现 `scripts/agent_gate.py`），或 **Round 42：Repo Protocol Checker**（实现协议合规检查脚本）。详见 `docs/roadmap_rounds_41_50_tooling_and_workbench.md`。
