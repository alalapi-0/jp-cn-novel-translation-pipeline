# Round 09：术语候选抽取设计与离线规则

## Agent 身份

你是 Terminology Candidate Extraction Agent。

## 本轮目标

实现离线术语候选抽取，不调用 LLM。

## 必读文件

`README.md`、`docs/terminology_system_design.md`、`docs/shared_core_design.md`、`docs/data_schema_plan.md`、`docs/governance_rules.md`。

## 当前上下文

术语候选必须先进入 candidate，不能直接 approved。

## 允许修改

`src/`、`scripts/`、`tests/`、`data/schemas/`、相关 docs。

## 禁止修改

不调用 API，不自动确认术语，不改译文，不覆盖 locked 术语。

## 具体任务

1. 设计候选 schema。
2. 做频率统计。
3. 抽取日文片假名候选。
4. 抽取中文专名候选。
5. 抽取括号和标题词。
6. 输出 candidates 并测试。

## 验收标准

1. candidates 可导出。
2. 状态为 candidate。
3. 有章节和 segment 来源。
4. 支持双方向。
5. 测试通过。

## 最终报告格式

说明规则、输出、误报风险、测试和下一轮建议。

## Git 提交建议

`feat: add terminology candidate extraction`
