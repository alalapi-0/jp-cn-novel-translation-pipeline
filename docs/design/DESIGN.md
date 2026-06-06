# 设计输入层（Design Input Layer）

本目录是 **UI 设计输入层**，供 Cursor / Codex / Agent 在实现前端前查阅与落盘设计产物。设计输入与业务代码分离，避免 Stitch 或手工原型无审查地覆盖 `frontend/`。

## 定位

| 角色 | 职责 |
|------|------|
| **Stitch MCP** | 生成 UI 原型、screen、HTML、截图、DESIGN 说明 |
| **docs/design/** | 保存设计规范、任务模板、导出物与评审记录 |
| **Cursor Agent** | 按设计拆任务，用项目技术栈落地到 `frontend/` |
| **Playwright / chrome-devtools** | 实现后做真实浏览器验收 |

## 本项目设计约束

- **项目类型**：中日文小说互译生产流水线 + Review Workbench 静态前端
- **技术栈**：静态 HTML + `frontend/assets/app.js` + `frontend/assets/styles.css`；Workbench API 由 Python 提供
- **视觉偏好**：Dark theme（见 `frontend/assets/styles.css` 的 `--bg` / `--panel` / `--accent`）
- **文案语言**：中文 UI 为主；方向标记 `JP_TO_CN` / `CN_TO_JP` 保留英文枚举

## 目录结构

```text
docs/design/
├── DESIGN.md                 # 本文件：设计层总览
└── stitch/
    ├── README.md             # Stitch 在本项目中的用法
    ├── STITCH_MCP_SETUP.md   # MCP 配置与 Key
    ├── STITCH_WORKFLOW.md    # 端到端工作流
    ├── UI_TASKS.md           # 按页面的设计任务模板
    ├── PROMPT_TEMPLATES.md   # Stitch 专用 prompt
    ├── EXPORT_GUIDE.md       # 导出 HTML / 截图规范
    ├── exports/              # Stitch HTML / 设计说明导出
    ├── screenshots/          # Stitch 截图
    ├── prompts/              # 已使用的 prompt 存档
    └── reviews/              # 设计评审与实现对照记录
```

## Agent 必读顺序（UI 任务）

1. `docs/design/DESIGN.md`（本文件）
2. `docs/design/stitch/README.md`
3. `docs/design/stitch/UI_TASKS.md`
4. `docs/design/stitch/PROMPT_TEMPLATES.md`
5. `docs/frontend_workbench_plan.md`（页面清单与数据契约）

## 禁止事项

- 不得把 `docs/design/stitch/exports/` 中的 HTML **直接覆盖** `frontend/` 业务文件
- 不得在设计文档或 MCP 配置中写入真实 `STITCH_API_KEY`
- 不得跳过浏览器检查就宣称 UI 完成

## 相关文档

- `AGENTS.md` — Stitch Design MCP 章节
- `.cursor/rules/stitch-design-mcp.mdc` — Cursor 规则
- `docs/mcp/README.md` — 全部 MCP 说明
- `docs/testing/BROWSER_TESTING.md` — 浏览器验收
