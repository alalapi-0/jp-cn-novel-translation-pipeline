# workspace/review

这是 Git 追踪的兼容说明文件，不再承载本机审核报告。审核报告由
`scripts/review_workspace_storage.py` 经双 UUID 守卫解析到外置盘；外盘缺失或身份
不符时失败关闭，不得在本目录重建回退数据。

Round 49 CLI：

```bash
python3 scripts/run_quality_review.py --workspace
```

写入外置审核工作区的 `issue_report.json`。提交到 Git 的样例请使用
`data/examples/review_issue_report.example.json`。
