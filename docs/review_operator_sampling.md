# Review 人工抽检操作说明 (AL-T04)

Operator runbook for `frontend/review.html` human sampling.

## 启动

```bash
npm run dev:frontend
# http://127.0.0.1:5174/review.html?project=demo-jp-cn
```

## 抽检步骤

1. 打开目标 `project` / `chapter` 参数
2. 对照原文/译文段落，标记可疑 segment
3. 确认 issue 列表与 segment 对齐（见 `issues.html`）
4. 不直接改 `human_edited` 字段除非明确授权
5. 记录结论到 `artifacts/`（不提交）

## 与质量审核关系

- 机器审核：`python3 scripts/run_quality_review.py`
- Issue 数据：`frontend/assets/review-issue-report.json` 或 API mock
- 流程：`docs/quality_review_workflow.md`
