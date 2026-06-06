# 真实 API 测试说明

## 原则

- 项目 **支持** 真实 API 小规模测试（授权范围内）
- **没有 Key** 时使用 mock / dry-run，**不得** 将 mock 冒充 `real_api`
- Key 只从 **环境变量** 读取；脚本不读 `.env` 内容到日志（Workbench dev server 可为未设置变量加载 `.env`）
- 不提交 Key；不保存完整真实 API 响应全文到可提交路径

## 环境变量

见 `.env.example`：

- `OPENROUTER_API_KEY` 等 provider Key
- `REAL_API_TESTS_ENABLED=true` 才允许出站真实调用
- `MAX_TEST_COST_USD` — `0` 时阻断 Workbench 页面真实生成
- `STITCH_API_KEY` — 仅 Stitch 设计 MCP，与翻译 API 分离

## 入口脚本

```bash
# 状态与 dry-run
python3 scripts/run_real_api_smoke.py
python3 scripts/run_real_api_smoke.py --status-only

# 真实 API（需 Key + REAL_API_TESTS_ENABLED）
python3 scripts/run_real_api_smoke.py --real
python3 scripts/run_real_api_smoke.py --real --json

# 诊断
python3 scripts/run_real_api_diagnostic.py
```

npm 快捷方式：

```bash
npm run agent:real-api
npm run agent:real-api:real
```

## 产物

- 摘要报告：`.agent_runtime/real_api_reports/`（默认不提交正文）
- 诊断 run：`workspace/diagnostics/real_api_runs/`（本地，大文件不提交）

## Workbench 页面

首页 API 状态卡片区分：

- Key 是否已配置
- 页面 **真实 API 生成** 是否可调用（还依赖 `MAX_TEST_COST_USD>0`）

## Model Router

业务代码经 `model-router` 统一入口，不直连供应商 SDK。见 `model-router/README.md`。

## Agent 约定

- 治理轮默认不启动大批量真实翻译
- 有 Key 时优先小样本 smoke；无 Key 记录 `missing_api_key` 并继续 mock 路径
- 队列：`python3 scripts/agent.py enqueue --type bugfix --reason test_failure`

## 参考

- `docs/openrouter_api_test_plan.md`
- `AGENTS.md` — Continuous Real API Multi-Agent Foundation
