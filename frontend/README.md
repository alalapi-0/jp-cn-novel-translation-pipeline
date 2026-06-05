# frontend

Phase 1 静态审核工作台 MVP（连续自动推进轮）。

## 页面

- `/index.html` — 项目首页、**真实 API 状态**、**新用户 Quickstart**（创建项目 + dry-run 生成）
- `/issues.html?project=<id>` — 质量审核 Issue 列表
- `/review.html?project=<id>` — 对照审核（审核状态写入 `workspace/review_state.json`）
- `/export.html` — 导出中心（触发/查看 `output_cn/translated` 与 `bilingual`）

## 本地启动

```bash
npm ci
pip install -r requirements-dev.txt
npm run dev:frontend
```

浏览器打开 `http://127.0.0.1:5174/`。

## 真实 API 状态

首页「真实 API 状态」卡片读取 `/api/runtime/api-status`（不读取 `.env`）：

- 无 Key：`api_mode=missing_api_key`
- 有 Key 未启用真实测试：`dry_run`
- 启用 `REAL_API_TESTS_ENABLED=true` 且 smoke 成功：`real_api`

CLI 探测：

```bash
python3 scripts/run_real_api_smoke.py --status-only
python3 scripts/run_real_api_smoke.py --real   # 需 Key + REAL_API_TESTS_ENABLED
```

## 配置

`assets/config.js` 默认 `AUTO_APPROVE=false`。自动推进：`/review.html?auto_approve=1`

审核状态持久化在 `workspace/review_state.json`（API 优先，localStorage 为回退）。

## 测试

```bash
pytest tests/ -q
npm run test:ui
```
