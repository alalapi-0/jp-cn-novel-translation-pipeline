# Round 10：角色候选抽取设计

## Agent 身份

你是 Character Candidate Extraction Agent。

## 本轮目标

建立角色候选抽取基础，不自动确认角色设定。

## 必读文件

`README.md`、`docs/character_profile_system.md`、`docs/shared_core_design.md`、`docs/data_schema_plan.md`、`docs/governance_rules.md`。

## 当前上下文

角色候选来自姓名模式、对话、称呼、敬称和首次出现位置。

## 允许修改

`src/`、`scripts/`、`tests/`、`data/schemas/`、相关 docs。

## 禁止修改

不调用 API，不自动写入 approved 角色，不生成百科，不改译文。

## 具体任务

1. 设计 CharacterCandidate schema。
2. 抽取姓名模式。
3. 抽取称呼和敬称线索。
4. 记录首次出现。
5. 支持别名字段。
6. 输出 candidates 并测试。

## 验收标准

1. 能生成角色候选。
2. 记录首次出现。
3. 记录别名。
4. 不强行确认。
5. 测试通过。

## 最终报告格式

说明候选来源、输出、局限、测试和下一轮建议。

## Git 提交建议

`feat: add character candidate extraction`
