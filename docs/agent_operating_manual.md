# Agent Operating Manual

未来所有推进轮 Agent 的工作手册。与 `AGENTS.md` 互补：AGENTS.md 为入口清单，本手册为操作细则。

---

## 5.1 Agent 类型

### Governance Agent

| 项 | 说明 |
|----|------|
| 职责 | 审计、文档、路线图、协议对齐、目录规划 |
| 必读 | 协议、`project.yaml`、`governance_rules`、路线图、对齐报告 |
| 允许修改 | `docs/`、`prompts/`、`governance/`、README、轻量 `.gitignore` |
| 禁止 | 真实翻译、真实 API、embedding、大型依赖安装 |
| 必须输出 | 审计/对齐/治理报告 |
| 真实 API | 否 |
| 安装工具 | 否（轻量脚本除外） |
| 真实原文 | 否 |

### Implementation Agent

| 项 | 说明 |
|----|------|
| 职责 | 按 Round 实现模块、schema、脚本、测试 |
| 必读 | 架构、shared core 设计、当前 Round Prompt |
| 允许修改 | `src/`、`tests/`、`data/schemas/`、相关文档 |
| 禁止 | 越级实现、无 fake provider 直接接真实 API |
| 必须输出 | 实现说明、测试结果 |
| 真实 API | 否（先用 fake） |
| 安装工具 | 是（必要依赖，需记录） |
| 真实原文 | 仅当 Round 明确要求且用户授权 |

### Translation Execution Agent

| 项 | 说明 |
|----|------|
| 职责 | 批量初翻、checkpoint、导出 |
| 必读 | batch workflow、provider 策略、术语/角色/世界观 |
| 允许修改 | workspace 输出、manifest、checkpoint |
| 禁止 | 无 cost guard 的真实批量调用 |
| 必须输出 | run log、成本摘要、checkpoint 报告 |
| 真实 API | 是（需授权与预算） |
| 安装工具 | 按需 |
| 真实原文 | 是（本地处理，不默认提交） |

### API Integration Agent

| 项 | 说明 |
|----|------|
| 职责 | provider adapter、dry-run、cost guard |
| 必读 | `api_provider_strategy.md`、model_policy |
| 允许修改 | adapter 代码、config 示例、dry-run 测试 |
| 禁止 | 无 dry-run 直接 production 调用 |
| 必须输出 | adapter 文档、dry-run 结果 |
| 真实 API | controlled run only |
| 安装工具 | 是 |
| 真实原文 | 否（除非集成测试需要样例） |

### Review Agent

| 项 | 说明 |
|----|------|
| 职责 | 术语/角色/世界观/漏译/润色 diff 审核 |
| 必读 | quality_review_workflow、refinement_workflow |
| 允许修改 | review 报告、issue 列表 |
| 禁止 | 静默覆盖 human_edited 内容 |
| 必须输出 | issue report、一致性检查结果 |
| 真实 API | 可选（强模型审核轮） |
| 安装工具 | QA 脚本 |
| 真实原文 | 读本地，不提交 |

### Frontend Agent

| 项 | 说明 |
|----|------|
| 职责 | Workbench UI、数据绑定、编辑 MVP |
| 必读 | frontend_workbench_plan、Round 36–39/46 |
| 允许修改 | `frontend/`、相关静态资源 |
| 禁止 | 只看代码不做浏览器验证（Round 46 起） |
| 必须输出 | UI smoke 结果、截图或 DOM 摘要 |
| 真实 API | 否 |
| 安装工具 | Node、Playwright（Round 44+） |
| 真实原文 | 否（用 mock/样例） |

### Tooling Agent

| 项 | 说明 |
|----|------|
| 职责 | agent_gate、protocol checker、环境审计、Playwright 框架 |
| 必读 | agent_tooling_strategy、agent_gate_and_protocol_check |
| 允许修改 | `scripts/`、工具文档、smoke tests |
| 禁止 | 把工具链变成大规模重构 |
| 必须输出 | gate 报告、工具验证结果 |
| 真实 API | 否 |
| 安装工具 | 是（Playwright 等） |
| 真实原文 | 否 |

### Protocol Alignment Agent

| 项 | 说明 |
|----|------|
| 职责 | 协议读取、对齐报告、迁移计划 |
| 必读 | 完整 `repo_protocol_standard.yaml`、repo_protocol_alignment |
| 允许修改 | 对齐报告、`project.yaml` overrides、治理骨架 |
| 禁止 | 擅自改写协议正文 |
| 必须输出 | alignment report、待确认冲突列表 |
| 真实 API | 否 |
| 安装工具 | 否 |
| 真实原文 | 否 |

---

## 5.2 每轮开始前必须做

1. 读取 `README.md`
2. 读取 `docs/project_vision.md`
3. 读取 `docs/architecture_overview.md`
4. 读取路线图（00–40 与 41–50 视轮次而定）
5. 读取 `docs/governance_rules.md`
6. 读取 `docs/repo_protocol_alignment.md`
7. 读取当前轮 Prompt
8. 执行 `git status`
9. 检查 `.env` 是否被 Git 跟踪
10. 检查是否存在未提交的重要变更
11. 运行 `scripts/agent_gate.py`（Round 41 起）

---

## 5.3 每轮结束前必须做

1. 更新相关文档
2. 更新 `governance/round_state.yaml`（若适用）
3. 更新本轮报告（`docs/reports/` 本地）
4. 运行必要测试或检查
5. 执行 `git status`
6. 确认没有提交 `.env`
7. 确认没有提交真实原文
8. 确认没有提交真实译文（除非用户明确要求）
9. commit（用户或 Prompt 要求时）
10. push（远程可用且用户授权时）

---

## 5.4 硬阻塞定义

遇到以下情况**必须停止**并报告，不得继续自主修改：

1. API Key 缺失，但当前轮必须真实调用 API
2. Git push 权限缺失，但当前轮必须远程同步且用户已要求 push
3. 本地权限不足，无法读写必需路径
4. 缺少用户承诺提供的协议文件，且当前轮唯一目标是协议对齐
5. 真实原文格式损坏，无法安全处理
6. 继续执行会覆盖真实译文
7. 继续执行会泄露敏感信息
8. 预算上限缺失而当前轮要真实调用大模型
9. MCP 安装失败且当前轮必须依赖 MCP（如 Round 45 无 fallback）
10. 上下文不足以安全修改核心架构

---

## 5.5 软阻塞定义

以下情况**记录但继续**（可用 fallback）：

1. 某些文档缺失（可本轮补齐）
2. 某些目录不存在（可创建占位）
3. 某些工具未安装但有 fallback
4. 某些路线图未细化
5. 某些测试未建立
6. 前端尚未实现
7. API provider 尚未接入
8. 向量库尚未选择
9. 通用协议未完全覆盖项目细节
10. 文档命名略有不统一

---

## 报告格式

每轮报告至少包含：

- summary
- files_changed
- validation_results
- unresolved_questions
- soft_blockers
- hard_blockers
- next_round_recommendation
