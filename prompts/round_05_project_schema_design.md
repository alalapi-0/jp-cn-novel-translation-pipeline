# Round 05：项目配置与 Project Schema

## Agent 身份

你是 Project Schema Design Agent。

## 本轮目标

设计项目级配置和核心数据 schema，不实现数据库。

## 必读文件

`README.md`、`docs/data_schema_plan.md`、`docs/api_provider_strategy.md`、`docs/directory_evolution_plan.md`、`docs/governance_rules.md`。

## 当前上下文

后续需要 project config、direction config、source file、chapter、segment 和 project state。

## 允许修改

`docs/data_schema_plan.md`、`data/schemas/`、`data/examples/`、`.env.example` 如需变量名。

## 禁止修改

不写真实 API Key，不实现数据库，不迁移旧真实数据。

## 具体任务

1. 设计 `project.yaml`。
2. 设计 `direction_config.yaml`。
3. 设计 Project schema。
4. 设计 SourceFile/Chapter/Segment schema。
5. 设计 ProjectState schema。
6. 增加脱敏 example config。

## 验收标准

1. 支持单项目。
2. 支持多项目扩展。
3. 支持两个方向。
4. 示例无敏感信息。
5. 不绑定数据库。

## 最终报告格式

说明 schema、示例、兼容性、未做事项和下一轮建议。

## Git 提交建议

`docs: design project configuration schema`
