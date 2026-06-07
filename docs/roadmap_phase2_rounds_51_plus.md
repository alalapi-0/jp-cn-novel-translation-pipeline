# Phase 2 路线图（Round 51+）

Round 41–50 已在合成样章上验证工具链；Phase 2 在用户授权与预算内推进**受控真实 API**、长篇试点与语义 checker 硬化。

## Round 51：OpenRouter 冒烟 + 日语漏译启发式

### 目标

- `scripts/run_openrouter_smoke.py`：单次低成本连通性验证（默认 dry-run；双开关开启时真实调用）。
- 强化 `checker.segment_alignment` 的 `OMISSION` 启发式：日文/混合 CJK 用字符长度而非西方分词。
- 更新 `governance/round_state.yaml` 进入 Phase 2。

### 验收

- `python3 scripts/run_openrouter_smoke.py` 在 dry-run 下 exit 0。
- 真实 API（若本地 Key + `REAL_API_TESTS_ENABLED`）单次花费 ≤ `MAX_TEST_COST_USD`。
- `pytest tests/test_quality_review_checkers.py tests/test_openrouter_smoke.py` 通过。
- `agent_gate` PASS/WARN；Playwright smoke 仍绿。

## Round 52：Stage C 受控润色试跑

### 目标

- `scripts/refine_stage_c.py`：小批量 refine（`REFINE_MODEL`），`human_edited` 保护，硬上限 30 段/次。
- 产物：`refine_diff.json`、`refine_quality_report.json`；`workspace/stage_state.json` 进入 `phase=refine`。

### 验收

- `refine_stage_c.py --dry-run` exit 0（本地存在 Stage B run 时）。
- `pytest tests/test_refine_stage_c.py` 通过。
- 可选真实 API 试跑 ≤ `MAX_TEST_COST_USD`。

## Round 53（建议）：多项目 manifest 后端

- `workspace/manifests/` 多 `project_id`；`workspace/workbench_state.json` 记录当前项目。
- `scripts/serve_frontend.py` 暴露 `/api/projects` 与项目切换；Workbench 首页/审核页可切换。
- `data/examples/workbench_project.*.example.json` 为可提交样例；gate 自动 seed 到 workspace。

### 验收

- `pytest tests/test_multi_project_manifest.py` 通过。
- `agent_gate` 含 `round_53_*` 检查项 PASS/WARN。
- Playwright smoke 仍绿（双项目卡片可见）。

## Round 54：语义 checker MVP

- `src/quality_review/checkers.py`：`check_mistranslation`（日源否定 vs 中译肯定动作）、`check_placeholder_lost`（`{{}}` / URL / `{PH_*}`）。
- `src/quality_review/workbench_adapter.py` + `GET /api/projects/{id}/quality-review`。
- 前端 `fetchIssueReport` 优先 API，静态 JSON 回退；fixture `seg-004`/`seg-005` 可复现。

### 验收

- `pytest tests/test_semantic_checkers.py tests/test_quality_review_checkers.py`
- `agent_gate` 含 `round_54_*` PASS/WARN。
- Playwright smoke 仍绿（issues/review 无 console error）。

## Round 55：CI 工具链集成

### 目标

- `.github/workflows/ci.yml`：`check:tooling` 在 push/PR 上必跑；`test:ui` 在 main push 与 `workflow_dispatch` 可选开启（PR 默认仅 tooling）。
- `scripts/run_tooling_checks.sh` 在 `CI=true` 时强制 `REAL_API_TESTS_ENABLED=false`。
- `agent_gate` 含 `round_55_*` 检查项。

### 验收

- `npm run check:tooling` exit 0 或 1（无 BLOCKED）。
- `npm run check:mcp` 可 WARN（无 token 不阻塞）。
- `agent_gate` 含 `round_55_ci_workflow_exists` PASS。
- 本地 `npm run test:ui` 仍绿（非 CI 硬阻塞）。

## Round 59（建议）：静态 Workbench 设计系统与文本审核 UI 落地

### 轮次类型

frontend / design_system / browser_validation

### 背景

Round 57 已落地静态 Workbench MVP（`frontend/index.html`、`frontend/review.html`、`frontend/issues.html`、`frontend/export.html` + `frontend/assets/app.js` / `styles.css`），Round 58 聚焦吞吐恢复与安全门控。当前 `docs/design/` 已建立 Stitch 设计输入层，但 `docs/design/DESIGN.md` 仍偏目录总览，尚未沉淀为可指导静态 HTML 工作台迭代的设计真相源；前端也仍缺少面向长篇文本审核的统一布局密度、双栏对照规范、术语/质量提示视觉规则、移动端审核手势与浏览器验收矩阵。

