# Round 02：共享核心模块文档落地

## Agent 身份

你是 Shared Core Governance Agent。

## 本轮目标

细化 shared core 与方向专属模块边界，为后续实现提供决策完整的设计。

## 必读文件

`README.md`、`docs/shared_core_design.md`、`docs/architecture_overview.md`、`docs/roadmap_rounds_00_40.md`、`docs/governance_rules.md`。

## 当前上下文

项目将支持 `JP_TO_CN` 和 `CN_TO_JP`，需要防止重复实现扫描、解析、术语、角色、世界观、embedding 和 provider。

## 允许修改

`docs/shared_core_design.md`、`shared/README.md`、相关治理文档。

## 禁止修改

不写代码，不创建复杂包结构，不移动旧 notes，不调用 API。

## 具体任务

1. 扩写 file scanner 边界。
2. 扩写 chapter parser 边界。
3. 扩写 glossary、character、world bible 边界。
4. 扩写 embedding、vector store、provider 边界。
5. 明确 direction 模块只维护规则和 Prompt。
6. 写清依赖和后续轮次。

## 验收标准

1. shared core 职责清晰。
2. direction 职责清晰。
3. 不建议重复实现。
4. 后续 Round 03/04 可引用。
5. 文档无真实正文。

## 最终报告格式

说明更新模块、关键边界、未解决问题、下一轮建议。

## Git 提交建议

`docs: refine shared core module boundaries`
