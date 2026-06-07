# Model Switching Policy

## 当前生产默认

| 角色 | 模型 | 状态 |
| --- | --- | --- |
| draft_translation_primary | `deepseek/deepseek-v4-pro` | **enabled** |
| draft_translation_fallback | `deepseek/deepseek-v4-pro` | **enabled**（必须保留） |
| draft_translation_candidate | `nvidia/nemotron-3-ultra-550b-a55b:free` | **disabled** |

配置：`config/draft_models.yaml`、`model-router/config/models.yaml`

## 切换流程

1. 运行隔离 A/B：`python3 scripts/model_ab_test.py --isolated`
2. 报告输出：`workspace/diagnostics/model_ab_tests/<ab_run_id>/model_ab_report.json`
3. 仅当 `production_switch_allowed=true` 时，将 candidate 设为 primary
4. **禁止**在同一 production run 中途混用模型
5. T-002 若已在 DeepSeek 下运行，须完成后再切换；T-003 起可用新 primary

## A/B 通过条件（最小）

- candidate API 可响应
- parse_failed ≤ baseline
- validation_failed 不明显高于 baseline
- 无大量漏译/原文残留
- latency 与 cost 可接受

## 回退

任何 production 异常 → 设置 `DRAFT_MODEL=deepseek/deepseek-v4-pro` 或禁用 candidate profile。
