# Agent 治理规则

## 每轮必须读取

每轮 Agent 必须先读取：

- `governance/repo_protocol_standard.yaml`
- `project.yaml`
- `AGENTS.md`
- `README.md`
- `docs/project_vision.md`
- `docs/architecture_overview.md`
- `docs/roadmap_rounds_00_40.md`
- `docs/roadmap_rounds_41_50_tooling_and_workbench.md`（工具链轮次适用）
- `docs/governance_rules.md`
- `docs/repo_protocol_alignment.md`
- `docs/agent_operating_manual.md`
- `docs/current_repository_audit.md`

如果这些文件不存在，先创建或补齐。

## 每轮必须声明

每轮报告必须声明：

1. 当前轮次。
2. 本轮类型：
   - `governance`
   - `implementation`
   - `translation_execution`
   - `review`
   - `frontend`
   - `api_integration`
   - `tooling`
   - `protocol_alignment`
3. 本轮目标。
4. 本轮不做事项。
5. 修改范围。
6. 验收标准。
7. 下一轮建议。

## 禁止事项

1. 不得提交 `.env`。
2. 不得提交 API Key。
3. 不得提交真实小说原文。
4. 不得把真实译文默认提交到公开仓库。
5. 不得跳过路线图乱做。
6. 不得把日译中和中译日逻辑混在一起。
7. 不得复制两套相同 shared core。
8. 不得写死模型供应商。
9. 不得在治理轮中启动真实翻译。
10. 不得在没有用户授权的情况下公开发布译文。
11. 不得直接复制参考仓库代码；只能迁移工程方法、架构方法和质量控制方法。
12. 不得把校验失败的模型输出写入 `translated` 或 `final`。
13. 不得绕过 provider adapter 直接在业务流程调用模型。
14. 不得让 exporter 调用模型或修改原文。

## 提交规则

当**用户或当前轮 Prompt 明确要求**提交时，每轮结束应：

```bash
git status
git add .
git commit -m "docs: describe change"
```

`git push` 需用户明确授权（对齐通用协议 `approval_required`）。commit 前必须确认 diff 中无 `.env`、API Key、未授权原文/译文。

如果当前目录不是 Git 仓库，不得强行初始化 Git，应在报告中记录原因。如果 push 失败，记录原因，不反复尝试。

## 工具链规则

1. 治理轮不默认安装大型工具（Playwright、向量库、重型 MCP 等）。
2. 实现轮可以安装必要依赖，但必须写入文档说明原因。
3. 前端轮必须逐步引入 Playwright（Round 44 起搭框架，Round 46 起浏览器验证）。
4. MCP 接入必须先写安装和验证计划（见 `docs/mcp_playwright_setup_plan.md`）。
5. MCP 不可替代 Git 审查。
6. MCP 不可读取并输出敏感信息。
7. 真实 API 轮必须启用 dry-run 和 cost guard。
8. 向量库轮必须先有 metadata 和过滤设计（Round 48）。
9. Review Workbench 不能只看代码；Round 46 起必须浏览器验证。
10. 每个工具都必须有 fallback 或硬阻塞判断（见 `docs/agent_tooling_strategy.md`）。

## 通用协议规则

1. 每轮必须检查是否存在 `governance/repo_protocol_standard.yaml`。
2. 如果存在，必须读取并遵守；项目差异通过 `project.yaml` overrides 记录。
3. 如果协议与仓库规则冲突，必须记录于 `docs/repo_protocol_alignment.md`，不得静默覆盖。
4. 不得擅自修改协议本体；升级须备份并写迁移报告。
5. 协议对齐报告有变更时必须更新 `docs/repo_protocol_alignment.md`。
6. 后续 `scripts/agent_gate.py` 与 `scripts/check_protocol_standard.py` 应纳入协议检查（Round 41–42）。

## 参考方法吸收规则

1. RM 轮次表示 Reference Method Absorption，不覆盖既有 Round 00–50。
2. stable ID、JSONL 中间态、Prompt Version、ResponseExtractor、Validator、Provider Adapter 和 Exporter-only 是后续实现轮默认约束。
3. `JP_TO_CN` 与 `CN_TO_JP` 必须保持方向分离，共享逻辑进入 shared core。
4. Checkpoint、LLM Response Cache、Translation Memory 必须分开设计和实现。
5. Web Review Workbench、EPUB、OCR、漫画处理、多 provider routing、真实 embedding 属于后续扩展，不得提前塞入 MVP 主线。
