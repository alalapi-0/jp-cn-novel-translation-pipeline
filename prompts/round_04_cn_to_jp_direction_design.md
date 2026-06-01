# Round 04：CN_TO_JP 方向规则设计

## Agent 身份

你是 CN_TO_JP Direction Governance Agent。

## 本轮目标

设计中文到日文方向的专属规则和 Prompt 草案。

## 必读文件

`README.md`、`docs/shared_core_design.md`、`docs/architecture_overview.md`、`directions/cn_to_jp/README.md`、`docs/governance_rules.md`。

## 当前上下文

`CN_TO_JP` 需要重建敬语、第一人称、称呼、日文小说文体和自然表达。

## 允许修改

`directions/cn_to_jp/` 下规则和 Prompt 草案，相关 docs。

## 禁止修改

不修改 `JP_TO_CN` 规则，不翻译真实小说，不调用 API。

## 具体任务

1. 写中文姓名日文化规则。
2. 写称呼转敬称规则。
3. 写第一人称策略。
4. 写日文小说文体规则。
5. 写中文口语/网络语日文化规则。
6. 写初翻、润色、审核 Prompt 草案。

## 验收标准

1. 规则独立。
2. 敬语策略明确。
3. 第一人称策略明确。
4. Prompt 可后续实现。
5. 不污染 `JP_TO_CN`。

## 最终报告格式

说明新增规则、Prompt 草案、风险和下一轮建议。

## Git 提交建议

`docs: add cn to jp direction rules`
