# 质量审核流程设计

## 审核维度

至少包括：

1. 漏译。
2. 多译。
3. 误译。
4. 术语不一致。
5. 人名不一致。
6. 地名不一致。
7. 组织名不一致。
8. 技能名不一致。
9. 称呼不一致。
10. 角色语气漂移。
11. 世界观冲突。
12. 段落错位。
13. 日文残留。
14. 中文残留。
15. 目标语言不自然。
16. 机翻腔。
17. 表达改写过度（仅用于用户修改稿或局部重译对比）。
18. 伏笔被提前解释。
19. 暧昧表达被强行明确化。
20. 敬语处理错误。
21. 标点问题。
22. 章节标题问题。
23. 版权声明或出处信息缺失。
24. 格式问题。

参考方法吸收后，审核 issue 应优先使用 `docs/translation_quality_taxonomy_reference_inspired.md` 中的稳定标签，例如 `MISTRANSLATION`、`OMISSION`、`INCONSISTENT_TERM`、`LOCKED_TERM_VIOLATION`、`PLACEHOLDER_LOST`、`PROMPT_CONTRACT_VIOLATION` 等。

## Review Issue Schema

权威 JSON Schema：`data/schemas/review_issue.schema.json`。样例报告：`data/examples/review_issue_report.example.json`（synthetic fixture 生成，可提交）。

当前机器报告使用 `schema_version: 1.1.0`。零 issue 只表示 `machine_checked`，报告固定写入 `review_actor_type: machine`、`approval_state: not_granted`；调用方填写的 `generated_by` 只是来源描述，不能据此成为用户或授予批准。该检查不证明语义、文学质量或完整源清单已验收。1.0.0 历史报告仍可读取，缺少 actor 证据保持未知，旧 `human_reviewed` 字符串不被转换为新的用户批准。真实审核记录不在此处批量改写。

报告顶层字段：

```yaml
schema_version:
project_id:
language_direction:
review_status:   # 对齐下方审核状态机
generated_at:
generated_by:
issues: []
summary: { total, by_type, by_severity }
```

单条 `ReviewIssue` 字段：

```yaml
issue_id:
project_id:
language_direction:
chapter_id:
paragraph_id:
segment_id:
issue_type:      # 稳定标签，见 translation_quality_taxonomy_reference_inspired.md
severity:
source_text_ref: # 短引用，非全文
target_text_ref:
description:
suggested_fix:
related_term_ids:
related_character_ids:
related_world_bible_ids:
status:          # open | acknowledged | resolved | wont_fix
created_by:
created_at:
resolved_at:
requires_human_review:
auto_fixable:
human_edited_segment:
```

## Round 49 机器审核维度（deterministic）

| 维度 | Checker | 标签示例 | 说明 |
|------|---------|----------|------|
| 术语一致性 | `checker.term_consistency` | `LOCKED_TERM_VIOLATION`, `INCONSISTENT_TERM` | 对照 glossary fixture；locked 禁止自动改译文 |
| 段落对齐 / 漏译启发 | `checker.segment_alignment` | `SEGMENT_ALIGNMENT_ERROR`, `OMISSION` | expected/orphan segment_id；词数比例启发式 |
| 改写 diff | `checker.refinement_diff`（legacy name） | `OVER_REFINEMENT` | draft vs revised/final 表面差异（不写入正文） |

CLI：`python3 scripts/run_quality_review.py --write-example`。Workbench 的当前项目从 `/api/projects/{project_id}/quality-review` 读取报告，审核操作保存到项目 review-state API；静态 JSON 仅是演示回退。旧 localStorage 记录保留供人工参考，不能作为正式通过依据。机器审核**不覆盖** `human_edited` 段落。

源文导入时在既有项目 manifest 保存 `source_inventory`：片段 ID、原文 UTF-8 SHA256、语言方向、导入来源及这份清单的摘要。它覆盖该次导入的全部输入；短样例 provider 截取部分段落不能缩小此分母。后续仅更新译文时保留清单；显式重新导入源文才更换它。当前 HTTP 生成入口在调用 provider 之前从输入文本解析源行，质量审核从这份独立清单检查缺失、重复、多余、空译文及同 ID 改源，不从现有译文反推应有范围。尚无可靠清单的历史 manifest 只读保留，并报告覆盖未知，不自动迁移或补造旧范围。

