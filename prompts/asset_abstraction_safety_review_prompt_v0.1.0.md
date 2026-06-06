# Asset Abstraction Safety Review Prompt v0.1.0

## 用途

人工或 LLM 辅助复核 `workspace/asset_extraction_runs/<run_id>/` 中的 JSONL 资产是否满足版权安全与抽象化要求。

## 输入

- `narrative_assets.jsonl` 等四类文件
- 可选：源 run 的 `segments.json`（仅用于 **检测重叠**，不得写入新资产）

## 复核清单

1. 是否缺少 `abstraction_level` / `copyright_safety_level` / `reuse_guidance`？
2. `pattern_description` 是否过长（>500 字）或像章节复述？
3. `generated_examples` 是否与原文有显著子串重叠？
4. 是否包含过多原作专名（片假名连续 ≥3、英文品牌式专名）？
5. `copyright_safety_level: unsafe` 是否被错误标记为可发布？
6. 叙事资产是否描述 **结构** 而非 **情节流水账**？

## 输出格式

```json
{
  "review_id": "safety-review-001",
  "run_id": "<extraction_run_id>",
  "passed": false,
  "blocked_asset_ids": ["na-xxx"],
  "findings": [
    {"asset_id": "na-xxx", "severity": "high", "reason": "example_from_source"}
  ],
  "recommendation": "不得写入 assets_extracted/；修正后重新提取"
}
```

## 决策

- 全部 `safe` 且零 high severity → 可考虑 `write_to_public_asset_library`（需用户授权）
- 任一 `unsafe` 或 high severity → 保持 run 目录隔离，不晋升公共库
