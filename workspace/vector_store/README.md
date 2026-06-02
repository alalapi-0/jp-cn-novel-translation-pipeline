# workspace/vector_store

本地向量索引目录，默认 **不提交** 到 Git（见根目录 `.gitignore`）。

## 用途

- 存放项目级 vector index（早期 MVP 为 JSON mock index）
- 由 embedding pipeline 写入；本目录只读检查见 `scripts/vector_db_inspect.py`

## 默认路径

| 文件 | 说明 |
|------|------|
| `index.json` | JSON mock 索引（`index_metadata` + `vectors[]`） |
| `.gitkeep` | 保留空目录结构 |

## Metadata schema

- JSON Schema：`data/schemas/vector_index_metadata.schema.json`
- 设计文档：`docs/embedding_vector_db_design.md`
- 与 `docs/data_schema_plan.md` 中 `EmbeddingRecord` 字段对齐

每条向量 **至少** 含 metadata：`project_id`、`language_direction`、`chapter_id`、`model`、`version`。

## 检查命令

```bash
# 空/缺失索引（软 fallback，exit 1 WARNING）
python3 scripts/vector_db_inspect.py

#  bundled 脱敏样例（含缺失 metadata 与 orphan 演示）
python3 scripts/vector_db_inspect.py --example --sample 3

python3 scripts/vector_db_inspect.py --json
```

## 未来适配

| Backend | 说明 |
|---------|------|
| `json_mock` | 当前 MVP；便于 pytest 与无依赖 CI |
| `chroma` | 本地 Chroma collection + 同名 metadata 字段 |
| `faiss` | FAISS 向量 + 侧车 JSON/SQLite metadata |
| `sqlite_vector` | SQLite 单文件结构化 + 向量扩展 |

Adapter 须保持 `project_id` / `language_direction` 过滤键稳定；检查工具通过 `--index` 指向导出 JSON 或 adapter 子命令。

## 安全

- 不提交真实 embedding 二进制或大索引
- 治理轮不生成 embedding、不调 cloud API
- 检查输出仅 id/长度/类型摘要，不打印段落全文
