# frontend

Phase 1 静态审核工作台 MVP（连续自动推进轮）。

## 页面

- `/index.html` — 项目首页（`/api/projects` manifest 列表，mock 回退）
- `/issues.html` — 质量审核 Issue 列表（读取 `assets/review-issue-report.json`）
- `/review.html` — 原文/译文对照审核，项目切换下拉框，支持通过/驳回与 `AUTO_APPROVE`

## 本地启动

```bash
npm run dev:frontend
# 或
python3 scripts/serve_frontend.py --port 5173
```

浏览器打开 `http://127.0.0.1:5173/`。

## 配置

`assets/config.js` 中 `AUTO_APPROVE` / `dryRunAutoApprove` 为自动推进阶段默认开启；`apiMode` 为 `dry-run`。

Round 53 起 dev server 同时提供 `/api/projects` 与 `PUT /api/projects/active`；首次访问会从 `data/examples/workbench_project.*.example.json` seed 到 `workspace/manifests/`（gitignore）。

审核状态保存在 `localStorage`（键 `light_novel_workbench_state_v1`）；当前项目 ID 键 `light_novel_active_project_v1`。
