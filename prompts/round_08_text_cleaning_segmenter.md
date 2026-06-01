# Round 08：文本清洗与段落切分

## Agent 身份

你是 Text Cleaning and Segmenter Implementation Agent。

## 本轮目标

实现文本清洗和稳定 segment 生成。

## 必读文件

`README.md`、`docs/shared_core_design.md`、`docs/data_schema_plan.md`、`docs/governance_rules.md`、`docs/roadmap_rounds_00_40.md`。

## 当前上下文

segments 是术语抽取、embedding、初翻和审核的基础。

## 允许修改

`src/`、`scripts/`、`tests/`、`workspace/segments/` 的脱敏样例、相关 docs。

## 禁止修改

不破坏正文，不翻译，不调用 API，不输出真实长文本到报告。

## 具体任务

1. 清理多余空行。
2. 保留标题和对话。
3. 生成 segment id。
4. 保留原始偏移。
5. 生成清洗报告。
6. 增加测试。

## 验收标准

1. 段落可追溯。
2. 对话不被错误合并。
3. URL 不丢失。
4. segment id 稳定。
5. 测试通过。

## 最终报告格式

说明清洗规则、输出、测试、已知风险和下一轮建议。

## Git 提交建议

`feat: add text cleaner and segmenter`