本轮吸收外部 UI 参考报告的可落地结论：文本翻译类工具优先双栏对照、章节/segment 导航、术语提示、质量 issue 联动、auto-save/状态反馈、diff/润色对比、Table/Badge 状态映射与真实浏览器验收；但不得把外部报告全文、参考仓库代码或商业模板直接搬入本仓库。

### 后续推进轮 Agent Prompt

你是本仓库 Round 59 的实现 Agent。请在保护当前未提交改动的前提下，将静态 Workbench 从「可用 MVP」推进到「有明确设计系统、文本审核密度与浏览器验收证据」的状态。全程使用简体中文写文档与 UI 文案；代码命名沿用仓库既有英文枚举与路径。

#### 目标

1. 把 `docs/design/DESIGN.md` 从设计输入层总览扩写为本项目 UI 设计真相源，覆盖静态 HTML + `frontend/assets/` 的 token、布局、组件、页面与验收规则。
2. 在不迁移 React/Vite、不引入新 UI 框架的前提下，优化现有静态 Workbench 的视觉一致性与长文本审核体验。
3. 为 Review Workbench 明确并尽量落地：segment 列表、原文/译文双栏、质量 issue/术语提示、run 元数据、REAL_API/MOCK/DRY_RUN 数据源标记、移动端单栏/底部操作栏。
4. 用 Playwright 或 Chrome DevTools / Cursor browser MCP 做真实浏览器验收，覆盖页面可见内容、console error、network 关键请求与核心用户流程。

#### 范围

- 必须优先处理当前已存在页面：`frontend/index.html`、`frontend/review.html`、`frontend/issues.html`、`frontend/export.html`、`frontend/assets/styles.css`、`frontend/assets/app.js`。
- 可以新增或更新 `docs/design/stitch/reviews/round59_ui_design_gap_audit.md`、`docs/design/stitch/prompts/round59_*.md`、`docs/design/stitch/exports/round59_*.md`，但 Stitch 产物只能作为设计输入，不得无审查覆盖业务代码。
- 可以扩展 `tests/ui/` 的 Playwright 用例或更新 `frontend/README.md` 的 UI 验收说明。
- 不做 React/Vite 迁移，不做完整后端重构，不做真实批量翻译，不做真实 API 调用。

#### 必读输入

1. 仓库治理与路线：`AGENTS.md`、`project.yaml`、`governance/round_state.yaml`、`docs/index.md`、`docs/roadmap_phase2_rounds_51_plus.md`、`docs/roadmap_rounds_41_50_tooling_and_workbench.md`。
2. 产品与架构：`docs/project_vision.md`、`docs/architecture_overview.md`、`docs/frontend_workbench_plan.md`、`docs/quality_review_workflow.md`。
3. 设计层：`docs/design/DESIGN.md`、`docs/design/stitch/README.md`、`docs/design/stitch/UI_TASKS.md`、`docs/design/stitch/PROMPT_TEMPLATES.md`、`docs/testing/BROWSER_TESTING.md`。
4. 当前实现：`frontend/README.md`、`frontend/*.html`、`frontend/assets/styles.css`、`frontend/assets/app.js`、现有 `tests/ui/`。
5. 外部报告仅作抽象参考，不复制全文：`04_TEXT_TRANSLATION_NOVEL_UI_REPORT.md`、`08_DESIGN_MD_TEMPLATE_FOR_MY_PROJECTS.md`、`07_CURSOR_UI_IMPLEMENTATION_TASKS.md`、`01_UI_DESIGN_ABSTRACTION_REPORT.md`。

#### 实现任务

