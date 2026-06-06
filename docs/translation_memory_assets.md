# Translation Memory Assets

## 目标

翻译任务重启、重试或再次运行时，可以把过往已审核、已完成或已导出的译文沉淀为可复用资产，供后续 prompt / pipeline 读取。该能力与抽象创作资产层并存：本层保存翻译一致性信息，例如术语、译名、短语映射、段落级 source->target 记忆和风格提示。

默认模式是 `agent`，只使用本地 deterministic 启发式，不调用外部 API。

## 构建资产

从 Workbench manifest + review_state 构建，仅沉淀 `approved` 段落：

```bash
python3 scripts/build_translation_assets.py --project-id demo-jp-cn --json
```

从 `workspace/runs/<run_id>/segments.json` 构建，适合已完成 draft/refine run：

```bash
python3 scripts/build_translation_assets.py --source-run run_20260602_203645_draft_stage_b_50ch --status-mode translated
```

默认输出：

```text
workspace/assets/translation_memory/<project-or-run>.json
```

## 资产内容

资产 JSON 包含：

- `approved_pairs`: 已审核/已完成的 source->target 段落对
- `segment_map`: 按 segment_id 查找历史译文
- `term_candidates`: 方括号标签等术语候选
- `proper_noun_candidates`: 片假名专名等译名候选
- `phrase_candidates`: 短句级翻译记忆
- `style_notes`: 本地启发式生成的风格提示
- `context_prompt`: 可直接注入后续翻译 prompt 的压缩上下文

## 重启任务消费

重启 draft 翻译时显式传入资产上下文：

```bash
python3 scripts/translate.py \
  --phase draft \
  --stage stage_a \
  --limit-chapters 1 \
  --run-id retry-with-assets \
  --asset-context workspace/assets/translation_memory/demo-jp-cn.json
```

`run_metadata.json` 会记录 `asset_context_path`，便于审计该次重启任务使用了哪份翻译记忆资产。

## Workbench 入口

导出中心提供“翻译记忆资产”卡片：

1. 先在审核页把需要沉淀的段落标为 `approved`。
2. 打开 `/export.html?project=<project_id>`。
3. 点击“构建 approved 翻译资产”。
4. 页面会显示资产路径、pairs 数量、候选术语数量和 API 调用数。

## external_api 模式

`external_api` 是可选增强，不是默认路径。它需要同时满足：

- `TRANSLATION_ASSET_EXTERNAL_API_ENABLED=true`
- `REAL_API_TESTS_ENABLED=true`
- `OPENROUTER_API_KEY` 已配置
- 成本门控允许本次调用

未满足时会返回清晰错误，不会伪装成功。低成本测试应优先使用 mock provider 或默认 `agent` 模式。
