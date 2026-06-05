# frontend

Phase 1 静态审核工作台 MVP。

## 页面

- `/index.html` — API 状态（来自 `/api/runtime/api-status`）、Quickstart（dry-run mock + 真实 API 小样本按钮）
- `/review.html?project=<id>` — 对照审核（`workspace/review_state.json` 持久化）
- `/export.html` — 导出中心（manifest 单项目 / runs 全量分离）

## 本地启动

```bash
npm ci
python3 -m venv .venv
source .venv/bin/activate
.venv/bin/pip install -r requirements-dev.txt
npm run dev:frontend
```

浏览器打开 `http://127.0.0.1:5174/`。

## 测试

```bash
.venv/bin/pytest tests/ -q
npm run test:ui
```

## 项目 ID 规则

仅允许字母、数字、`_`、`-`；禁止 `/`、`\`、`..`、空白及其他危险字符。非法 ID 返回 HTTP 400 JSON。

## 真实 API

```bash
.venv/bin/python3 scripts/run_real_api_smoke.py --status-only
.venv/bin/python3 scripts/run_real_api_smoke.py --real
```

Key 仅通过环境变量配置，勿提交 `.env`。
