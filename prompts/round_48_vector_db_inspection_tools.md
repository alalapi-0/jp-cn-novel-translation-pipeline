# Round 48：Vector DB Inspection Tools

## Agent 身份

你是 Vector DB Tooling Agent，负责向量库检查工具规划或 MVP，不无脑生成 embedding。

## 当前轮次

Round 48

## 本轮类型

`tooling` / `data`

## 背景

embedding 与向量库设计见 `docs/embedding_vector_db_design.md`，但缺少 inspection 工具。生成向量前必须有 schema、metadata 与过滤设计。

## 必读文件

- `docs/embedding_vector_db_design.md`
- `governance/model_policy.yaml`
- `governance/data_policy.yaml`
- `docs/agent_tooling_strategy.md`

## 允许修改

`scripts/vector_db_inspect.py` 或规划文档、schema 示例、tests（mock index）、`workspace/vector_store/` README。

## 禁止修改

不生成真实 embedding；不建立生产向量库数据；治理轮不调 cloud embedding API。

## 工具要求

Python 3；可选 chromadb/faiss 仅作 dev dependency 且文档说明（或用 JSON mock index）。

## MCP / Playwright 要求

N/A

## 通用协议要求

embedding_policy：无 schema/metadata/cost guard 不得 bulk embed。

## 具体任务

1. 定义 vector index metadata schema（chapter_id、direction、embedding_model、version）。
2. 实现 inspect CLI：统计条目数、缺失 metadata、orphan vectors。
3. 支持 mock/empty index 验证 CLI 行为。
4. 文档化 Chroma/FAISS/SQLite vector 未来适配点。
5. 与 workspace gitignore 策略对齐。
6. 添加 agent_gate 可选检查项（index 路径存在性）。
7. 写 Round 49/50 对 vector 检索的依赖说明。
8. 更新 round_state。

## 验收标准

1. inspect 脚本对 empty/mock index 可运行。
2. metadata 缺失可报告 WARNING。
3. 未生成真实 embedding 文件进 git。
4. schema 文档与 data_schema_plan 一致或 cross-ref。
5. cost/过滤设计已文档化。
6. 无 API key 泄露。
7. 不阻塞无向量库时的其他轮次（软阻塞 fallback）。

## 安全检查

不读取 `.env`；不 upload 向量到外部服务。

## Git 提交建议

`feat: add vector db inspection tooling scaffold`

## 最终报告格式

schema_summary、inspect_commands、mock_results、future_adapters、blockers。
