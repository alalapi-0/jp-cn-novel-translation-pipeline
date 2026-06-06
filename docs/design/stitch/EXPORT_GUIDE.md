# Stitch 导出指南

## 导出类型

| 类型 | 来源 | 存放路径 |
|------|------|----------|
| Screen HTML | `getHtml()` / MCP 工具 | `docs/design/stitch/exports/` |
| 截图 | `getImage()` / MCP 工具 | `docs/design/stitch/screenshots/` |
| 设计说明 | Agent 整理 | `docs/design/stitch/exports/*-DESIGN.md` |
| Prompt 存档 | 生成前副本 | `docs/design/stitch/prompts/` |
| 评审记录 | 实现后对照 | `docs/design/stitch/reviews/` |

## 命名规范

```text
{date}_{page-slug}_{variant}.{ext}

示例：
20260606_review-workbench_desktop_v1.html
20260606_review-workbench_desktop_v1.png
20260606_review-workbench_DESIGN.md
20260606_review-workbench_prompt.md
20260606_review-workbench_implementation-review.md
```

- `page-slug`：与 `UI_TASKS.md` 章节对应（如 `dashboard`、`review-workbench`）
- `variant`：`v1`、`v2`、`dark`、`sidebar` 等

## HTML 导出步骤

1. 通过 Stitch MCP 或 SDK 获取 HTML **下载 URL**
2. 下载到 `exports/`（可用 `curl`，勿把 URL 中的 token 写入文档）
3. 在同级 `*-DESIGN.md` 记录：
   - Stitch project / screen ID（可脱敏后几位）
   - 布局说明
   - 与 `frontend/` 的差异项
   - 待实现组件列表

## 截图导出步骤

1. 保存 PNG/WebP 到 `screenshots/`
2. 文件名与对应 HTML 一致（扩展名不同）
3. 可选：在 `reviews/` 附 Playwright 实现后截图对比

## 什么应该提交 Git

- 设计说明 Markdown、prompt 存档、评审记录：**建议提交**
- HTML 原型与截图：**体积合理时可提交**；大文件放本地并在 review 中引用路径
- **绝不提交**：含 API Key 的 URL、`.env`、真实原文/译文

## 从导出到实现

1. 打开 `exports/*.html` 在浏览器预览（仅本地）
2. 提取：间距、层级、组件分区——**不是**整段 CSS/JS 复制
3. 映射到 `frontend/assets/styles.css` 变量与现有 class 命名风格
4. 在 `reviews/` 勾选实现清单

## Agent 检查清单

- [ ] 导出物已放入正确子目录
- [ ] prompt 已存档
- [ ] DESIGN.md / review 已写
- [ ] 未将 export HTML 覆盖 `frontend/*.html`
- [ ] 实现后已跑浏览器检查
