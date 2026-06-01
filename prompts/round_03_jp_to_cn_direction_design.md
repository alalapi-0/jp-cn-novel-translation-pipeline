# Round 03：JP_TO_CN 方向规则设计

## Agent 身份

你是 JP_TO_CN Direction Governance Agent。

## 本轮目标

设计日文到中文方向的专属规则和 Prompt 草案。

## 必读文件

`README.md`、`docs/shared_core_design.md`、`docs/architecture_overview.md`、`directions/jp_to_cn/README.md`、`docs/governance_rules.md`。

## 当前上下文

`JP_TO_CN` 需要处理日文敬称、省略主语、片假名、汉字名、拟声词和中文自然化。

## 允许修改

`directions/jp_to_cn/` 下规则和 Prompt 草案，相关 docs。

## 禁止修改

不修改 `directions/cn_to_jp/`，不翻译真实章节，不调用 API。

## 具体任务

1. 写敬称规则。
2. 写姓名规则。
3. 写片假名术语规则。
4. 写省略主语规则。
5. 写轻小说中文风格规则。
6. 写初翻、润色、审核 Prompt 草案。

## 验收标准

1. 规则独立。
2. Prompt 不写死模型。
3. 中文风格目标清晰。
4. 能接 context pack。
5. 不污染 shared core。

## 最终报告格式

说明新增规则、Prompt 草案、风险和下一轮建议。

## Git 提交建议

`docs: add jp to cn direction rules`
