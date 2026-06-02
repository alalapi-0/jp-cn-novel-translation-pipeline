# Round RM-01：参考仓库方法迁移总览

## Agent 身份

你是当前仓库的参考仓库方法吸收推进 Agent。本轮只执行 RM-01，不得越级到其他 RM 轮次。

## 本轮类型

governance

## 参考来源

AiNiee, GalTransl, TBL, SakuraLLM, LiteraryTranslation, oomol

## 必读文件

- `governance/repo_protocol_standard.yaml`
- `project.yaml`
- `AGENTS.md`
- `README.md`
- `docs/reference_repo_methodology_integration.md`
- `docs/current_project_method_stack.md`
- `docs/reference_inspired_pipeline_design.md`
- `docs/roadmap_rounds_reference_method_01_40.md`
- `docs/governance_rules.md`
- `docs/agent_operating_manual.md`

## 本轮目标

将参考仓库分析整理为当前项目自己的方法迁移总纲。

## 允许修改

- 与本轮目标直接相关的 `docs/` 文档。
- 与本轮目标直接相关的 `data/` schema 或 sample。
- 与本轮目标直接相关的 `src/`、`tests/` 文件（仅 implementation 轮）。
- `governance/round_state.yaml` 和必要的本轮报告。

## 禁止事项

- 不读取、修改或提交 `.env`。
- 不处理真实版权长篇原文。
- 不提交真实原文或真实译文。
- 不调用真实 API，除非本轮明确是受控 API 轮且用户授权。
- 不生成真实 embedding 或真实向量库。
- 不复制参考仓库代码。
- 不把 `JP_TO_CN` 与 `CN_TO_JP` 方向逻辑混在一起。

## 具体任务

1. 创建参考方法总纲。
2. 归纳 P0/P1/P2 方法。
3. 标记不迁移内容。
4. 映射到当前项目模块。
5. 更新 README。
6. 更新治理规则。
7. 说明只迁移方法不复制代码。

## 验收标准

1. 本轮产物存在且路径清晰。
2. stable ID、JSONL 中间态、Validator 或 exporter-only 等相关原则未被破坏。
3. `JP_TO_CN` 与 `CN_TO_JP` 方向保持分离。
4. 没有真实翻译、真实 API、真实 embedding 或真实向量库。
5. 文档或测试能被后续 RM 轮次直接引用。

## 测试要求

- governance / schema design 轮至少执行文档自检和 `git status`。
- implementation 轮必须增加或更新聚焦测试；若测试基础设施不存在，先创建最小测试并说明范围。
- fake provider / dry-run 优先，真实 provider 禁止默认使用。

## 安全要求

- 确认 `.env` 未进入 Git diff。
- 确认 `input_jp/`、`input_cn/`、`output_cn/`、`output_jp/` 中真实内容未被提交。
- 报告中不得粘贴真实原文、真实译文、API key 或敏感请求头。

## Git 提交建议

建议提交信息：`docs: complete rm-01 参考仓库方法迁移总览`。只有用户或当前轮 Prompt 明确要求时才 commit；push 需用户授权。

## 最终报告格式

# RM-01 Report
## 本轮定位
## 完成内容
## 修改文件
## 测试与检查
## 安全自检
## 未做事项
## 软阻塞
## 硬阻塞
## 下一轮建议
