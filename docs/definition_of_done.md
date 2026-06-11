# Definition of Done

> Done 定义（2026-06-10 创建；2026-06-11 治理复核，无 Done 条件弱化）。锚点：`docs/product_final_state_spec.md` §25。
> 详细可验证条件见 `docs/phase_acceptance_criteria.md`；本文件是各级 Done 的权威汇总。

## 1. 自动化生产流程 Done（项目级）

当且仅当规格 §25 的 27 项全部满足（逐项证据见 FS-069 核对表）：

1–5. Phase A–E 全部按 `phase_acceptance_criteria.md` 对应节 PASS；
6–8. `production_candidate/`、`production_candidate_metadata.json`、`production_candidate_go_decision.md` 已生成；
9–18. Web UI 可启动，且总览 / 流水线控制（启动、暂停、恢复）/ 章节状态 / 术语库查看编辑与导入导出 / 三栏对照 / 修改稿上传 / 同步计划 / 导出 production_candidate 全部可用（Playwright 证据）；
19–22. blocking issue = 0、failed / validation_failed = 0、no active worker、no orphan worker；
23. local scheduler 可暂停 / 恢复 / 查看状态（`local_scheduler_status.py --json`）；
24. 所有关键报告存在（round / consistency / baseline / refinement / final review / candidate decision / cost）；
25. Git 中无真实原文、真实译文、API Key、token、cookie、大型 workspace 文件（agent_gate 证据）；
26. **未**标记 human_approved_final；
27. **未**对外发布。

## 2. Web UI MVP Done

`phase_acceptance_criteria.md` 第 6 节（U1–U9）全部 PASS。八页：Dashboard、项目设置、API / 模型设置、Pipeline 控制台、章节管理、术语库 CRUD、报告、导出入口；统一设计系统、中文界面、危险操作二次确认、Playwright 通过、Key 永不明文。

## 3. Web UI Final Done

`phase_acceptance_criteria.md` 第 7 节（F1–F8）全部 PASS。15 页齐全、对照页 6 模式、用户修改稿旅程可走通、状态标签全站统一、响应式与 a11y 基础达标、全套 UI 测试通过。

## 4. Phase A Done

`phase_acceptance_criteria.md` 第 1 节（A1–A9）全部 PASS。摘要：613 章 draft 完成、failed=0、blocking validation_failed=0、无漏段错位、checkpoint 与报告完整、无 worker 残留、可导出。

## 5. Phase B Done

第 2 节（B1–B8）全部 PASS。摘要：manifest / segment index / entity index 齐备、blocking conflicts=0、局部修正闭环、一致性报告完整、progressive disclosure 合规。

## 6. Phase C Done

第 3 节（C1–C5）全部 PASS。摘要：baseline 目录 + metadata + go decision 齐备、写保护生效、前置 Phase 验收通过。

## 7. Phase D Done

第 4 节（D1–D9）全部 PASS。摘要：全书 refined、R-MR 报告 / diff / change_log 齐备、三 checker 无 blocking、baseline 未被改动、无 worker 残留。

## 8. Phase E Done

第 5 节（E1–E8）全部 PASS。摘要：review index 完整、异常与过度润色候选闭环、blocking quality issue=0、final review report 完整、candidate 已生成且未标 final 未发布。

## 9. production_candidate Done

第 11 节（P1–P7）全部 PASS。摘要：目录完整、metadata 版本链、go decision、写保护、未标 human_approved_final、未发布、正文不入 Git。

## 10. human_approved_final 的限制

- 只能由**用户**在人工逐章审阅后明确确认生成；
- 任何 Agent、脚本、调度器**永远不得**自动标记；
- 它不在任何自动化轮次的 Done 范围内：FS-070 完成后项目处于"等待人工最终审阅"状态即为自动化流程的终点；
- 标记后该版本立即获得与 baseline 同级的写保护；
- 标记 human_approved_final 不等于允许发布；发布是独立的用户决策且当前为非目标。
