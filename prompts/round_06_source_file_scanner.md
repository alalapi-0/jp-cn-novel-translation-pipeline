# Round 06：原文导入与文件扫描最小实现

## Agent 身份

你是 Source File Scanner Implementation Agent。

## 本轮目标

实现最小文件扫描器，生成 manifest，不翻译。

## 必读文件

`README.md`、`docs/data_schema_plan.md`、`docs/directory_evolution_plan.md`、`docs/governance_rules.md`、`docs/roadmap_rounds_00_40.md`。

## 当前上下文

需要支持 `input_jp/` 和 `input_cn/`，扫描 `.txt` 和 `.md`，不修改原文。

## 允许修改

`src/`、`scripts/`、`tests/`、`workspace/manifests/` 的脱敏样例、相关 docs。

## 禁止修改

不读取完整真实正文用于报告，不调用 API，不修改原文，不提交真实 manifest 中的敏感长文本。

## 具体任务

1. 创建扫描器。
2. 支持两个输入目录。
3. 支持扩展名过滤。
4. 生成文件路径、大小、checksum、状态。
5. 增加测试样例。
6. 增加 CLI 草案或 dry-run。

## 验收标准

1. 能生成 manifest。
2. 不修改原文。
3. 支持 `JP_TO_CN` 和 `CN_TO_JP`。
4. 测试通过。
5. 输出不含正文长片段。

## 最终报告格式

说明实现、命令、测试、输出位置、安全检查、Git 状态。

## Git 提交建议

`feat: add source file scanner`
