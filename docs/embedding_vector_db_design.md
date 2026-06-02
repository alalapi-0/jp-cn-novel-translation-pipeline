# Embedding 与向量数据库设计

Embedding 的目的不是炫技，而是服务于整本小说翻译一致性。它帮助检索相似段落、术语上下文、角色语气、世界观证据和翻译记忆。

## 需要 embedding 的内容

1. 原文段落。
2. 译文段落。
3. 原文译文对齐片段。
4. 章节摘要。
5. 术语上下文。
6. 角色发言样例。
7. 世界观设定片段。
8. 已确认译名的例句。
9. 润色前后对比片段。

## 不建议 embedding 的内容

1. 纯日志。
2. 临时错误信息。
3. 无意义空行。
4. 重复标题。
5. 未清洗的大块乱码。
6. 未确认的敏感数据。
7. API Key、请求头、用户隐私或 `.env` 内容。

## Metadata 设计

每条向量记录至少包含：

```yaml
embedding_id:
project_id:
language_direction:
source_language:
target_language:
text_type:
chapter_id:
segment_id:
paragraph_id:
speaker_character_id:
term_ids:
world_bible_ids:
source_file:
target_file:
status:
created_at:
model:
provider:
version:
```

机器可读 schema：`data/schemas/vector_index_metadata.schema.json`（与 `docs/data_schema_plan.md` EmbeddingRecord 对齐）。

只读检查：`python3 scripts/vector_db_inspect.py`（缺失 index 为 WARNING 软 fallback）；样例 `--example` 见 `data/examples/vector_index_mock.example.json`。

## 检索场景

1. 翻译当前段落前，检索相似原文段落。
2. 翻译某个术语时，检索该术语过去出现位置。
3. 翻译某个角色台词时，检索该角色过去台词。
4. 润色当前段落时，检索初翻和原文对齐片段。
5. 检查术语冲突时，检索所有相关译法。
6. 检查角色语气时，检索同角色发言样例。
7. 检查世界观设定时，检索相关设定原文证据。

## 可替换向量库方案

### Option A: Chroma

- 适合场景：本地原型、轻量检索、Python 生态。
- 优点：上手快，metadata filter 直观。
- 缺点：长期大规模和部署形态需要评估。
- 当前项目是否应该早期采用：可以作为早期本地候选。
- 后续替换成本：中等，需保持 adapter 接口稳定。

### Option B: FAISS

- 适合场景：本地高性能向量检索和较大规模索引。
- 优点：成熟、性能好、无服务端依赖。
- 缺点：metadata 管理需要额外存储。
- 当前项目是否应该早期采用：可以作为本地候选，适合技术用户。
- 后续替换成本：中等，需要单独抽象 metadata store。

### Option C: SQLite + vector extension

- 适合场景：本地单文件项目、结构化数据和向量一起管理。
- 优点：部署简单，便于备份。
- 缺点：扩展兼容性和性能上限需验证。
- 当前项目是否应该早期采用：可作为中期本地方案。
- 后续替换成本：较低，结构化 schema 容易迁移。

### Option D: LanceDB

- 适合场景：本地或轻量服务化数据湖式向量存储。
- 优点：适合批量数据和列式存储。
- 缺点：项目早期引入可能偏重。
- 当前项目是否应该早期采用：暂不优先。
- 后续替换成本：中等。

### Option E: Remote vector database

- 适合场景：多人协作、服务端部署、跨设备访问。
- 优点：可扩展、便于集中管理。
- 缺点：成本、隐私、网络和权限复杂度更高。
- 当前项目是否应该早期采用：不建议早期采用。
- 后续替换成本：取决于 adapter 设计，需避免锁定供应商。

## 早期建议

早期优先本地 Chroma 或 FAISS，避免过早引入复杂服务端。但任何实现都必须通过 vector store adapter 接入，不写死唯一向量库。

## 约束

- 向量库不能替代术语表。
- 向量库不能替代角色表。
- 向量库不能替代人工确认规则。
- 检索必须受 `project_id` 和 `language_direction` 约束。
