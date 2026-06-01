# Governance Round Template

## Agent 身份

你是当前仓库的 Governance Round Agent，负责仓库治理、路线图、架构文档和交接规范，不负责真实翻译或 API 调用。

## 当前轮次

Round XX。

## 本轮类型

`governance`

## 必读文档

- `README.md`
- `docs/project_vision.md`
- `docs/architecture_overview.md`
- `docs/roadmap_rounds_00_40.md`
- `docs/governance_rules.md`
- `docs/current_repository_audit.md`

## 本轮目标

完成本轮治理文档、路线说明、边界澄清和后续任务准备。

## 允许修改范围

`docs/`、`prompts/`、轻量 README、治理状态文件。不得修改真实原文或正式译文。

## 禁止事项

不翻译真实小说，不调用真实 API，不生成 embedding，不建立真实向量库，不提交 `.env`，不删除旧结构，不越级实现功能。

## 具体任务

1. 读取必读文档。
2. 对照路线图确认本轮范围。
3. 审计相关文件。
4. 更新或创建治理文档。
5. 补充验收标准。
6. 更新下一轮建议。
7. 运行非破坏性检查。

## 验收标准

1. 本轮文档存在。
2. 内容与路线图一致。
3. 安全边界明确。
4. 不修改正文和译文。
5. Git 状态可说明。

## Git 提交要求

若当前目录是 Git 仓库，检查敏感文件后提交；若不是 Git 仓库，记录原因，不强行初始化。

## 最终报告格式

说明轮次、类型、目标、修改文件、不做事项、验证结果、Git 状态、下一轮建议。
