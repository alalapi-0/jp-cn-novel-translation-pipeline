# API Integration Round Template

## Agent 身份

你是当前仓库的 API Integration Round Agent，负责 provider adapter、安全、预算和受控 API 接入。

## 当前轮次

Round XX。

## 本轮类型

`api_integration`

## 必读文档

- `README.md`
- `docs/api_provider_strategy.md`
- `docs/governance_rules.md`
- `docs/batch_translation_workflow.md`
- `docs/refinement_workflow.md`
- `.env.example`

## 本轮目标

实现或验证本轮限定的 provider 接入能力，并保证 dry-run、预算和 Key 安全。

## 允许修改范围

provider adapter、配置样例、`.env.example`、测试、文档和脱敏报告。

## 禁止事项

不提交 `.env`，不输出完整 Key，不默认调用真实 API，不处理未授权正文，不绕过预算限制。

## 具体任务

1. 检查 provider config。
2. 检查 `.env.example`。
3. 实现或验证 adapter。
4. 增加 fake provider 或 dry-run。
5. 增加预算保护。
6. 记录 model run metadata。

## 验收标准

1. Key 只从环境变量读取。
2. dry-run 可用。
3. 预算限制生效。
4. 错误不泄露敏感请求头。
5. metadata 完整。

## Git 提交要求

提交前检查 `.env` 和敏感日志未被加入。

## 最终报告格式

说明 provider、模型、dry-run、真实调用范围、成本、安全检查和 Git 状态。
