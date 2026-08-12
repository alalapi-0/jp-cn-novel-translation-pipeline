# Final State Implementation Roadmap

> v2.0（2026-06-18）。最高锚点：`docs/product_final_state_spec.md` v2.0。
> 本路线图废弃旧 Phase D refinement / R-MR / Phase E / production_candidate 主线。

---

## 1. 当前仓库状态摘要（2026-07-13 实测）

| 维度 | 现状 | 证据 |
| --- | --- | --- |
| 全书章节 | **609 编号章**（`input_jp/README.md` 不计入章节） | 编号源文文件 / singleton export manifest |
| 翻译进度 | **609/609（100%）** | `output_cn/final_export_manifest.json` |
| 当前 Phase | **final_ready**；scheduler paused=true | `local_scheduler_status.py --json` |
| 下一调度 round | **无**；`next_round_id=null`、`next_chapter_range=null` | `local_scheduler_status.py --json` |
| Worker 状态 | 0 active / 0 orphan；scheduler lock absent | `check_orphan_workers.py --json` |
| 一致性治理 | final dry-run changed_segments=0；term variance=0；singleton export PASS | `docs/final_consistency_report.md` / `reports/final_translation_singleton_check.json` |
| 最终译文交付 | 唯一文件：`output_cn/translated/full_volume_cn.md` | `output_cn/final_export_manifest.json` |
| 执行方式 | 历史产物来自真实 API micro-round；未来新作品支持 API Mode 或 Agent Quota Mode | `docs/translation_production_protocol.md` |
| 前端 | 现有 4 页 Workbench + 本地 API；仍需按 v2.0 UI 完整化 | `frontend/` / Playwright |
| Git 安全 | `.env` 未跟踪；真实输出默认 ignored | `.gitignore` + agent_gate |

## 2. 与最终规格 v2.0 的差距分析

| # | 规格要求 | 现状 | 差距 |
| --- | --- | --- | --- |
| G1 | 本地调度系统 | 已完成；状态机已切到 `final_ready` | 小（UI 接线） |
| G2 | 全书翻译 | 已完成 | 已关闭 |
| G3 | 一致性检查 | 已完成；另有 final cleanup | 已关闭 |
| G4 | baseline lock | 已完成 | 已关闭 |
| G5 | singleton final export | 已完成；仅保留一份最终译文 | 已关闭 |
| G6 | API / Agent Quota 双执行路径 | API 路径存在；Agent Quota 协议已定义，写入器仍需实现 | 中 |
| G7 | Web UI v2.0 信息架构 | 现有 4 页，未完整覆盖 | 大 |
| G8 | 用户修改稿同步 | 缺失 | 大 |
| G9 | 导出系统完整化 | singleton final 完成；辅助包 / EPUB / TXT 未完整 | 中 |

**结论**：当前作品的自动化翻译与一致性治理已收口，生产状态为 `final_ready`。后续主线不再是 R-MR 或 production_candidate，而是：

```text
新作品 API/Agent 双路径翻译能力
→ Web UI v2.0
→ 用户修改稿同步
→ 导出辅助包完整化
→ 最终 DoD 验收
```

## 3. 阶段拆分总览

| Stage | 名称 | 轮次范围 | 真实 API | Agent Quota | Web UI | 状态 |
| --- | --- | --- | --- | --- | --- | --- |
| S0 | 治理与基线对齐 | FS-000 | 否 | 否 | 否 | completed |
| S1 | 本地调度器主线 | FS-001…FS-007 | smoke only | 否 | 否 | completed |
| S2 | 全书翻译完成 | FS-008…FS-010 + historical D-MR | 是 | 可选 | 否 | completed |
| S3 | configs 资产层与术语库内核 | FS-011…FS-016 | 否 | 否 | 否 | completed |
| S4 | Web UI 基座与设计系统 | FS-017…FS-022 | 否 | 否 | 是 | pending |
| S5 | Web UI MVP v2.0 | FS-023…FS-030 | 否 | 否 | 是 | pending |
| S6 | 一致性检查工具链 | FS-031…FS-037 | Level 4 小规模 | 可选判断 | 否 | completed |
| S7 | baseline lock + singleton final export | FS-038…FS-039 + 2026-06-18 cleanup | 否 | 否 | 否 | completed |
| S8 | API / Agent Quota 统一写入器 | FS-new | 可选 | 是 | 可选 | pending |
| S9 | 用户修改稿同步 | FS-new | 局部重译小规模 | 可选 | 是 | pending |
| S10 | 导出辅助包完整化 | FS-new | 否 | 否 | 是 | pending |
| S11 | Web UI Final 与 DoD 验收 | FS-new | 验证性 | 验证性 | 是 | pending |

