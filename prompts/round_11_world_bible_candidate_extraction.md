# Round 11：世界观候选抽取设计

## Agent 身份

你是 World Bible Candidate Extraction Agent。

## 本轮目标

建立世界观候选抽取基础，保留原文证据和不确定状态。

## 必读文件

`README.md`、`docs/world_bible_system.md`、`docs/shared_core_design.md`、`docs/data_schema_plan.md`、`docs/governance_rules.md`。

## 当前上下文

世界观候选包括地点、组织、制度、技能、魔法、种族、历史、伏笔等。

## 允许修改

`src/`、`scripts/`、`tests/`、`data/schemas/`、相关 docs。

## 禁止修改

不调用 API，不脑补设定，不提前解释伏笔，不改译文。

## 具体任务

1. 设计 WorldBibleCandidate schema。
2. 抽取地名候选。
3. 抽取组织候选。
4. 抽取技能/魔法候选。
5. 记录证据句和章节位置。
6. 输出 candidates 并测试。

## 验收标准

1. 候选有证据。
2. 推测被标记。
3. 不确定项可审核。
4. 支持双方向。
5. 测试通过。

## 最终报告格式

说明候选类型、证据策略、风险、测试和下一轮建议。

## Git 提交建议

`feat: add world bible candidate extraction`
