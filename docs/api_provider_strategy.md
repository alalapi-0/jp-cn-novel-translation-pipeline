# API Provider 抽象策略

项目未来可能接入 DeepSeek、Grok、OpenAI、OpenRouter、Anthropic、Google、Local Embedding Models 和 Other Compatible Providers。任何 provider 都不能写死在业务流程中。

## Provider 类型

- `embedding_provider`
- `terminology_provider`
- `translation_provider`
- `refinement_provider`
- `review_provider`

## Provider Adapter 字段

```yaml
provider_id:
provider_name:
base_url:
api_key_env_name:
model_name:
model_type:
supports_streaming:
supports_json_mode:
supports_long_context:
cost_profile:
rate_limit_profile:
notes:
```

## 安全规则

1. API Key 只能从 `.env` 或系统环境变量读取。
2. 不提交 `.env`。
3. 不在日志输出完整 Key。
4. 不在 metadata 输出完整 Key。
5. `.env.example` 只能写变量名。
6. 所有 provider 调用必须记录 model run metadata。
7. 出错时记录错误类型，不记录敏感请求头。
8. 真实 API 调用必须支持 dry-run、预算限制和显式用户授权。

## 模型选择策略

- embedding：成本低、速度快、稳定。
- 术语抽取：结构化输出稳定。
- 初翻：成本可控、长上下文、忠实。
- 润色：强推理、强语言能力。
- 审核：擅长对照检查和结构化问题输出。

## Model Run Metadata

每次模型调用应记录：

- `model_run_id`
- `project_id`
- `language_direction`
- `pipeline_stage`
- `provider_id`
- `model_name`
- `input_reference`
- `output_reference`
- `started_at`
- `finished_at`
- `status`
- `estimated_tokens`
- `actual_usage`
- `error_type`

不得记录完整 API Key、敏感请求头或真实正文长片段。
