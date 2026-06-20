# Model Router

统一 LLM 调用入口，业务代码通过 `model_router.chat(...)` 访问模型，不直接依赖 OpenAI / Anthropic / Gemini / OpenRouter 等 SDK。

## 目录

```
model-router/
  config/models.yaml    # profile、provider、fallback 配置
  src/model_router/
    modelRouter.py      # 路由核心
    providers/
      openaiCompatible.py
      anthropic.py
      gemini.py
```

## 快速使用

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path("model-router/src").resolve()))

from model_router import chat, ChatOptions

result = chat(
    [{"role": "user", "content": "Reply exactly: smoke_ok"}],
    ChatOptions(profile="fast", max_tokens=32, temperature=0.0),
)
print(result.content, result.provider, result.model, result.usage.to_dict())
```

返回结构：

| 字段 | 说明 |
|------|------|
| `content` | 模型文本输出 |
| `model` | 实际使用的模型名 |
| `provider` | 实际使用的 provider id |
| `usage` | token 用量 |
| `raw` | 供应商原始 JSON（不含 prompt） |

## 配置

### models.yaml

- `default_profile`：默认 profile（可被环境变量覆盖）
- `profiles.*`：每个 profile 指定 `provider`、`model`、`temperature`、`fallback` 链
- `providers.*`：provider 类型、`base_url`、`api_key_env`、超时与重试

Pipeline 专用 profile：

- `draft_translation` — 翻译执行
- `legacy_refinement` — 历史 Stage C 复现入口（默认流程不使用）
- `coding` / `fast` / `reasoning` — 通用场景

### 环境变量

见仓库根目录 `.env.example`：

- `MODEL_ROUTER_DEFAULT_PROFILE` — 覆盖默认 profile
- `MODEL_ROUTER_CONFIG_PATH` — 自定义 YAML 路径
- 各 provider 的 `*_API_KEY`（仅环境变量，不入库）

## Fallback 规则

| 错误类型 | 行为 |
|----------|------|
| 400 参数错误 | 立即失败，**不** fallback |
| 401/402/403/429/5xx/超时/网络 | 按 profile.fallback 切换下一 provider |
| 同一 provider | 按 `max_retries` 重试（指数退避） |

日志仅记录 provider id、状态码与 retry 元数据，**不**记录 prompt、用户内容或 API key。

## 与现有 pipeline 集成

`src/providers/router_provider.py` 将 legacy `provider.generate()` 桥接到 model router：

- `get_provider(ProviderMode.REAL)` → `RouterProvider`
- `draft_runner` / workbench 真实 API 样本均已迁移；legacy `refine_runner` 仅用于显式历史复现

保留 `OpenRouterProvider` 作为兼容层（内部使用 `openaiCompatible` adapter）。

## 国内中转 / OpenAI-compatible

在 `models.yaml` 增加 provider 即可，例如：

```yaml
providers:
  my_relay:
    type: openai_compatible
    base_url: https://your-relay.example.com/v1
    api_key_env: DOMESTIC_RELAY_API_KEY
```

然后在 profile 中引用 `provider: my_relay`。

## 测试

```bash
.venv/bin/pytest tests/test_model_router.py tests/test_openrouter_provider.py -q
```
