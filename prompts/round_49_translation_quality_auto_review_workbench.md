# Round 49：Translation Quality Auto-review Workbench

## Agent 身份

你是 Quality Review Workbench Agent，负责将术语/角色/世界观冲突、漏译、润色 diff 等接入前端或结构化报告。

## 当前轮次

Round 49

## 本轮类型

`review` / `frontend`

## 背景

项目价值在于一致性与可复查性（`docs/quality_review_workflow.md`）。需在 Workbench 或报告中集中展示 auto-review 结果。

## 必读文件

- `docs/quality_review_workflow.md`
- `docs/refinement_workflow.md`
- `docs/terminology_system_design.md`
- `docs/frontend_workbench_plan.md`
- Round 46–47 产出

## 允许修改

review issue schema、frontend review 页面、checker 脚本、样例 issue JSON、文档。

## 禁止修改

不静默覆盖 human_edited 内容；不删除 review history；不提交真实长篇译文。

## 工具要求

Python checker 脚本、frontend 数据绑定、可选 Playwright 验证 Round 46 页面。

## MCP / Playwright 要求

若改 UI，Round 46 级浏览器 spot-check 至少 1 次。

## 通用协议要求

review 状态可追踪（artifact、chapter、version、reviewer、decision）。

## 具体任务

1. 定义 issue 类型：术语冲突、角色语气、世界观冲突、漏译、多译、润色 diff。
2. 实现至少 2 类 deterministic checker（如术语一致性、段落对齐）on 样例数据。
3. 输出 JSON/Markdown issue report 供 Workbench 读取。
4. 在 frontend 增加 issue 列表或 diff 视图（或文档化 wire-up 若 UI 未就绪）。
5. 链接到 quality_review_workflow 状态机。
6. Playwright 验证 issue 页可见（若 UI 存在）。
7. 更新 round_state 与 file_role_map（若新增 schema）。
8. 准备 Round 50 e2e 验收清单。

## 验收标准

1. issue schema 文档化且样例 JSON 存在。
2. 至少 2 类 checker 对样例有 deterministic 输出。
3. Workbench 或报告可展示 issues。
4. human_edited 轨迹未被破坏。
5. 无真实 API 批量调用。
6. 浏览器或报告证据存在。
7. agent_gate WARNING 已记录（若有）。

## 安全检查

样例数据 synthetic；不 leak 用户 private edits。

## Git 提交建议

`feat: add translation quality auto-review workbench scaffold`

## 最终报告格式

issue_types、checkers_implemented、ui_status、sample_output、e2e_prereqs。
