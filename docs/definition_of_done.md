# Definition of Done

> Done 定义（v2.0，2026-06-18）。锚点：`docs/product_final_state_spec.md` v2.0。
> 详细可验证条件见 `docs/phase_acceptance_criteria.md`；本文件是各级 Done 的权威汇总。

## 1. 自动化生产流程 Done（项目级）

当且仅当以下条件全部满足：

1. Phase A 全书翻译完成；
2. Phase B 一致性检查完成；
3. Phase C singleton final export 完成；
4. `output_cn/translated/full_volume_cn.md` 已生成；
5. `output_cn/final_export_manifest.json` 已生成且声明 `singleton_full_volume_cn`；
6. `reports/final_translation_singleton_check.json` PASS；
7. Web UI 可以启动；
8. Web UI 可以显示项目总览；
9. Web UI 可以启动 / 暂停 / 恢复流水线；
10. Web UI 可以查看章节状态；
11. Web UI 可以查看和编辑术语库；
12. Web UI 可以导入 / 导出术语库；
13. Web UI 可以查看原文 / 译文 / 用户修改稿对照；
14. Web UI 可以上传用户修改稿；
15. Web UI 可以生成用户修改同步计划；
16. Web UI 可以导出唯一最终译文；
17. blocking issue = 0；
18. failed / validation_failed = 0；
19. no active worker；
20. no orphan worker；
21. local scheduler 可暂停 / 恢复 / 查看状态，completed project 显示 `final_ready`；
22. 所有关键报告存在（round / consistency / final export / cost 或 Agent usage）；
23. Git 中无真实原文、真实译文、API Key、token、cookie、大型 workspace 文件；
24. **未**标记 human_approved_final；
25. **未**对外发布。

自动化流程不再要求 Phase D refinement、R-MR、Phase E 或 production_candidate。

## 2. Web UI MVP Done

`phase_acceptance_criteria.md` 第 4 节（U1–U9）全部 PASS。八页：Dashboard、项目设置、API / Agent 设置、Pipeline 控制台、章节管理、术语库 CRUD、报告、导出入口；统一设计系统、中文界面、危险操作二次确认、Playwright 通过、Key 永不明文。

## 3. Web UI Final Done

`phase_acceptance_criteria.md` 第 5 节（F1–F8）全部 PASS。对照页支持原文 / 译文 / 用户修改稿，用户修改稿旅程可走通，状态标签全站统一，响应式与 a11y 基础达标，全套 UI 测试通过。

## 4. Phase A Done

`phase_acceptance_criteria.md` 第 1 节（A1–A9）全部 PASS。摘要：全部编号章翻译完成、failed=0、blocking validation_failed=0、无漏段错位、checkpoint 与报告完整、无 worker 残留、执行模式记录明确。

## 5. Phase B Done

第 2 节（B1–B8）全部 PASS。摘要：manifest / segment index / entity index 齐备、blocking conflicts=0、局部修正闭环、一致性报告完整、progressive disclosure 合规。

## 6. Phase C Done

第 3 节（C1–C6）全部 PASS。摘要：canonical segments 一致性修正稳定、唯一最终译文导出、singleton check PASS。

## 7. Singleton Final Translation Done

第 9 节（P1–P7）全部 PASS。摘要：唯一最终译文存在、manifest 指向唯一文件、无额外 final 副本、未标 human_approved_final、未发布、正文不入 Git。

## 8. human_approved_final 的限制

- 只能由**用户**在人工逐章审阅后明确确认生成；
- 任何 Agent、脚本、调度器**永远不得**自动标记；
- 它不在任何自动化轮次的 Done 范围内；
- 标记后该版本立即获得写保护；
- 标记 human_approved_final 不等于允许发布；发布是独立的用户决策且当前为非目标。

## 9. Legacy 路线限制

以下路线已从自动化生产 Done 中移除：

```text
Phase D refinement
R-MR
Phase E refinement final review
production_candidate
```

后续 Agent 不得把这些 legacy 路线作为下一轮任务，除非用户未来明确提出新的 v3 规格并修改 `docs/product_final_state_spec.md`。
