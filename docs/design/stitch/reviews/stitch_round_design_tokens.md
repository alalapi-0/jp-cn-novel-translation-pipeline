# Stitch Round 设计 Token（fallback）

本文件记录本轮手工设计依据。未写入任何真实 API Key。

## 色彩

| Token | 值 | 用途 |
|---|---:|---|
| `--bg` | `#0f1419` | 页面背景 |
| `--panel` | `#1a2332` | 卡片 / 面板 |
| `--text` | `#e7ecf3` | 主文本 |
| `--muted` | `#8b9bb4` | 次级说明 |
| `--accent` | `#3d8bfd` | 焦点、链接、主要操作 |
| `--ok` | `#3dd68c` | 已通过 |
| `--warn` | `#f5a524` | 待审核 / 警告 |
| `--danger` | `#f2555a` | 驳回 / 危险操作 |
| `--mock` | `#6b7d99` | mock 标记 |
| `--real-api` | `#7c6cf0` | 真实 API 标记 |

## 布局

- Desktop：审核台三栏，队列 `180-220px`、阅读区自适应、元数据 `200-260px`。
- Tablet / Mobile：900px 以下堆叠单栏；390px 以下显示 sticky 底部操作栏。
- 阅读区：原文 / 译文双栏，移动端堆叠。

## 交互组件

- Segment item：按钮化列表项，`is-active` 显示当前段。
- Status badge：`pending` / `approved` / `rejected` 使用 warning / success / danger 映射。
- Shortcut key：使用 `kbd` 小胶囊，保持高对比和可扫描。
- Focus：按钮、链接、输入框、select 使用 `--accent` 外描边。

## 可访问性约束

- 快捷键说明必须可见，不能只依赖隐藏文档。
- 全局快捷键不得拦截 input / textarea / select。
- 焦点移动到当前 segment 时保留滚动定位。
- 操作仍保留按钮点击路径，快捷键只是增强。
