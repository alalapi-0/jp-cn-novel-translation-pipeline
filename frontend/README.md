# frontend

Phase 1 静态审核工作台 MVP（连续自动推进轮）。

## 页面

- `/index.html` — 项目首页（mock 项目列表）
- `/issues.html` — 质量审核 Issue 列表（读取 `assets/review-issue-report.json`）
- `/review.html` — 原文/译文对照审核，支持通过/驳回与 `AUTO_APPROVE`；高亮有 issue 的 segment

## 本地启动

```bash
npm run dev:frontend
# 或
python3 scripts/serve_frontend.py --port 5173
```

浏览器打开 `http://127.0.0.1:5173/`。

## 配置

`assets/config.js` 中 `AUTO_APPROVE` / `dryRunAutoApprove` 为自动推进阶段默认开启；`apiMode` 为 `dry-run`。横幅会显示 mock 标识。

审核状态保存在 `localStorage`（键 `light_novel_workbench_state_v1`）。
