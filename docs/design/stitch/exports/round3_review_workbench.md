# Round 3 · Review Workbench（对照审核）

> 设计参考文档（Stitch 占位）。实现见 `frontend/review.html`。

## 三栏布局

```
┌─────────────┬──────────────────────┬──────────────┐
│ 段落队列    │ 对照阅读（原文|译文） │ 状态与操作   │
│ segment 列表│ 舒适行宽 1.65 行高   │ 元数据+按钮  │
└─────────────┴──────────────────────┴──────────────┘
```

## 组件

1. **左栏队列**：segment_id、状态徽章（待审核/已通过/已驳回）、open issue 计数
2. **中栏阅读**：双栏对照，max-width ~42rem，mock/real_api 标签
3. **右栏操作**：通过、驳回；AUTO_APPROVE 关闭时隐藏「触发自动通过」

## 移动端（≤390px）

- 三栏纵向堆叠
- 底部 sticky `review-mobile-actions`：通过 / 驳回

## 状态色

沿用 `styles.css`：`badge-warning` / `badge-success` / `badge-danger` / `badge-mock` / `badge-real-api`
