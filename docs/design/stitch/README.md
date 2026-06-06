# Stitch 设计 MCP（本项目）

[Google Stitch](https://stitch.withgoogle.com/) 为本仓库提供 **UI 设计能力**：生成设计方案、页面原型、screen HTML 与截图，供后续 Agent 实现 Review Workbench、导出页、管理视图等界面。

## 在本项目中的定位

Stitch **只负责设计输入**，不负责：

- 替代主开发 Agent 写业务逻辑
- 直接覆盖 `frontend/` 代码
- 调用翻译 API 或处理真实原文/译文

Stitch **应该用于**：

- 主控制台 Dashboard 布局探索
- 审核台 Review Workbench 信息架构
- 真实 API 生成任务页交互原型
- Debug / 可观测性面板
- 导出与质量审核相关页面

## 快速开始

1. 在 [Stitch 设置页](https://stitch.withgoogle.com/) 获取 API Key
2. 本地设置环境变量（**不要**写入仓库）：

   ```bash
   export STITCH_API_KEY=your_key_here
   ```

3. 确认 `.cursor/mcp.json` 已包含 `stitch` server（本地 stdio proxy）
4. **Reload Window** 或重启 Cursor，在 Settings → MCP 确认 `stitch` 已启用
5. 运行 `npm run check:stitch`

## 文档索引

| 文档 | 内容 |
|------|------|
| [STITCH_MCP_SETUP.md](./STITCH_MCP_SETUP.md) | MCP 与 API Key 配置 |
| [STITCH_WORKFLOW.md](./STITCH_WORKFLOW.md) | 设计 → 实现 → 验收流程 |
| [UI_TASKS.md](./UI_TASKS.md) | 按页面的设计任务模板 |
| [PROMPT_TEMPLATES.md](./PROMPT_TEMPLATES.md) | Stitch prompt 模板 |
| [EXPORT_GUIDE.md](./EXPORT_GUIDE.md) | 导出物存放与命名 |

## 产物存放

| 类型 | 路径 |
|------|------|
| HTML / DESIGN 导出 | `docs/design/stitch/exports/` |
| 截图 | `docs/design/stitch/screenshots/` |
| 使用过的 prompt | `docs/design/stitch/prompts/` |
| 设计评审记录 | `docs/design/stitch/reviews/` |

## 实现后验收

UI 落地后 **必须** 使用 `playwright` 或 `chrome-devtools` MCP（或 `npm run test:ui`）做真实浏览器检查。见 `docs/testing/BROWSER_TESTING.md`。

## 安全

- 仅通过 `STITCH_API_KEY` 环境变量认证
- 禁止提交 `.env` 与真实 Key
- 禁止在 `.cursor/mcp.json` 硬编码 Key
