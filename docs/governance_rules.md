# Agent 治理规则

## 每轮必须读取

每轮 Agent 必须先读取：

- `README.md`
- `docs/project_vision.md`
- `docs/architecture_overview.md`
- `docs/roadmap_rounds_00_40.md`
- `docs/governance_rules.md`
- `docs/current_repository_audit.md`

如果这些文件不存在，先创建或补齐。

## 每轮必须声明

每轮报告必须声明：

1. 当前轮次。
2. 本轮类型：
   - `governance`
   - `implementation`
   - `translation_execution`
   - `review`
   - `frontend`
   - `api_integration`
3. 本轮目标。
4. 本轮不做事项。
5. 修改范围。
6. 验收标准。
7. 下一轮建议。

## 禁止事项

1. 不得提交 `.env`。
2. 不得提交 API Key。
3. 不得提交真实小说原文。
4. 不得把真实译文默认提交到公开仓库。
5. 不得跳过路线图乱做。
6. 不得把日译中和中译日逻辑混在一起。
7. 不得复制两套相同 shared core。
8. 不得写死模型供应商。
9. 不得在治理轮中启动真实翻译。
10. 不得在没有用户授权的情况下公开发布译文。

## 提交规则

每轮结束应：

```bash
git status
git add .
git commit -m "docs: describe change"
git push
```

如果当前目录不是 Git 仓库，不得强行初始化 Git，应在报告中记录原因。如果 push 失败，记录原因，不反复尝试。
