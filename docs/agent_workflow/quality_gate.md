# Quality Gate

## 目标

Quality Gate 用于判断一次生成、翻译、检查或页面展示是否足以进入后续流程。它不替代人工审校，但为 Runner、Browser Inspector、Bugfix 和 Quality Optimizer 提供统一触发规则。

## 通用质量判断

- 输出是否符合项目目标：中日文小说互译、可复查、可审核、可导出。
- 格式是否稳定：字段、JSONL、Markdown、HTML 或报告结构可被脚本重复解析。
- 是否能被后续流程消费：ResponseExtractor、Validator、review、exporter 或前端能读取。
- 是否保存到正确路径：运行产物进入 `.agent_runtime/*_reports/` 或 workspace，源代码变更进入对应目录。
- 是否有元数据：至少包含 provider/mode、created_at、input_reference、prompt_version 或等价字段。
- 是否能在页面中展示：工作台能加载，页面无白屏，无严重 console/network error。
- 是否能进入审核流：可定位到 chapter / paragraph / segment / issue，不丢失 stable ID。
- 是否脱敏：报告不包含完整 API Key、cookie、token、真实 API 返回全文或未经授权原文/译文。

## 文本 / 小说 / 翻译项目

- 是否保留术语：locked / approved 术语不得被随意改写。
- 是否格式一致：章节标题、段落、对白、标点和换行策略稳定。
- 是否章节完整：不得漏章、漏段、漏译或错配 segment。
- 是否能进入一致性校对或审核流程：翻译中间态、review issue、exporter 的输入输出边界清楚。
- 是否有明显幻觉或断裂：不得新增原文没有的信息、提前解释伏笔、混入无关剧情。
- 是否保留角色声音：人称、敬语、称呼关系和典型语气不应被统一成同一种声音。
- 是否保留 stable ID：`paragraph_id` / `segment_id` 不得在流程中丢失。

## 图片 / 游戏资产项目

- 是否风格一致：同一项目的画风、线条、光照和材质不能明显漂移。
- 是否角色一致：角色脸型、服装、配色、道具和剪影应可识别。
- 是否可作为游戏素材：尺寸、裁切、透明通道、边缘、姿势和状态适合引擎导入。
- 是否背景、尺寸、透明度符合要求：不能把不该透明的区域透明化，也不能保留脏边。
- 是否能进入审核和导出流程：资产元数据、预览图、版本和导出路径完整。

## 视频项目

- 是否镜头连续：动作、场景、角色位置和时间线不应无故跳变。
- 是否风格一致：画风、色彩、角色形象和字幕样式稳定。
- 是否有明显跳帧或崩坏：肢体、文字、脸部、物体连续性没有严重破损。
- 是否能保存、预览、审核：视频文件、缩略图、元数据和审核记录路径稳定。

## 触发规则

- 流程错误 → 入队 `bugfix`。
- 质量差 → 入队 `quality_optimization`。
- 页面显示问题 → 入队 `browser_inspection`；若根因明确为代码缺陷，再入队 `bugfix`。
- API 返回格式不稳定 → 同时入队 `bugfix` 与 `quality_optimization`。
- 无 API Key 但可 mock / dry-run → 不停止，记录 `missing_api_key` 或 `dry_run`。
- 无 API Key 且当前轮唯一目标必须真实调用 API → `python3 scripts/agent.py block --reason "missing_required_api_key"`。
- 真实 API 成功但无法展示 → 先 `browser_inspection`，再视根因进入 `bugfix`。
- 真实 API 成功但内容不合格 → `quality_optimization`，并重新运行小规模测试。

## 报告要求

- 报告只保存摘要，不保存完整 API 返回全文。
- 报告必须包含 `created_at`。
- 失败报告必须包含可执行的 `error_summary` 或 `suggested_next_action`。
- 浏览器报告进入 `.agent_runtime/inspection_reports/`。
- 真实 API 报告进入 `.agent_runtime/real_api_reports/`。
- 质量报告进入 `.agent_runtime/quality_reports/`。
- 修复报告进入 `.agent_runtime/fix_reports/`。

## 验收标准

- 任一 Agent 能根据本文件决定 bugfix、quality optimization、browser inspection 或 hard block。
- 质量判断不依赖真实 API Key 是否存在。
- mock/dry-run 不伪装成真实 API。
- 低质量输出不会进入 final / translated。
- 页面可见性和流程可消费性都被纳入质量判断。
