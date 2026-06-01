# 目录结构演进方案

## 目标结构

```text
.
├── README.md
├── .gitignore
├── .env.example
├── docs/
├── prompts/
├── notes/
├── input_jp/
├── output_cn/
├── input_cn/
├── output_jp/
├── data/
│   ├── projects/
│   ├── schemas/
│   └── examples/
├── workspace/
│   ├── manifests/
│   ├── parsed/
│   ├── segments/
│   ├── embeddings/
│   ├── vector_store/
│   ├── context_packs/
│   ├── model_runs/
│   └── checkpoints/
├── shared/
│   └── README.md
├── directions/
│   ├── jp_to_cn/
│   └── cn_to_jp/
├── src/
│   └── README.md
├── frontend/
│   └── README.md
├── scripts/
│   └── README.md
└── tests/
    └── README.md
```

## 演进原则

1. 本轮可以只创建轻量目录。
2. 不要填充大量空代码。
3. 每个新增顶级目录必须有 README 或 `.gitkeep`。
4. 真实原文和真实译文默认不提交。
5. `workspace` 中大型中间文件默认不提交。
6. `data` 中可提交 schema 和样例，不提交真实版权文本。
7. 旧目录继续有效，不做一次性大迁移。

## 目录职责

- `input_jp/`：日文原文输入。
- `output_cn/`：中文译文输出。
- `input_cn/`：中文原文输入。
- `output_jp/`：日文译文输出。
- `shared/`：共享核心。
- `directions/`：方向专属规则。
- `workspace/`：中间产物和运行状态。
- `data/`：结构化项目数据。
- `src/`：未来代码。
- `frontend/`：未来前端。
- `scripts/`：轻量脚本。
- `tests/`：测试。
