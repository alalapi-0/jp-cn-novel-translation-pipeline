# configs/ — 翻译资产配置层（FS-011）

规格 `docs/product_final_state_spec.md` §10 定义的五个配置文件的 **脱敏模板**。

| 文件 | 内容 | Schema |
| --- | --- | --- |
| `glossary.yaml` | 术语库（13 字段 + 12 分类，规格 §7.8） | `schemas/glossary.schema.json` |
| `character_profile.yaml` | 角色设定（称呼关系 / 口癖 / 敬语风格，规格 §7.9） | `schemas/character_profile.schema.json` |
| `style_profile.yaml` | 风格配置（轻小说节奏 / 伏笔 / 段落结构，规格 §15.1） | `schemas/style_profile.schema.json` |
| `world_bible.yaml` | 世界观设定（14 分类，规格 §7.10） | `schemas/world_bible.schema.json` |
| `model_profiles.yaml` | 模型配置（profile / fallback / cost guard） | `schemas/model_profiles.schema.json` |

## 模板 vs 真实数据

- **本目录提交 Git，只放脱敏模板**：示例条目一律虚构（`サンプル~` / `示例~`），不得写入真实小说术语、译名、设定。
- **真实数据放 `workspace/configs/`**（已 gitignore），由 FS-012 从 `workspace/assets/translation_memory/` 迁移生成，结构与本目录模板一致。
- `model_profiles.yaml` 永不写入 API Key；密钥只从环境变量读取。

## 校验

```bash
python3 scripts/validate_configs.py          # 校验本目录模板
python3 scripts/validate_configs.py --json   # 机器可读输出
python3 scripts/validate_configs.py --configs-dir workspace/configs  # 校验真实数据
```

测试：`tests/test_configs_schema.py`（包含 13 字段 / 12 分类枚举 / 负例拒绝 / 脱敏断言）。
