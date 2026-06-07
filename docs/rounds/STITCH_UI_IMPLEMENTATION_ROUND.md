# Stitch MCP 驱动的 UI 推进轮

## 1. 当前项目类型判断

- 项目类型：中日文小说互译生产流水线治理仓库，当前有静态 Review Workbench MVP。
- 前端形态：静态 HTML + `frontend/assets/app.js` + `frontend/assets/styles.css`，由 `scripts/serve_frontend.py` 提供本地 Workbench API。
- 当前主流程：首页 Quickstart 创建/生成项目 -> 对照审核 -> 质量 Issue -> 导出中心。
- 主要页面：`frontend/index.html`、`frontend/review.html`、`frontend/issues.html`、`frontend/export.html`。
- UI 设计约束：Dark theme、中文 UI、显式标记 `REAL_API` / `MOCK` / `DRY_RUN` / fixture fallback，不引入大型 UI 框架。

## 2. 本轮 UI 切片

本轮选择 `frontend/review.html` 的审核效率切片：为 Review Workbench 增加键盘快捷键与可见提示，提升长篇 segment 审核时的段落切换和通过/驳回效率。

选择依据：

- `docs/frontend_workbench_plan.md` 将 Side-by-side Translation Review 定义为连接审核和导出的核心页面。
- `docs/design/stitch/UI_TASKS.md` 明确 Review Workbench 需要 segment 列表、双栏对照、操作栏和质量 issue 入口。
- `docs/design/stitch/reviews/round3_ui_ux_review.md` 的后续可选项包含“审核页键盘快捷键（上一段/下一段）”。
- `docs/roadmap_phase2_rounds_51_plus.md` 的 Round 59 建议要求强化 Review Workbench 的长文本审核体验。

不在本轮范围：

- 不迁移 React/Vite。
- 不改后端数据契约。
- 不做完整 Dashboard 或 Debug Panel。
- 不调用真实翻译 API。

## 3. Stitch 使用计划与本轮 fallback 修复

### 状态检查

- `.cursor/mcp.json`：包含 `stitch` server，使用 `node scripts/stitch_mcp_proxy.mjs`。
- `docs/design/stitch/STITCH_MCP_SETUP.md`：存在，并说明无 Key 或工具超时时应使用模板 fallback。
- `.env.example`：包含 `STITCH_API_KEY` 占位符。
- 当前环境变量：`STITCH_API_KEY=SET`（仅检查是否存在，未打印值）。
- MCP descriptor：`project-0-light_novel-stitch/tools/` 存在，包含 `list_projects`、`generate_screen_from_text` 等工具 schema。

### 上次卡住原因

恢复读取上一个子代理 transcript 后确认：任务停在“检查 Stitch MCP 可用性/准备调用 `list_projects`”阶段，没有进入代码实现、测试、commit 或 push。上次疑似连轻量 `list_projects` 调用都长时间未返回或被用户中断。

### 本轮修复决策

本轮禁止再次发起可能长时间阻塞的 Stitch 生成调用。虽然环境变量存在，且 descriptor 可读，但因上次轻量工具调用已造成卡住，本轮将 Stitch 判定为“配置存在但运行不稳定”，采用以下 fallback：

- 使用 `docs/design/stitch/PROMPT_TEMPLATES.md` 的 Review Workbench 模板抽象设计。
- 使用 `docs/design/stitch/UI_TASKS.md` 的审核台组件清单拆分实现。
- 使用 Round 3 评审与 Round 59 路线图作为优先级依据。
- 将 fallback 设计说明、token 和参考 HTML 保存到 `docs/design/stitch/`，避免 Stitch 不可用阻断 UI 改造闭环。

后续重试建议：只在 Cursor MCP 面板确认 `stitch` 已连接、且用户接受潜在长等待时，先单次调用 `list_projects`；生成类工具必须按 descriptor 说明等待，不并发、不重复调用。

## 4. 实现计划

本轮落地内容：

- 在审核页右侧“状态与操作”区域新增快捷键提示。
- 支持 `J` / `ArrowDown` 选择下一段，`K` / `ArrowUp` 选择上一段。
- 支持 `A` 通过当前段，`R` 驳回当前段。
- 保持输入框、搜索框、select 内键盘输入不被快捷键拦截。
- 增强焦点可见性，方便键盘用户确认当前 segment。
- 增加 Playwright 回归测试覆盖键盘审核流。

## 5. 验收标准

- `review.html` 可以打开且非白屏。
- 页面仍显示 `api_mode` / mock / dry-run 等模式信息。
- segment 列表、双栏对照、质量 issue 入口和通过/驳回操作保持可用。
- 桌面宽度显示三栏；窄屏堆叠并保留底部操作栏。
- `J/K/A/R` 快捷键能完成“选择下一段 -> 通过 -> 回到上一段 -> 驳回”。
- Console 无本轮引入的严重错误；Network 无意外外域翻译 API 请求。
- `npm run check:mcp`、`npm run check:stitch`、相关 Playwright 测试通过或清楚记录环境阻塞。

## 6. 本轮验收记录

- MCP 配置：`npm run check:mcp` PASS。
- Stitch 配置：`npm run check:stitch` PASS；未调用生成工具。
- 目标 UI 测试：`npm run test:ui -- --grep "review page supports keyboard shortcuts|review state persists"` 2 passed。
- 全量 UI 测试：`npm run test:ui` 32 passed，3 skipped（规划中页面）。
- 浏览器页面：`http://127.0.0.1:5174/review.html?project=pw-keys-1780798054286`。
- 浏览器可见内容：模式横幅、项目切换、段落队列、双栏对照、状态与操作、快捷键提示均可见。
- 浏览器主流程：`J` 选择下一段、`A` 通过当前段已验证；Playwright 覆盖 `J/A/K/R` 完整路径。
- Network：仅出现本地 `/api/runtime/api-status`、`/api/projects`、`/api/projects/{id}/workbench-data`、`/review-state`、`/generation-job`、`/quality-review`，未出现外域翻译 API 请求。
- 响应式：390px 宽度下 `scrollWidth=390`，无横向溢出；底部审核操作栏显示。
- Python：首次 `npm run test:py` 在当前 shell 的 `REAL_API_TESTS_ENABLED=true` 环境下出现 1 个成本护栏默认值断言失败；随后 `REAL_API_TESTS_ENABLED=false npm run test:py` 160 passed。
