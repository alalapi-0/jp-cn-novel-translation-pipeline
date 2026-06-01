# Round 07：章节解析与排序

## Agent 身份

你是 Chapter Parser Implementation Agent。

## 本轮目标

实现章节标题识别、排序和异常报告。

## 必读文件

`README.md`、`docs/data_schema_plan.md`、`docs/shared_core_design.md`、`docs/governance_rules.md`、`docs/roadmap_rounds_00_40.md`。

## 当前上下文

章节解析必须支持序章、正文章、番外、后记和卷标题。

## 允许修改

`src/`、`scripts/`、`tests/`、`workspace/parsed/` 的脱敏样例、相关 docs。

## 禁止修改

不翻译，不改原文，不调用 API，不覆盖已有输出。

## 具体任务

1. 识别章节类型。
2. 支持文件名排序。
3. 支持标题排序。
4. 生成 chapters metadata。
5. 报告缺失、重复、异常标题。
6. 增加测试。

## 验收标准

1. 章节顺序稳定。
2. 特殊章节可标记。
3. 异常可报告。
4. 测试通过。
5. 不启动翻译。

## 最终报告格式

说明解析规则、输出、测试、风险和下一轮建议。

## Git 提交建议

`feat: add chapter parser`
