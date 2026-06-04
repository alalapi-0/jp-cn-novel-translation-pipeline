# Quality Optimizer Agent

## 角色职责

Quality Optimizer Agent 在真实 API 调用成功但输出质量不达标时触发。它优化 prompt、参数、解析、保存、后处理和审核标准，每次只做小步可验证改动。

## 输入文件

- `.agent_runtime/queue.jsonl`
- `.agent_runtime/real_api_reports/`
- `.agent_runtime/quality_reports/`
- `docs/agent_workflow/quality_gate.md`
- Prompt 模板
- provider 参数配置
- Validator / ResponseExtractor / exporter 相关代码

## 输出文件

- 更新后的 prompt、参数或质量检查逻辑
- `.agent_runtime/quality_reports/`
- 必要时追加 `real_api_smoke`、`browser_inspection` 或 `bugfix` 任务

## 可使用工具

- `python scripts/agent.py enqueue --type quality_optimization --reason ...`
- `python scripts/run_real_api_smoke.py`
- 项目现有质量检查脚本
- 相关单元测试
- 后续 Cursor MCP 页面验证

## 触发条件

- 真实 API smoke 成功但结果格式不稳定。
- 输出无法被后续流程消费。
- 术语、人名、章节结构、角色语气或格式不符合质量门。
- 页面能展示结果，但质量不适合进入审核流。

## 停止条件

- 缺少真实 API Key 且无法用 dry-run/mock 验证改动方向。
- 质量判断需要用户阅读真实版权正文后裁决。
- 优化会改变大量业务行为，超出小步验证范围。

## 禁止事项

- 不一次性重写整套 prompt 体系。
- 不把低质量结果标记为通过。
- 不隐藏模型幻觉、漏译、格式断裂或解析失败。
- 不提交真实 API 返回全文。
- 不把 quality optimization 当作 bugfix 混合提交，除非根因同时涉及流程 bug。

## 验收标准

- 每次优化有明确原因和验收指标。
- 改动范围小且可回滚。
- 重新运行小规模 smoke 或相关质量检查。
- 结果能被后续流程消费、保存、展示并进入审核。
- 若仍不达标，继续入队 `quality_optimization` 或标记 hard block 原因。
