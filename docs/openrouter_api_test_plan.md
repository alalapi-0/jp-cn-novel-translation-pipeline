# OpenRouter API 测试规划

## 1. API Key 管理

- **环境变量**：`OPENROUTER_API_KEY`
- **示例 .env**：请参见根目录的 `.env.example`，其中只保留变量名，不写真实值或仿真密钥。
- **安全性**：绝不在仓库中提交真实密钥；所有 CI/脚本均使用 `dry_run` 模式，只有在显式启用 `REAL_API_TESTS_ENABLED=true` 时才会进行真实调用。

## 2. 模型分工配置（示例）

```yaml
models:
  draft_translation: deepseek/deepseek-v4-flash
  polish: google/gemini-3.5-flash
  reasoning_review: google/gemini-3.5-pro
  embedding: google/gemini-embedding-2
runtime:
  output_dir: output_cn/experiments
  dry_run: true
  overwrite_existing: false
```

> **注**：实际模型名称请根据 OpenRouter 当前可用模型列表自行确认。

## 3. 小样本测试范围

- **章节**：仅选取第 **001** 章节前 **500‑1000** 字进行测试。
- **流程**：
  1. **初译**：使用 `draft_translation` 模型生成 `draft_001.md`（写入 `output_cn/experiments/`）。
  2. **润色**：使用 `polish` 模型对草稿进行润色，生成 `polished_001.md`。
  3. **术语一致性检查**：调用 `scripts/check_terms.py`（假设已实现）对 `polished_001.md` 与 `glossary.md` 进行比对。可选：使用 `embedding` 检索相关上下文片段。

## 4. 实验输出记录

每次实验应生成 `output_cn/experiments/experiment_001_log.md`，记录：

- 时间戳
- 使用的模型名称
- 输入文件路径
- 输出文件路径
- Prompt（已脱敏）
- 是否成功
- 错误信息（如有）
- 估算 token 数与成本（仅估算，不调用计费 API）
- 人工评价（简短文字）

## 5. 失败处理策略

- 记录错误信息但 **不删除** 已有正式译文或实验文件。
- 实验失败不影响仓库状态；后续可在 `output_cn/experiments/` 继续追加新实验。
- 若出现 API 错误（如配额、网络），仅在日志中记录并保持 `dry_run` 状态。

## 6. 后续计划

- 将上述实验脚本抽象为统一的 CLI 工具 `scripts/run_openrouter_test.py`，支持 `--model draft|polish|embedding` 参数。
- 在 `CHANGELOG.md` 中记录每一次真实 API 调用的日期、模型、成本（在得到明确授权后）。
