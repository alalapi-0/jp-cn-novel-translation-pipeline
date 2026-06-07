# Stitch Round 设计说明（fallback）

## Stitch MCP 状态

- 本轮读取了 `project-0-light_novel-stitch` 的工具 descriptor。
- `list_projects` 是轻量查询工具；`generate_screen_from_text` 明确可能耗时数分钟。
- 上一个任务停在 Stitch 可用性检查附近，疑似 `list_projects` 调用未返回或被中断。
- 本轮不再调用 Stitch 生成工具，避免重复卡住。

## fallback 决策

虽然 `STITCH_API_KEY` 在当前环境中为 `SET`，但本轮将 Stitch MCP 判定为“配置存在但运行不稳定”。推进方式改为：

1. 使用 `PROMPT_TEMPLATES.md` 的 Review Workbench 模板作为设计 prompt 来源。
2. 使用 `UI_TASKS.md` 的审核台组件清单约束实现范围。
3. 使用 Round 3 UI/UX 评审中的“审核页键盘快捷键”作为本轮切片。
4. 使用 Playwright 浏览器检查替代 Stitch screen 生成闭环。

## 本轮设计切片

页面：`frontend/review.html`

目标用户：译者 / 审核员

目标：降低长篇 segment 审核的鼠标依赖，让审核员能连续完成上一段/下一段、通过、驳回。

核心交互：

- `J` / `ArrowDown`：选择下一段。
- `K` / `ArrowUp`：选择上一段。
- `A`：通过当前段。
- `R`：驳回当前段。
- 输入框、搜索框、select 内不触发全局快捷键。

## 实现对照

| 设计要求 | 实现位置 | 验收方式 |
|---|---|---|
| 快捷键提示可见 | `frontend/assets/app.js` 渲染 `.review-shortcuts` | 浏览器查看右侧栏 |
| 当前 segment 可定位 | `.review-queue-item.is-active` + focus 样式 | Playwright 断言 active class |
| 键盘选择上下段 | `setupReviewKeyboardHandler` | `tests/ui/workbench.spec.ts` |
| 键盘通过/驳回 | `applyReviewSegmentAction` 复用原逻辑 | Playwright 状态 badge 断言 |
| 不改变后端契约 | 仍调用原 `/review-state` patch | 现有审核持久化测试 |

## 未生成截图

本轮没有生成 Stitch screenshot，原因是上次 Stitch MCP 轻量调用已卡住；为避免再次阻塞，改用真实浏览器检查和 Playwright 测试作为验收证据。
