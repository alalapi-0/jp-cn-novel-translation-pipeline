# Round 3 · Export Success（导出成功卡片）

> 设计参考文档（Stitch 占位）。实现见 `frontend/export.html` → `#export-success-card`。

## 结构（非密集日志段落）

1. **成功徽章**：`导出成功`（绿）或 `导出跳过`（黄）
2. **导出计数**：`已导出 N / 共 M 段 · 模式 approved`
3. **跳过统计**：`待审核(pending):1` 等中文标签
4. **文件列表**：每行路径 +「复制路径」按钮

## 空状态

- `#export-session-empty`：「尚无本次导出」
- 导出完成后隐藏空状态、显示成功卡片

## 历史区

- `details` 折叠历史文件列表，与「本次导出」分离
