# Stitch Prompt 模板

复制下列模板到 Stitch（或 Stitch MCP 的 `generate_screen_from_text`），替换 `{{...}}` 占位符。生成前请阅读 `UI_TASKS.md` 对应章节。

**通用要求（每条模板已隐含，追加时勿删）**：

1. 明确页面目标与服务真实翻译审核流程  
2. 中文 UI 文案  
3. Dark theme：`#0f1419` 背景、`#1a2332` 面板、`#3d8bfd` 强调色  
4. 不要营销页、不要无关插画英雄区  
5. 须体现 `REAL_API` / `MOCK` / `DRY_RUN` 状态区域  
6. Desktop 优先，信息密度高，适合长时间审核工作  

---

## Dashboard 设计模板

```text
设计一个「中日文小说互译生产流水线」主控制台 Dashboard（Desktop）。

项目类型：长篇小说/轻小说互译治理仓库，非营销网站。
目标用户：译者、项目管理员。
布局：顶栏（项目名 + 方向 JP_TO_CN/CN_TO_JP）+ 左侧导航（首页、审核台、导出、设置）+ 主区域网格。

核心组件：
1. API 状态卡片：Key 是否已配置（脱敏）、REAL_API 是否可用、成本护栏 MAX_TEST_COST_USD 状态。
2. 最近任务表：run_id、阶段（初翻/润色）、provider、状态、时间。
3. 失败任务告警区：脱敏错误码与重试按钮。
4. 快捷入口：「进入审核台」「导出已批准章节」。
5. 模式徽章：REAL_API / MOCK / DRY_RUN 三色区分。

交互状态：加载中骨架屏、无任务空状态、API 不可用禁用真实生成按钮。
视觉：Dark theme，克制专业，无大图 banner。
文案语言：简体中文。
不要：落地页、定价、社交媒体元素。
```

---

## Review Workbench 设计模板

```text
设计「翻译审核工作台 Review Workbench」页面（Desktop）。

项目：中日文小说 segment 级人工审核，对照原文与译文。
目标用户：审核员、译者。
布局：顶栏筛选（待审/已通过/已驳回）+ 左 segment 列表 + 中间双栏对照（原文|译文）+ 右侧元数据与操作。

核心组件：
1. Segment 列表项：segment_id、章节名、状态色点、real_api/mock 小标签。
2. 双栏阅读区：等宽字体可选、段落对齐、长度比例提示占位。
3. 操作：通过、驳回、添加备注；禁止误导性「一键全部通过」。
4. 元数据：run_id、provider、prompt_version、文件路径（脱敏）。
5. Quality issue 折叠面板：显示 issue 类型与严重度。

状态：空列表、loading、validation_failed 高亮、fixture 数据源警告条。
Dark theme，高对比，适合长时间阅读。
中文 UI。不要营销内容。
```

---

## Visual Review 设计模板（扩展 · 插图审核）

```text
设计「视觉结果审核台」用于小说章节插图/封面审核（Desktop）。

项目类型：翻译流水线附属视觉资产审核，仍属生产工具非展示站。
布局：顶栏筛选 + 主区缩略图 grid + 右侧详情抽屉。

核心组件：
1. 图片 grid：缩略图、状态角标（待审/通过/驳回）。
2. 详情：大图预览、关联章节、prompt 摘要（脱敏）、生成参数只读。
3. 质量区：评分滑块占位、一致性检查列表、失败重试。
4. 操作：通过、驳回、重新生成（需二次确认）。
5. 模式标记：REAL_API vs MOCK。

Dark theme，中文 UI。不要游戏商城风格促销元素。
```

---

## Game Asset Gallery 设计模板（扩展）

```text
设计「游戏资产 Gallery」管理页（Desktop），用于查看角色立绘与 sprite sheet（扩展场景，默认低优先级）。

布局：左侧资产树（角色/动画/UI）+ 主预览区 + 底部属性检查栏。

核心组件：
1. 角色图与 sprite sheet 预览，棋盘格透明背景。
2. 动画帧时间轴条，帧号与尺寸标注。
3. 检查项：透明背景、尺寸、帧对齐、导出格式。
4. 导出按钮与批量选择。

Dark theme，工具型 UI，中文标签。不要 RPG 商城界面。
```

---

## Video Preview Workbench 设计模板（扩展）

```text
设计「视频生成 Workbench」页面（Desktop，扩展场景）。

布局：左输入（参考图+prompt）+ 中视频播放器 + 右镜头/抽帧列表。

核心组件：
1. 图片输入预览与文字 prompt 区。
2. 生成进度与状态（排队/渲染/失败）。
3. 视频播放器与控制条。
4. 抽帧缩略图 strip，镜头列表可单镜头重生成。
5. REAL_API 成本与模式徽章。

Dark theme，中文 UI，生产工具风格。
```

---

## Debug Panel 设计模板

```text
设计「Debug / Observability」面板（Desktop），服务翻译流水线运维与 Agent 自检。

布局：顶栏全局 health + 两列卡片网格 + 底部日志 tail。

核心组件：
1. Health：Workbench API、MCP（playwright/stitch）状态灯。
2. 任务队列：bugfix / browser_inspection / quality_optimization 列表。
3. Checkpoint / run 文件状态表。
4. 吞吐量简图占位（segments/hour）。
5. 最近日志（脱敏，无 API Key）。

状态：全部正常、部分降级、硬阻塞红色横幅。
Dark theme，等宽字体日志区，中文标签。
不要：花哨图表动画、无关业务 KPI。
```

---

## Mobile Responsive 设计模板

```text
设计上述「审核台 Review Workbench」的 Mobile 响应式变体（手机竖屏）。

约束：主流程仍为「查看 segment + 通过/驳回」，可牺牲次要元数据到折叠面板。
布局：顶栏 + 可滑动 segment 卡片 + 堆叠原文/译文 + 底部固定操作栏。

核心组件：
1. 大号通过/驳回按钮，拇指可达。
2. 模式徽章与数据源警告仍可见。
3. 列表与详情间清晰返回。

Dark theme，中文 UI。不要隐藏 REAL_API 风险提示。
设备：MOBILE，375px 宽参考。
```

---

## 使用记录

每次使用请将填好占位符的 prompt 存入：

`docs/design/stitch/prompts/{date}_{page-slug}_prompt.md`