1. 设计差距审计：对照当前 `frontend/` 与 `docs/design/`，写出 Round 59 UI gap audit，按 P0/P1/P2 标注「必须改」「可后续」「不适用」。重点检查双栏阅读密度、状态 badge、空/loading/error 态、移动端、focus 可见性、术语/issue 可定位性。
2. DESIGN 真相源：扩写 `docs/design/DESIGN.md`，至少包含项目概述、技术栈、dark theme token、布局规则、阅读/审核 typography、状态 badge 映射、页面级规范、交互反馈、响应式策略、a11y checklist、禁止事项与浏览器验收清单。
3. 静态 UI 落地：在现有静态 HTML/CSS/JS 内小步优化，不引入第二套 UI 库。优先统一 `header`/`main`/`card`/`badge`/`button`/`table or list` 视觉规则；Review 页优先强化双栏对照、segment 定位、质量 issue 入口与数据源标记；Issues 页优先强化筛选与状态流转可读性；Export 页优先强化 `approved` / `draft` 风险提示。
4. 文本审核体验：为长篇章节保留阅读友好行高与宽度，移动端使用单栏或堆叠模式，不允许 320px 宽度出现横向溢出；所有真实 API、mock、dry-run、fixture fallback 状态必须可见。
5. 测试与文档：更新或新增 Playwright 测试，覆盖项目首页、对照审核、质量 Issue、导出中心四类页面的关键路径；更新 `frontend/README.md` 或相关设计文档说明本轮 UI 验收命令。

#### 浏览器验收要求

1. 启动本地前端后，用 `npm run test:ui` 或等价 Playwright 命令验证现有 smoke 与本轮新增路径。
2. 使用 Playwright / Chrome DevTools / Cursor browser MCP 至少真实打开四个页面：`/index.html`、`/review.html`、`/issues.html`、`/export.html`。
3. 验收必须记录：页面可见主标题与核心 CTA、console 无未解释 `error`、network 不出现意外外域翻译 API 请求、核心按钮/筛选/项目切换或导出风险确认可交互。
4. 截图、trace、浏览器报告写入 `artifacts/` 或 `docs/reports/` 的本地报告说明中；`artifacts/` 不提交 Git。

#### 产物路径

- 设计真相源：`docs/design/DESIGN.md`
- 设计差距/验收记录：`docs/design/stitch/reviews/round59_ui_design_gap_audit.md` 或 `docs/reports/round59_ui_browser_validation.md`
- 前端实现：`frontend/*.html`、`frontend/assets/styles.css`、`frontend/assets/app.js`
- UI 测试：`tests/ui/`（沿用现有 Playwright 结构）
- 文档说明：`frontend/README.md` 或 `docs/testing/BROWSER_TESTING.md` 的最小必要更新

#### 禁止事项

- 禁止读取或打印 `.env` 内容；禁止把 API Key、PAT、cookie、真实原文/真实译文写入文档、测试、截图或 Git。
- 禁止直接复制外部报告全文、参考仓库整页代码或 Stitch 导出 HTML 到 `frontend/`。
- 禁止引入 React/Vite、shadcn、Tailwind 或第二套 UI 库来替代当前静态技术栈，除非用户另开迁移轮明确授权。
- 禁止真实 API 调用、批量翻译、覆盖 workspace 运行产物或删除用户未提交文件。
- 禁止在没有浏览器证据时宣称 UI 完成。

#### 安全边界

- 所有演示数据使用 fixture、mock 或用户明确授权样例；报告中只写脱敏摘要。
- 真实 API 相关按钮只能检查 UI 状态，不填入密钥、不绕过 `REAL_API_TESTS_ENABLED` / `MAX_TEST_COST_USD`。
- 修改前后都要检查 Git diff，仅提交用户明确要求的文件；本轮默认不 commit、不 push。
- 发现 MCP / Playwright 不可用时，记录为 soft blocker，并使用 `npm run test:ui` 或最小本地浏览器检查作为 fallback。

#### 验收标准

1. `docs/design/DESIGN.md` 足以让后续 Agent 不依赖外部报告即可理解本项目 UI token、布局、组件、页面和验收规则。
2. 当前四个静态页面在桌面宽度与 375px 移动宽度下无明显重叠、横向溢出或不可见核心操作。
3. Review 页能清晰体现 segment 列表、原文/译文对照、审核操作、数据源/模式标记与质量 issue 入口。
4. Issues 页和 Export 页的筛选、状态、风险提示与禁用/确认状态可读。
5. Playwright 或 MCP 浏览器验收有可复现命令与结果记录；console error 与 network 外域请求检查有结论。
6. `git diff` 中无 `.env`、真实密钥、未授权原文/译文、无关大文件或 artifacts。
7. 未完成项写入 gap audit 的 P1/P2 后续清单，不把未实现功能伪装成已完成。

## 安全与成本

- 不得提交 `.env`、真实原文/译文、API Key。
- 所有真实调用须 `REAL_API_TESTS_ENABLED` + `MAX_TEST_COST_USD` + 用户授权范围。
- 产物默认落在 `workspace/`（gitignore）。