这里的片段 ID 是已导入源单元，不是目标句子的数量。合法合句/拆句需有对应源单元或显式 span 对齐；缺少映射是工程覆盖未证明，不能据此宣称语义漏译。导入清单只证明本项目选择的输入，不能证明已导入全书。长度启发式、语义和文学质量仍需分别校准。

真实项目没有明确词表时记录 `none_no_project_glossary` 并跳过术语检查，不借用演示术语。Workbench 的明确 demo 项目可使用其 synthetic fixture；通用 runner/CLI 只有未指定源输入的演示调用才默认使用样例对。自定义 `--segments` 未附 `--glossary` 时不会加载样例词表。CLI 的 `CHECKED_WITH_ISSUES` / `CHECKED_NO_ISSUES` 只描述检查过程，均不授予批准；退出码保持原约定。

留待 Round 50+：语义误译、角色语气、世界观、日文残留、机翻腔等（需模型或更厚规则）。

## 审核状态

- `draft`
- `machine_translated`
- `review_needed`
- `term_conflict`
- `voice_conflict`
- `world_conflict`
- `style_issue`
- `final_ready`
- `human_reviewed`
- `machine_checked`（确定性机器检查；不授予批准）
- `final`

## 审核原则

- 审核流程生成 issue，不自动覆盖译文。
- 所有 issue 必须可定位到 chapter 和 segment。
- 涉及 locked 术语时不得自动修改。
- 对伏笔、暧昧表达和角色语气保持保守。
- high 及以上 issue 默认阻止 final 导出，除非人工明确确认。
- Validator 与 checker 生成的 issue 必须写回 JSONL 或 review issue 数据，不散落在不可解析日志中。

## Workbench 段落通过与版本变更

所有段落状态修改（包括通过、驳回、退回待审核）都绑定同一项目、段落 ID、语言方向和当前原文/译文内容。客户端先从 `/api/projects/{project_id}/workbench-data` 读取显示内容及 `approval_identity`，核对后 PATCH `/api/projects/{project_id}/review-state`：

```json
{"segments":{"seg-001":{"status":"approved","expected_identity":"<该段落返回的 sha256 指纹>"}}}
```

服务端在项目写锁内比较指纹；缺失、无效、过期指纹返回 409；正式通过还要求原文和译文非空，整次段落/issue 补丁不保存。页面显示未保存并提供刷新入口，重新读取和审核最新内容后才能再通过。指纹只保存摘要，不复制原文或译文；时间和 PASS 元数据不参与内容身份。

嵌入 manifest 的旧 `approved`、无来源的历史审核和过期审核均需重新核验，原值与备注保持可读，不批量迁移。`review-state` 的 `decision_summaries` 是只读解释：旧标签加内容指纹仍为未知，不能自动进入 approved 导出或 TM。

HTTP 服务没有可信真人身份证明，因此 PATCH 固定记录 `unknown` 来源；请求体、header、自报 actor、`autoApprove` 或 PASS 字样不能制造真人批准。状态修改只支持 `approved/rejected/pending`，真人审核和最终批准在此入口拒绝。客户端 provenance 字段不能覆盖服务端记录；无状态的普通备注更新不改变已有来源。

受控本地 Python 服务调用可通过 `DecisionActor("agent", "<调用方来源>")` 或 `psh_proxy` 明确记录非真人决定；此参数不能从 HTTP JSON 读取。服务调用方负责该来源归属，这是本地工程调用契约，不是防御有文件写权限者的认证系统。`machine` 和 `unknown` 不具备候选接受资格，`human`/最终批准的签发接口未实现，保持关闭。实际 PSH 绑定/权限与真人证明须在后续集成阶段验收，不能由此接口推定。

Workbench approved 导出与 manifest TM 复用同一内容绑定、非空、非真人候选接受判据。输出标记 `nonhuman_candidate`、actor 来源、`human_approved_final: false` 和 `is_canonical: false`；这不代表正式译文或真人验收。无来源 run 的 `approved` 标签也不能绕过判据；显式 `translated` TM 模式仍保留为未审核资料，`draft` 预览仍需确认。内容变化使旧决定失效。实际 canonical/生产入口与 UI 说明在 P2.R03 继续验收。
