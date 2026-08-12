# Agent Gate and Protocol Check

`scripts/agent_gate.py` 是 Round 41 实现的完整门禁能力。它可能写报告或触发 workspace 敏感检查，**禁止在真实仓库工作树运行**；仅可在一次性隔离副本运行，且隔离产生的 `workspace/`、`reports/`、`.agent_runtime/` 等输出不得写回。真实工作树只运行当前合同指定的 targeted/read-only checks。

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
| `reference_method_docs_exist` | 参考方法总纲、方法栈、核心流水线设计 |
| `stable_id_jsonl_doc_exists` | stable ID 与 JSONL 设计 |
| `extractor_validator_doc_exists` | ResponseExtractor / Validator 设计 |
| `provider_adapter_doc_exists` | Provider Adapter / Registry 设计 |
| `exporter_principle_doc_exists` | exporter-only 输出原则 |
| `rm_roadmap_exists` | RM-01 到 RM-40 路线图 |
| `rm_prompts_exist` | RM-01 到 RM-10 Prompt 草案 |

**Protocol Checker（Round 42 MVP）：** `scripts/check_protocol_standard.py` — 校验根目录/治理文件、协议版本与 `project.yaml` 对齐、AGENTS 阅读顺序。

该 checker 会写合规报告，因此下列命令也只在一次性隔离副本运行；真实工作树用 `npm run check:tooling` 中不写报告的目标检查。

运行：

```bash
python3 scripts/check_protocol_standard.py
python3 scripts/check_protocol_standard.py --json
```

真实工作树推荐运行 `npm run check:tooling` 或当前合同列出的更窄检查。完整 gate 与 protocol checker 的组合只能由外层在一次性隔离副本中串行运行。

**Repo Contract（未来）：** `scripts/check_repo_contract.py` — 验证 governance YAML 必填字段。

**Inventory（Round 43）：** `scripts/scan_repo_inventory.py` — 生成 `governance/repo_inventory.generated.json`。

Inventory 生成是写入型维护，不是每轮或 live-tree 隐式验证；只有当前 scoped task 明确拥有 inventory refresh 时才可运行并审查其精确 diff。

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
- 每轮 Agent 应手动对照本文件并运行合同指定的 targeted/read-only checks；完整 gate 只有在合同要求且已有一次性隔离副本时才运行

---

## MVP 实现 sketch（Round 41）

```python
# scripts/agent_gate.py — 未来实现
# 1. Parse args: --json, --strict
# 2. Run checks from checklist above
# 3. Write docs/reports/agent_gate_report.md
# 4. sys.exit(0|1|2)
```

Round 41 已实现 MVP（`scripts/agent_gate.py`）。

## MVP 已实现检查项（Round 41）

| ID | 状态 |
|----|------|
| `docs_exist` | PASS/FAIL — README、AGENTS、project.yaml、vision、architecture、governance_rules、index |
| `roadmap_exists` | PASS/WARN/FAIL — 00–40 为核心；41–50 默认 WARN，`--strict` 时 FAIL |
| `protocol_exists` / `protocol_alignment_exists` | PASS/FAIL |
| `tooling_strategy_exists` / `mcp_plan_exists` / `frontend_plan_exists` / `api_provider_strategy_exists` | PASS/FAIL |
| 参考方法相关文档（reference、stable_id、extractor、provider、exporter） | PASS/FAIL |
| `prompt_templates_exist` | PASS/WARN — `prompts/*_template.md` 数量 ≥ 6 |
| `direction_dirs_exist` | PASS/WARN |
| `gitignore_safe` | PASS/WARN |
| `env_not_tracked` | PASS/FAIL — `.env` 被跟踪时为 BLOCKED |
| `input_sources_ignored` / `outputs_ignored` | PASS/WARN — `git check-ignore` 探测 |
| `git_status_*` | PASS/WARN — 工作区与分支摘要 |
| `agent_layer_*` | PASS/WARN — Layer 2.0 文件缺失默认 WARN；`--strict-layer` 时 FAIL |
| `vector_inspect_script_exists` / `vector_metadata_schema_exists` | PASS/WARN — Round 48 inspect 脚本与 schema |
| `vector_index_present` / `vector_index_health` | PASS/WARN — 无 index 时 soft fallback；有 index 时 metadata/orphan 漂移为 WARNING，不 BLOCKED |

### 隔离副本中的运行示例

```bash
python3 scripts/agent_gate.py
python3 scripts/agent_gate.py --json
python3 scripts/agent_gate.py --strict
python3 scripts/agent_gate.py --strict-layer
python3 scripts/agent_gate.py --json --strict-layer
pytest tests/test_agent_gate.py -q
```

报告路径：`docs/reports/agent_gate_report.md`（本地，已在 `.gitignore`）。

以上命令不得在真实工作树执行；外层必须证明副本是一次性的，并在完成后丢弃副本，不复制任何 gate 输出回真实仓库。

---

## 每轮协议检查流程

```
开始
 → 真实工作树运行合同指定的 targeted/read-only checks
 → 若合同要求完整 gate，创建一次性隔离副本并在其中运行 python3 scripts/agent_gate.py
 → 若 exit 2: 停止，写报告
 → 若 exit 1: 记录 warnings，继续低风险任务
 → 若 exit 0: 继续
 → 若合同还要求 protocol checker，在同一隔离副本运行 python3 scripts/check_protocol_standard.py
 → 丢弃隔离副本；不得把 workspace/reports/runtime 输出写回
结束
```
