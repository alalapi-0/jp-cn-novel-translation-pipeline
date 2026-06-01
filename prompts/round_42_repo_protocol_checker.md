# Round 42：Repo Protocol Checker

## Agent 身份

你是 Protocol Checker Agent，负责实现 `scripts/check_protocol_standard.py`，输出机器可读协议合规报告。

## 当前轮次

Round 42

## 本轮类型

`protocol_alignment` / `tooling`

## 背景

Round 02 已同步完整协议 v0.3.0 并写入 `docs/repo_protocol_alignment.md`，但缺少自动化 checker。未来每轮 Agent 需运行协议检查以防 drift。

## 必读文件

- `governance/repo_protocol_standard.yaml`
- `project.yaml`
- `docs/repo_protocol_alignment.md`
- `docs/agent_gate_and_protocol_check.md`
- `governance/file_role_map.yaml`
- `prompts/protocol_alignment_round_template.md`

## 允许修改

`scripts/check_protocol_standard.py`、可选 `scripts/check_repo_contract.py` 骨架、合规报告模板、`governance/round_state.yaml`。

## 禁止修改

不得改写 `governance/repo_protocol_standard.yaml` 正文；不得删除 `docs/archive/` 备份。

## 工具要求

Python 3、PyYAML（或标准库 yaml）、git。

## MCP / Playwright 要求

N/A

## 通用协议要求

检查 project.yaml 中 protocol version 与协议一致；检查 AGENTS.md 阅读顺序与协议 default_reading_order 对齐（允许 documented overrides）。

## 具体任务

1. 实现 `scripts/check_protocol_standard.py`，支持 `--json` 输出。
2. 验证 required_root_files：AGENTS.md、README.md、project.yaml 存在。
3. 验证 required governance files 存在（agent_policy、round_state、file_role_map 等）。
4. 验证 protocol.version 与 project.yaml protocol_standard.version 一致。
5. 验证 docs/reports 与 docs/archive 目录存在。
6. 输出 `docs/reports/protocol_compliance_report.md`（本地）。
7. 与 `agent_gate.py` 集成说明（先跑 gate 再跑 protocol check）。
8. 记录 known failures 与 next action（协议允许 allow_known_failures）。

## 验收标准

1. checker 可运行并生成报告。
2. 版本不一致时能报告 fail。
3. 缺失 governance 文件时能报告 fail。
4. JSON 输出可被脚本解析。
5. 不修改协议正文。
6. 不读取 `.env`。
7. 对齐报告中的 override 项在报告中列为 informational。

## 安全检查

不输出 secrets；只检查文件存在与字段一致性。

## Git 提交建议

`feat: add repo protocol compliance checker`

## 最终报告格式

compliance_summary、passed_checks、failed_checks、overrides_noted、files_changed、next_round_43。
