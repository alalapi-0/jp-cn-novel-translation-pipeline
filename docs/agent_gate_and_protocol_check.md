# Agent Gate and Protocol Check

未来统一检查入口：`python3 scripts/agent_gate.py`（Round 41 实现 MVP）。

---

## 6.1 agent_gate 的目标

1. 检查仓库结构
2. 检查必读文档是否存在
3. 检查 `.env` 是否被 Git 跟踪
4. 检查真实原文是否可能被提交
5. 检查真实译文是否可能被提交
6. 检查路线图是否存在
7. 检查通用协议文件是否存在
8. 检查协议对齐文档是否存在
9. 检查当前轮报告是否存在（若适用）
10. 检查 Git 状态

**原则：** 确定性脚本，不调用 LLM。exit code 对齐协议 `automation_policy`：

| Code | 含义 |
|------|------|
| 0 | PASS — 可继续自主推进（在 allowed_actions 内） |
| 1 | WARNING — 可继续做低风险治理任务，须记录警告 |
| 2 | BLOCKED — 仅输出报告，请求人工确认 |

报告输出：`docs/reports/agent_gate_report.md`（本地，默认 gitignore）。

---

## 6.2 agent_gate 未来检查项

规划检查项 ID（Round 41 起逐步实现）：

| ID | 检查内容 |
|----|----------|
| `docs_exist` | README、AGENTS、project.yaml、核心 docs |
| `roadmap_exists` | roadmap 00–40 与 41–50 |
| `protocol_exists` | governance/repo_protocol_standard.yaml 完整 |
| `protocol_alignment_exists` | docs/repo_protocol_alignment.md |
| `gitignore_safe` | .env、input/output 规则 |
| `env_not_tracked` | git ls-files 不含 .env |
| `input_sources_ignored` | input_jp/cn 忽略策略 |
| `outputs_ignored` | output 译文目录忽略 |
| `prompt_templates_exist` | 6+ 工具链模板 |
| `direction_dirs_exist` | directions/jp_to_cn、cn_to_jp |
| `shared_core_docs_exist` | shared_core_design 等 |
| `frontend_plan_exists` | frontend_workbench_plan |
| `api_provider_strategy_exists` | api_provider_strategy |
| `tooling_strategy_exists` | agent_tooling_strategy |
| `mcp_plan_exists` | mcp_playwright_setup_plan |

**Protocol Checker（Round 42）：** `scripts/check_protocol_standard.py` — 读取协议与 project.yaml，输出机器可读合规报告。

**Repo Contract（未来）：** `scripts/check_repo_contract.py` — 验证 governance YAML 必填字段。

**Inventory（Round 43）：** `scripts/scan_repo_inventory.py` — 生成 `governance/repo_inventory.generated.json`。

---

## 6.3 不同轮次的 gate 强度

| 轮次类型 | Gate 重点 |
|----------|-----------|
| Governance Round | 文档 + 协议 + gitignore + 无 secrets |
| Implementation Round | 文档 + 测试 + 目录结构 |
| API Integration Round | 安全 + dry-run + budget guard |
| Translation Execution Round | 原文/译文保护 + 成本 + checkpoint |
| Frontend Round | 前端启动 + Playwright smoke |
| Review Round | 输出一致性 + issue report |
| Tooling Round | agent_gate 自身 + 环境审计 |

---

## 6.4 与通用协议的关系

- `agent_gate` 应逐步吸收 `governance/repo_protocol_standard.yaml` 要求
- **不得**随意篡改协议文件本体
- 项目 override 只记录在 `project.yaml` 与 `docs/repo_protocol_alignment.md`
- 每轮 Agent 应运行 gate（实现后）或手动对照本文件（实现前）

---

## MVP 实现 sketch（Round 41）

```python
# scripts/agent_gate.py — 未来实现
# 1. Parse args: --json, --strict
# 2. Run checks from checklist above
# 3. Write docs/reports/agent_gate_report.md
# 4. sys.exit(0|1|2)
```

Round 02 仅规划，不实现完整脚本。

---

## 每轮协议检查流程

```
开始
 → python3 scripts/agent_gate.py
 → 若 exit 2: 停止，写报告
 → 若 exit 1: 记录 warnings，继续低风险任务
 → 若 exit 0: 继续
 → （Round 42+）python3 scripts/check_protocol_standard.py
 → 更新 docs/reports/
结束
```
