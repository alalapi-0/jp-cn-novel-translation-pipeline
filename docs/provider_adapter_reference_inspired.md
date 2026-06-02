# Provider Adapter 与 Registry 设计

本设计吸收 TranslateBooksWithLLMs、AiNiee、LunaTranslator、BallonsTranslator 的统一适配思路。业务流水线只能调用 ModelAdapter，不直接调用具体 provider SDK。

## 接口草案

```python
class ModelAdapter:
    def generate(self, messages, options) -> ModelResult:
        ...
```

## ModelResult

```yaml
provider_id:
model_id:
model_run_id:
raw_output:
parsed_output:
usage:
cost_estimate:
latency_ms:
finish_reason:
error:
```

## Provider 类型

1. `fake`
2. `dry_run`
3. `openai_compatible`
4. `deepseek`
5. `grok`
6. `openrouter`
7. `anthropic`
8. `gemini`
9. `local_embedding`
10. `cloud_embedding`

## Registry

```yaml
providers:
  - provider_id:
    provider_type:
    base_url:
    api_key_env_name:
    default_model_id:
    enabled:
    supports_json_mode:
    supports_streaming:
    supports_embedding:
    timeout_seconds:
    max_retries:
    rate_limit:
    cost_profile:
```

## 横切能力

1. retry。
2. backoff。
3. rate limit。
4. timeout。
5. token estimate。
6. cost guard。
7. model run metadata。
8. raw response storage。
9. sensitive header redaction。
10. provider fallback。

## Fake Provider

用途：

1. 不调用真实 API。
2. 让 parser -> context -> prompt -> extractor -> validator -> exporter 链路可测试。
3. 生成固定、可预测的结构化输出。
4. 用于 CI 和治理轮自检。

禁止：

1. 假装代表真实模型质量。
2. 读取 `.env`。
3. 处理真实长篇内容。

## Dry-run Provider

用途：

1. 构建请求但不发送。
2. 估算 token 和成本。
3. 记录 prompt_version、segment_ids、provider 配置。
4. 在真实 API 轮前做安全检查。

## OpenAI-compatible Provider

用途：

1. 接 DeepSeek、OpenRouter、兼容代理或其他兼容接口。
2. 统一 messages/options/result。
3. 支持 JSON mode 能力声明。

安全要求：

1. API Key 只从 `.env` 或环境变量读取。
2. 不打印完整 key。
3. raw response 不包含敏感 header。
4. 真实调用必须有用户授权、预算上限和小样例范围。

## ModelRun Metadata

```yaml
model_run_id:
project_id:
language_direction:
pipeline_stage:
provider_id:
model_id:
prompt_version:
input_segment_ids:
request_hash:
started_at:
finished_at:
status:
usage:
cost_estimate:
error_type:
raw_output_ref:
```

## Fallback 策略

Provider fallback 只能在配置明确允许时发生。fallback 不能绕过成本上限、不能改变输出契约、不能自动把失败输出写入译文。

## 验收标准

1. fake provider 可跑通完整链路。
2. dry-run 不调用 API。
3. provider 可通过 registry 配置。
4. model_run metadata 可追踪。
5. 敏感 header 和 API key 不进入日志或报告。
