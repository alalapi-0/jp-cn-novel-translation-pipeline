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


## 显式作品规则与只读审计

`work_rules.example.json` 是空的合成模板，不会自动载入，也不代表任何作品已经核验。
当前格式为 `work-rules/1`，唯一支持的 activation 是 `review_only`。配置文件必须位于本仓库
`configs/` 或 `workspace/configs/`，以文件 SHA-256、work_id、已登记 source_revision 和
JP_TO_CN / CN_TO_JP 显式选择。哈希和声明身份只限定输入范围，不证明规则语义或源文真实性，
也不签发人审、canonical、写回或发布权限。旧 inactive/unverified 归档不能作为活动配置加载。

`target_files` 必须列出所选普通 `segments.json` 的仓库相对路径与精确字节 SHA-256；
只允许 `workspace/runs/`、`workspace/archived_runs/` 或 `workspace/candidates/` 下的文件。
路径、清单成员和哈希在解析正文前检查，正文还须声明相同作品、源版本及方向。
不扫描其他运行目录、不按 mtime 选择、不读取默认术语表/人物或风格文件。
章范围由显式 `--chapters START END` 或 rules.chapter_range 的两个整数给出；两者同时给出必须一致。

术语提示使用 rules.term_registry，每项含 term_id、source、canonical、aliases 和 kind。
canonical 在这里是待核提示；相同 source 可有不同 term_id / 语境，不强制唯一词面。
rules.contextual_variants 每项含 source、source_contains、target_contains_any，匹配后仅附解释，不隐去观察。

rules.audit 可含：

- target_field：默认 draft_text；可显式选 target_text，或为历史只读比较选 refined_text。不会恢复 refinement 生产路线。
- english_terms、protected_literals、punctuation_rules：字符串列表，均为选定作品提示；英文/假名/标点观察不会因此被自动删除。
- characters：每项含唯一 character_id、source_names、target_names，以及 voice_markers。
  每个 voice marker 含 source 字符串和 targets 字符串列表；机械匹配只是提示，不证明人物声音或翻译错误。
- previous_issues：每项含 path 和 sha256。允许本仓库 workspace/review/、workspace/candidates/
  或 workspace/tooling/actual_chapter_audits/ 下的普通 JSON；未列出、软链接、版本变化或外部路径在读取前拒绝。

选定旧问题文件须是 `work-review-input/1` 对象，含 work_id、source_revision、language_direction、
target_files（旧目标路径/版本，路径须属于本次选择范围）及 issues 数组；每条 issue 须有 segment_id，
可有 description、suggested_fix 等历史线索。旧数组/批准标签不可直接当可信审查输入。
旧目标哈希可以与当前目标不同，比较结果仅为“旧建议词面相同/提示出现或缺席”等关系，不能宣称语义已解决。

`audit_actual_chapter_content.py`、术语报告和预览 fixer 共用显式选择参数：
`--work-rules CONFIG --work-rules-sha256 SHA --work-id WORK --source-revision REV --language-direction DIRECTION`。
审计另须 `--output`，可选 `--previous-issues`。输出只能是
`workspace/tooling/actual_chapter_audits/` 或 `workspace/review/audits/` 中的新 JSON；原子发布且不覆盖既有报告或人工稿。
报告保留模式、策略/目标版本和定位，严重度/置信度未校准时明确未知；零观察不代表语义接受。
CN_TO_JP 不把日文目标中的假名当残留，JP 特有扫描会注明方向适用性。

维护者在选择契约、字段或审计输入格式变化时更新本节；当前任务和下一步仍只查 governance/round_state.yaml。
