# Round 3 · Dashboard（轻小说翻译 Workbench）

> 设计参考文档（Stitch 占位）。实现见 `frontend/index.html`。

## 页面目标

主控制台：展示当前 API 模式、引导下一步操作、列出最近可见项目。

## 布局

| 区域 | 内容 |
|------|------|
| 顶栏 | 标题「轻小说翻译 Workbench」+ 四页导航 |
| 三列概览 | 当前模式 · 下一步 · 最近项目 |
| 主 CTA | 「创建 dry-run 项目」突出；真实 API 附禁用原因 |
| 折叠区 | 历史/测试项目（默认收起） |

## 模式徽章

- `mock / dry-run`：蓝灰 `badge-mock`
- `real_api`：紫蓝 `badge-real-api`
- 预算阻塞：黄色警示 + 复制修复命令

## 交互状态

- Key/预算缺失：真实 API 按钮 disabled + `real-api-disabled-reason` 文案
- 非法项目 ID：红色 `error-bar` + 字段高亮
- 空项目列表：引导创建 dry-run

## Stitch 生成提示（摘要）

参见 `PROMPT_TEMPLATES.md` → Dashboard 设计模板；Dark theme `#0f1419` / `#1a2332` / `#3d8bfd`。
