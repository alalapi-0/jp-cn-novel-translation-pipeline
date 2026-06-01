# Round 01：仓库结构标准化

## Agent 身份

你是 Repository Normalization Agent，负责轻量目录结构标准化。

## 本轮目标

补齐双向互译流水线所需目录和 README/.gitkeep，不写复杂代码。

## 必读文件

`README.md`、`docs/project_vision.md`、`docs/architecture_overview.md`、`docs/directory_evolution_plan.md`、`docs/governance_rules.md`、`docs/roadmap_rounds_00_40.md`。

## 当前上下文

仓库已有早期 `JP_TO_CN` 结构，需要加入 `CN_TO_JP` 和 shared/workspace/data/frontend/src/tests 基础目录。

## 允许修改

目录 README、`.gitkeep`、`.gitignore`、目录说明文档。

## 禁止修改

不得修改 `input_jp/` 正文、`output_cn/` 译文、`.env`、已有脚本逻辑。

## 具体任务

1. 创建 `input_cn/`。
2. 创建 `output_jp/translated/`、`bilingual/`、`review/`。
3. 创建 `shared/`、`directions/`、`workspace/`、`data/`、`src/`、`frontend/`、`tests/`。
4. 每个新增目录添加 README 或 `.gitkeep`。
5. 更新 `.gitignore`。
6. 运行目录检查。

## 验收标准

1. 新目录存在。
2. 占位文件存在。
3. `.gitignore` 保护输入输出和 workspace。
4. 未提交真实原文和译文。
5. Git 状态可说明。

## 最终报告格式

列出新增目录、`.gitignore` 变化、未做事项、验证结果、Git 状态。

## Git 提交建议

`docs: normalize bilingual pipeline repository structure`
