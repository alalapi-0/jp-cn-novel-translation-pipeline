# Implementation Round Template

## Agent 身份

你是当前仓库的 Implementation Round Agent，负责小步实现路线图指定功能。

## 当前轮次

Round XX。

## 本轮类型

`implementation`

## 必读文档

- `README.md`
- `docs/project_vision.md`
- `docs/architecture_overview.md`
- `docs/roadmap_rounds_00_40.md`
- `docs/governance_rules.md`
- 本轮相关设计文档

## 本轮目标

实现路线图中明确限定的最小功能，并提供测试或 dry-run 验证。

## 允许修改范围

本轮指定的 `src/`、`scripts/`、`tests/`、`docs/`、`data/examples/`。不得修改真实原文或正式译文。

## 禁止事项

不调用真实 API，除非本轮明确授权；不提交 `.env`；不处理未授权真实正文；不覆盖已有输出；不越级实现后续轮次。

## 具体任务

1. 读取必读文档和相关代码。
2. 确认本轮输入输出。
3. 实现最小功能。
4. 增加测试或 dry-run。
5. 更新相关文档。
6. 检查 `.gitignore` 和敏感文件。

## 验收标准

1. 功能可运行。
2. 测试或 dry-run 通过。
3. 不破坏旧结构。
4. 不调用真实 API。
5. 输出路径安全。

## Git 提交要求

若是 Git 仓库，提交前检查 `git status`，确认无 `.env`、真实原文、真实译文。

## 最终报告格式

列出修改、验证命令、未做事项、风险、Git 状态和下一轮建议。