Legacy，不再作为主线：

| Legacy Stage | 原名称 | 处理 |
| --- | --- | --- |
| old S8 | Phase D refinement / R-MR | deprecated；不得作为下一轮任务 |
| old S9 | Phase E / production_candidate | deprecated；不得作为自动化终点 |

## 4. 新主线阶段详情

### S8 API / Agent Quota 统一写入器

- **目标**：实现 `docs/translation_production_protocol.md` 中的同构产物契约，让外部 API 和 Agent 额度翻译都写入同一 segment/run schema。
- **输出**：`execution_mode` 字段、Agent quota 写入入口、报告模板、测试。
- **完成标准**：API mode 与 Agent quota mode 的产物能被同一个一致性检查和 final exporter 消费。
- **真实 API**：可选，小规模 smoke；默认 dry-run / fixture。

### S9 用户修改稿同步

- **目标**：上传用户修改稿，生成 diff / sync plan，经用户确认后同步 TM、glossary、character profile 与 revised output。
- **禁止**：覆盖原文、baseline、human_approved_final。
- **完成标准**：`phase_acceptance_criteria.md` User revision sync 节全部 PASS。

### S10 导出辅助包完整化

- **目标**：在 singleton final translation 之外，按需生成辅助包：TXT、EPUB、双语对照、glossary、character、world、TM、报告。
- **原则**：辅助包可再生成，不得成为第二份“最终译文”。

### S11 Web UI Final 与 DoD 验收

- **目标**：完整实现 v2.0 UI，跑通用户视角测试，逐条核对 `definition_of_done.md`。

## 5. 推荐推进顺序

1. 保持当前作品 `final_ready` 状态，不再启动 R-MR。
2. 先做 S8：Agent Quota Mode 写入器和报告，让新作品可不依赖外部 API。
3. 继续 S4/S5：把 UI 的 phase/status 文案改成 v2.0。
4. 做 S9：用户修改稿同步。
5. 做 S10/S11：辅助导出和最终验收。

## 6. 全局风险

| 风险 | 等级 | 缓解 |
| --- | --- | --- |
| 旧 R-MR 文档误导后续 agent | P1 | 旧文档归档；AGENTS/README/roadmap/spec 全部指向 v2.0 |
| launchd 后台 tick 产生 orphan worker | P0 | tick 末尾强制 `check_orphan_workers`；lock 协议 |
| 真实 API 成本失控 | P0 | cost guard、`MAX_TEST_COST_USD`、每 tick 单任务 |
| Agent Quota 输出绕过结构化产物 | P1 | 必须写入同构 segment/run schema；一致性检查后才 export |
| 真实译文 / 原文误提交 | P0 | 精确 staged-diff / tracked-path / secret 检查；完整 agent_gate 仅在隔离副本运行 |
| UI 范围膨胀拖垮主线 | P1 | 每轮一个页面切片；MVP 优先 |
| 用户修改稿同步覆盖 baseline | P0 | 同步禁写 baseline/human_approved_final（代码层拒绝 + 测试） |

## 7. 验证命令

```bash
python3 scripts/local_scheduler_status.py --json
python3 scripts/check_orphan_workers.py --json
python3 scripts/check_final_translation_singleton.py --json
# 在真实工作树只运行当前合同指定的 targeted/read-only tests。
# 完整 agent_gate 仅在一次性隔离副本运行，输出不得写回。
```
