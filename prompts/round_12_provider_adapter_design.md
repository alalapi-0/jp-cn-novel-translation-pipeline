# Round 12：LLM Provider Adapter 设计

## Agent 身份

你是 Provider Adapter Design Agent。

## 本轮目标

设计 provider adapter，并加入 fake provider 测试，不真实调用 API。

## 必读文件

`README.md`、`docs/api_provider_strategy.md`、`docs/data_schema_plan.md`、`docs/governance_rules.md`、`.env.example`。

## 当前上下文

未来可能接入 DeepSeek、Grok、OpenAI、OpenRouter、Anthropic、Google 和本地 embedding 模型。

## 允许修改

provider adapter 设计、fake provider、配置样例、`.env.example`、测试和文档。

## 禁止修改

不提交 `.env`，不输出完整 Key，不调用真实 API，不发送真实正文。

## 具体任务

1. 设计 provider interface。
2. 设计 request/response/error schema。
3. 设计 model run metadata。
4. 设计 provider config。
5. 实现 fake provider。
6. 增加 dry-run 测试。

## 验收标准

1. 不写死供应商。
2. fake provider 可运行。
3. Key 只通过环境变量名配置。
4. metadata 完整。
5. 测试不触发真实 API。

## 最终报告格式

说明 adapter、fake provider、配置、安全检查、测试和下一轮建议。

## Git 提交建议

`feat: design provider adapter with fake provider`
