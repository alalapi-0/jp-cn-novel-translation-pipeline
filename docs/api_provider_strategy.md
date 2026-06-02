# API Provider 抽象策略

项目未来可能接入 DeepSeek、Grok、OpenAI、OpenRouter、Anthropic、Google、Local Embedding Models 和 Other Compatible Providers。任何 provider 都不能写死在业务流程中。

## Provider 类型

- `fake_provider`
- `dry_run_provider`
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
- `prompt_version`
- `request_hash`
- `raw_output_ref`

不得记录完整 API Key、敏感请求头或真实正文长片段。

## Provider Registry 原则

所有 provider 必须通过 registry 和 adapter 被调用。业务流水线只依赖统一 `ModelAdapter.generate(messages, options) -> ModelResult`，不直接依赖具体 SDK。

`fake_provider` 与 `dry_run_provider` 是真实 API 之前的必经阶段。真实 OpenAI-compatible、DeepSeek、Grok、OpenRouter、Anthropic、Gemini 等 provider 只能在 API integration 或 translation execution 轮中启用，并必须具备用户授权、预算上限、timeout、retry、rate limit、敏感 header redaction 和 model run metadata。

Provider 返回的 raw output 不能直接写入译文；必须经过 ResponseExtractor 与 Validator。

## 实现入口（Round 47）

代码位于 `src/providers/`：

| 模块 | 用途 |
|------|------|
| `fake_provider.py` | 固定 JSON 响应，零 network |
| `dry_run_provider.py` | 记录 request_hash / token 估算，零 network |
| `cost_guard.py` | `MAX_TEST_COST_USD`、`MAX_TOKENS_PER_RUN` 超限 abort + log |
| `controlled_run.py` | `CONTROLLED_RUN_ENABLED` 开关与 checkpoint |
| `registry.py` | `get_provider(ProviderMode)` |

环境变量见 `.env.example`（仅变量名，无真实 Key）。

## Cost Guard 环境变量

| 变量 | 默认 | 说明 |
|------|------|------|
| `REAL_API_TESTS_ENABLED` | `false` | 为 `true` 时才允许 real provider（仍须 Key 与授权） |
| `MAX_TEST_COST_USD` | `0` | 累计估算成本上限，超出 abort |
| `MAX_TOKENS_PER_RUN` | `0` | 0=不限；正整数为 token 估算硬上限 |
| `COST_PER_MILLION_TOKENS` | `0.5` | dry-run 成本估算系数 |
| `CONTROLLED_RUN_ENABLED` | `false` | 受控试跑开关 |
| `CONTROLLED_RUN_ID` | `default` | checkpoint 文件名 |

Abort 日志写入 `workspace/model_runs/cost_guard_abort_*.json`（gitignore）。

## Round 50 受控试跑前置条件

进入 Round 50 E2E 受控试跑前须满足：

1. `tests/test_fake_provider.py`、`tests/test_dry_run_provider.py`、`tests/test_cost_guard.py` 全部 pass。
2. `agent_gate` 与 `check:tooling` 无 BLOCKED。
3. 默认配置下（`REAL_API_TESTS_ENABLED=false`、`MAX_TEST_COST_USD=0`）无任何 outbound HTTP。
4. fake → dry-run →（可选）controlled run 链路已在样例 segment 上验证。
5. 若启用真实 API：用户显式授权、`REAL_API_TESTS_ENABLED=true`、`.env` 中 Key 仅本地、预算上限已设、`CONTROLLED_RUN_ENABLED=true`。
6. checkpoint 与 model run log 不含完整 Key 或长正文。

Round 50 默认仍使用 fake/dry-run；真实调用仅在用户授权且 guard 通过时进行。
