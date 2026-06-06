# 用户视角测试说明

## 角色分工

| 角色 | 职责 | 是否改代码 |
|------|------|------------|
| **Codex（用户视角 Agent）** | 像真实用户一样走流程，输出问题与改进任务 | **否** |
| **Cursor（推进 Agent）** | 根据队列与报告落地修复、实现 UI | **是** |
| **Stitch** | 提供 UI 设计输入 | 仅设计层 |
| **Playwright / chrome-devtools** | 客观页面与网络检查 | 工具 |

## Codex 用户视角流程

1. 启动 Workbench：`npm run dev:frontend`
2. 走核心用户路径：
   - 查看首页 API 状态
   - 进入审核台浏览 segment
   - 导出页选择 approved/draft
   - （若授权）真实 API 小样本生成
3. 使用浏览器观察：布局、文案、错误提示、模式标记是否清晰
4. 输出 **问题清单** 与 **改进任务**（可写入 `.agent_runtime/queue.jsonl` 或 inspection 报告）
5. **不** 直接修改 `frontend/` 或 `src/`

## 必须覆盖的路径

- **浏览器**：真实加载页面，非 curl-only
- **真实 API 路径**：有 Key 时验证 real；无 Key 时验证 dry-run 提示诚实
- **模式诚实**：UI 必须区分 REAL_API / MOCK / DRY_RUN

## 与 Stitch 设计验收

用户视角测试可对照：

- `docs/design/stitch/UI_TASKS.md` 成功标准
- `docs/design/stitch/reviews/` 实现对照表

发现「设计与实现不一致」时写入 `browser_inspection` 或 `bugfix` 队列。

## 队列入口

```bash
python3 scripts/agent.py enqueue --type browser_inspection --reason periodic_check
python3 scripts/agent.py enqueue --type bugfix --reason ux_issue_from_codex
```

## 参考

- `docs/agent_workflow/browser_inspector_agent.md`
- `docs/agent_workflow/continuous_multi_agent_loop.md`
- `docs/testing/BROWSER_TESTING.md`
