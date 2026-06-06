# Stitch 设计任务模板（light-novel 互译流水线）

面向 **中日文小说互译生产流水线** 与 **Review Workbench** 的页面设计任务。Agent 在调用 Stitch 前应先填「任务卡」，再选用 `PROMPT_TEMPLATES.md` 中对应模板。

**全局约束**：Dark theme；中文 UI；效率优先于炫酷；须区分 `real_api` / `mock` / `dry-run`；不设计营销落地页。

---

## 1. 主控制台 Dashboard

**页面 ID**：`dashboard`  
**对应文件**：`frontend/index.html`

### 目标

- 展示项目状态与最近翻译/润色任务
- 展示 real API / mock / dry-run 模式与 Key 配置状态（脱敏）
- 展示最近产物（run、segment 摘要，无完整原文）
- 展示失败任务与重试入口
- 提供进入审核台、导出页的入口

### 核心组件

| 组件 | 说明 |
|------|------|
| 项目状态卡片 | 方向 `JP_TO_CN` / `CN_TO_JP`、Round、pipeline 阶段 |
| API 状态条 | Key 已配置 / Workbench 真实 API 可调用 / 成本护栏 |
| 任务列表 | 最近 ModelRun：状态、provider、时间 |
| 失败告警 | 脱敏错误码、可行动提示 |
| 快捷导航 | 审核台、导出、质量 Issue（若有） |

### 数据与交互

- 读取：Workbench API `/api/status` 类端点（见 `src/workbench/api_status.py`）
- 写入：以跳转为主
- 状态：loading、空项目、API 不可用、成本护栏阻断

### Stitch 交付物

- `exports/*_dashboard_*.html`
- `screenshots/*_dashboard_*.png`
- `reviews/*_dashboard_*.md`

---

## 2. 真实 API 生成任务页

**页面 ID**：`real-api-generate`  
**对应文件**：`frontend/index.html`（生成面板区域）或独立子视图

### 目标

- 输入 prompt / 章节选择
- 选择模型 / provider（经 Model Router）
- 配置参数（max_tokens、profile）
- 显示生成状态与进度
- 显示脱敏错误与重试
- 显示生成结果摘要；支持保存与重试

### 核心组件

| 组件 | 说明 |
|------|------|
| Prompt 输入区 | 多行文本 + 章节/segment 选择 |
| Provider 选择 | dry-run / real；显示当前 profile |
| 参数面板 | max_tokens、成本估算只读 |
| 状态时间线 | queued → running → success / failed |
| 结果预览 | 截断译文预览，链接到审核台 |
| 模式徽章 | `REAL_API` / `MOCK` / `DRY_RUN` 必须醒目 |

### 约束

- `MAX_TEST_COST_USD=0` 时 real 按钮 disabled 须在 UI 体现
- 不得展示完整 API Key 或完整真实 API 响应正文

---

## 3. 审核台 Review Workbench

**页面 ID**：`review-workbench`  
**对应文件**：`frontend/review.html`

### 目标

- 对照原文/译文 segment
- 预览生成结果
- 通过 / 驳回 / 待审（`review_state`）
- 显示 real_api / mock / dry-run 标记
- 显示文件路径与 run 元数据（脱敏）
- 显示日志摘要与 quality issue

### 核心组件

| 组件 | 说明 |
|------|------|
| Segment 列表 | stable ID、状态色、筛选 |
| 双栏对照 | 原文 | 译文；支持润色前后对比（规划） |
| 操作栏 | 通过、驳回、备注 |
| 元数据侧栏 | run_id、provider、prompt_version |
| 模式与数据源标记 | fixture fallback 须可见 |
| 术语/质量提示 | 链到 quality-review（若有） |

### 交互状态

- 无 segment、全部已审、存在 validation_failed
- `AUTO_APPROVE=false` 默认：无自动通过按钮误导

---

## 4. Debug / Observability 页面

**页面 ID**：`debug-panel`  
**对应文件**：规划视图（可参考 Workbench API + `.agent_runtime/`）

### 目标

- API health 与 MCP 检查摘要
- Console / network 错误摘要占位（对接浏览器检查报告）
- 任务队列（`.agent_runtime/queue.jsonl` 可视化概念）
- 文件/checkpoint 状态
- 最近操作日志（脱敏）

### 核心组件

| 组件 | 说明 |
|------|------|
| Health 卡片 | API、MCP stitch/playwright 状态 |
| 队列视图 | bugfix / browser_inspection / quality_optimization |
| Checkpoint 列表 | run 恢复点 |
| 日志流 | 尾部 N 行，无密钥 |
| 吞吐量指标 | 链接 `docs/throughput_metrics_summary.md` 概念 |

---

## 5. 导出工作台 Export

**页面 ID**：`export-workbench`  
**对应文件**：`frontend/export.html`

### 目标

- 选择导出模式：`approved` / `draft`
- 预览将导出的章节范围
- 合并审核状态提示
- 导出进度与错误
- 下载链接（本地路径提示，非公网）

*注：本项目为文本翻译流水线，非图片/视频主场景；§5–7 视觉类模板保留供扩展（封面、插图审核等）。*

---

## 6. 术语与角色审核视图（扩展）

**页面 ID**：`glossary-review`

### 目标

- 术语表：source / target / locked / candidate
- 角色表：称呼、语气、第一人称
- 冲突标记与人工确认流

见 `docs/frontend_workbench_plan.md` 中 Terminology Review、Character Review 章节。

---

## 7. 视觉结果审核台（扩展 · 插图/封面）

**页面 ID**：`visual-review`  
**适用**：若未来增加书籍封面、章节插图资产

### 目标

- 缩略图 grid
- prompt 摘要（脱敏）
- 质量评分与一致性检查占位
- 通过 / 驳回 / 重新生成
- 与正文翻译任务分离标记

---

## 8. 游戏资产 Gallery（扩展 · 不适用主路径）

**页面 ID**：`game-asset-gallery`  
**适用**：仅当项目扩展至游戏化资产；默认 **跳过**，除非 Round 明确要求。

### 目标

- 角色立绘、sprite sheet、动画帧预览
- 透明背景 / 尺寸 / 帧对齐检查
- 导出游戏资产包

---

## 9. 视频生成 Workbench（扩展 · 不适用主路径）

**页面 ID**：`video-preview`  
**适用**：仅当项目扩展至视频衍生内容；默认 **跳过**。

### 目标

- 图片输入 + 文字 prompt
- 生成状态、视频结果、抽帧、镜头列表
- 单镜头重生成

---

## 任务卡模板（复制使用）

```markdown
## 设计任务卡

- 日期：
- 页面 ID：
- 负责人 Agent：
- 目标用户：译者 / 审核员 / 运维
- 必读：frontend_workbench_plan §...
- 成功标准：Stitch 原型 + review 文档 + 实现 PR 浏览器通过
- 不在范围：
- Stitch project 名：
- 输出路径：docs/design/stitch/exports/...
```
