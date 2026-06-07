# Model Switching Policy

## 当前生产默认

| 角色 | 模型 | 状态 |
| --- | --- | --- |
| draft_translation_primary | `deepseek/deepseek-v4-pro` | **enabled** |
| draft_translation_fallback | `deepseek/deepseek-v4-pro` | **enabled**（必须保留） |
| draft_translation_candidate | `nvidia/nemotron-3-ultra-550b-a55b:free` | **disabled** |

配置：`config/draft_models.yaml`、`model-router/config/models.yaml`

## 切换决策（2026-06-07）

Nemotron 隔离 A/B（`model_ab_20260607_104224`）：

| 指标 | DeepSeek | Nemotron |
| --- | --- | --- |
| validation / parse | 通过 | 通过 |
| avg_latency_ms | ~7,900 | **~195,800** |
| 结论 | **继续作 primary** | **不切换**（延迟过高） |

**用户确认**：不换模型；T-002 及后续轮次均使用 `deepseek/deepseek-v4-pro`。

## 切换流程（若未来重评）

1. 运行隔离 A/B：`python3 scripts/model_ab_test.py --isolated`
2. 除质量门外，**latency 须与 baseline 同量级**（20 章/轮可完成）
3. 仅满足上述条件方可将 candidate 设为 primary
4. **禁止**在同一 production run 中途混用模型

## A/B 通过条件（最小）

- candidate API 可响应
- parse_failed ≤ baseline
- validation_failed 不明显高于 baseline
- 无大量漏译/原文残留
- **latency 可接受**（本轮 Nemotron 因 ~25× 延迟被否决）

## 回退

任何 production 异常 → 设置 `DRAFT_MODEL=deepseek/deepseek-v4-pro` 或禁用 candidate profile。
