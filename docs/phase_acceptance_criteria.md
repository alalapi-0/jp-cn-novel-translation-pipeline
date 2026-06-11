# Phase Acceptance Criteria

> 阶段验收标准（2026-06-10 创建；2026-06-11 治理复核，无验收项弱化）。锚点：`docs/product_final_state_spec.md`。
> 所有条目必须**可检查**：以命令输出、报告文件、测试结果或 Playwright 断言为证据；禁止"体验良好"类不可验证表述。
> 每个阶段验收时生成核对表（checklist + 证据引用），存入 `workspace/round_reports/` 或 `docs/reports/`（脱敏统计版）。

## 1. Phase A：全书初翻 完成标准

| # | 条件 | 验证方式 |
| --- | --- | --- |
| A1 | 613 章全部存在 draft 输出 | `phase_a_completion_check.py --json` 章节计数 = 613 |
| A2 | 全部 segment status=completed | 同上，pending/in_progress=0 |
| A3 | failed segment = 0 | 同上 |
| A4 | blocking validation_failed = 0 | 同上 |
| A5 | 无章节错位 / 无漏段 | `audit_draft_structure.py`（FS-035）结果 0 blocking |
| A6 | checkpoint 完整可续跑 | 抽样 run 的 checkpoint hydrate 测试通过 |
| A7 | D-MR round reports 完整 | `workspace/round_reports/D-MR-*` 数量与队列一致 |
| A8 | no active / orphan worker | `check_orphan_workers.py --json` decision=CLEAN |
| A9 | draft 可导出或已导出 | exporter 运行成功，产物文件清单非空 |

## 2. Phase B：初翻一致性检查 完成标准

| # | 条件 | 验证方式 |
| --- | --- | --- |
| B1 | chapter manifest 已构建且覆盖 613 章 | `build_chapter_manifest.py --json` |
| B2 | segment index 已构建 | `build_segment_index.py` 输出存在且漏段=0 |
| B3 | entity index 已构建 | `build_entity_index.py` 输出存在 |
| B4 | glossary 冲突已统计 | `audit_glossary_conflicts.py --json` 可复现 |
| B5 | blocking conflicts = 0 | 同上，blocking 计数 = 0 |
| B6 | 必要局部修正 / 重译已完成 | local fix plan 全项状态 closed |
| B7 | 一致性报告完整 | `workspace/consistency_audit/` full report 存在 |
| B8 | progressive disclosure 合规 | 报告记录各 Level 展开比例；Level 4 调用数 ≤ 预算 |

## 3. Phase C：baseline lock 完成标准

| # | 条件 | 验证方式 |
| --- | --- | --- |
| C1 | Phase A、B 验收全部 PASS | 两份核对表存在 |
| C2 | `draft_full_baseline/` 生成 | 目录存在且章节数=613 |
| C3 | `draft_full_baseline_metadata.json` 完整 | 含全章节哈希与来源 run 引用 |
| C4 | `draft_full_baseline_go_decision.md` 结论明确 | 文件存在且逐条引用 A/B 核对表 |
| C5 | baseline 写保护生效 | `test_baseline_lock.py` 通过（写尝试抛错） |

## 4. Phase D：全书润色 完成标准

| # | 条件 | 验证方式 |
| --- | --- | --- |
| D1 | 613 章全部有 refined 输出 | refined manifest 计数 |
| D2 | R-MR round reports 完整 | `workspace/round_reports/R-MR-*` 与队列一致 |
| D3 | 每个 R-MR 有 diff + change_log | `build_refine_diff.py` 产物核对 |
| D4 | failed = 0、blocking validation_failed = 0 | runner 统计 |
| D5 | terminology preservation checker 无 blocking | `check_refinement_quality.py --json` |
| D6 | character voice checker 无 blocking | 同上 |
| D7 | over-refinement checker 无 blocking | 同上 |
| D8 | no orphan worker | `check_orphan_workers.py --json` CLEAN |
| D9 | baseline 未被修改 | baseline 哈希复核与 metadata 一致 |

## 5. Phase E：终检 完成标准

| # | 条件 | 验证方式 |
| --- | --- | --- |
| E1 | refined metadata / diff index 完整 | `build_final_review_index.py` 输出 |
| E2 | 修改比例异常已检查 | 异常章节清单每项有处置记录 |
| E3 | 过度润色候选已检查 | 候选清单闭环 |
| E4 | blocking quality issue = 0 | final review report 统计 |
| E5 | 局部重润色 / 修正已完成并复检 | fix plan closed + 复检报告 |
| E6 | final review report 完整 | `workspace/final_review/` 存在 |
| E7 | production_candidate 已生成 | 见第 11 节 |
| E8 | 未标记 human_approved_final / 未发布 | metadata 字段核验 |

## 6. Web UI MVP 完成标准（FS-030 闸门）

| # | 条件 | 验证方式 |
| --- | --- | --- |
| U1 | 八页可用：Dashboard / 项目设置 / API 设置 / Pipeline 控制台 / 章节 / 术语库 CRUD / 报告 / 导出入口 | 逐页 Playwright spec 通过 |
| U2 | Dashboard 显示 current phase / next task / active worker / orphan / 成本估算，且与 `local_scheduler_status.py --json` 一致 | Playwright 断言 |
| U3 | 控制台可暂停 / 恢复，pause file 真实写入 | Playwright + 文件断言 |
| U4 | 术语库 CRUD + 三格式导入导出可用 | Playwright + roundtrip 测试 |
| U5 | 全部页面接入统一布局壳与设计系统 | grep 无散落硬编码状态 / 色值 |
| U6 | 危险操作全部二次确认 | Playwright 断言 confirm 流程 |
| U7 | 界面中文优先 | 抽样页面无未翻译英文主文案（styleguide 除外） |
| U8 | 无未解释 console 错误；关键 API 请求正常 | 浏览器检查记录入 artifacts |
| U9 | API Key 永不明文出现在 DOM / 响应 | Playwright network 断言 |

## 7. Web UI Final 完成标准（FS-068 闸门）

| # | 条件 | 验证方式 |
| --- | --- | --- |
| F1 | 规格 §7 的 15 个主页面全部实现 | 导航无置灰占位 |
| F2 | 对照页支持 6 种栏模式 + 高亮 + 审阅标记 | Playwright spec |
| F3 | 上传 → 对齐 → diff → sync plan → 确认 → 同步 旅程可走通（fixture） | 跨页旅程测试通过 |
| F4 | 导出页全部导出项可用且显示前置信息 | Playwright spec |
| F5 | 11 个标准状态标签全站统一 | FS-065 审计报告 P1=0 |
| F6 | 1280 / 1024 视口核心流程可用 | FS-066 双视口测试 |
| F7 | 键盘可达性与对比度基础达标 | a11y 基础检查无 critical |
| F8 | `npm run test:ui` 全套通过（含完整用户旅程） | CI 输出 |

## 8. Glossary system 完成标准

| # | 条件 | 验证方式 |
| --- | --- | --- |
| G1 | 13 字段 + 12 分类 schema 校验通过 | `test_configs_schema.py` |
| G2 | CRUD / locked / approved 状态机有测试 | `test_glossary_store.py` |
| G3 | CSV / YAML / JSON roundtrip 无损 | `test_glossary_io.py` |
| G4 | locked 术语不被机器建议与导入覆盖 | 专项测试 |
| G5 | term usage index 可增量构建 | `test_term_usage_index.py` |
| G6 | prompt 注入仅含当前 batch 命中子集 | `test_prompt_builder_assets.py` |
| G7 | UI CRUD + 导入导出可用 | U4 |

## 9. User revision sync 完成标准

| # | 条件 | 验证方式 |
| --- | --- | --- |
| R1 | 未改动文本自动对齐率 100%（fixture） | `test_user_revision_align.py` |
| R2 | 对齐失败进入人工对齐而非强行覆盖 | 测试 + Playwright |
| R3 | sync plan 含规格 §19.3 全 12 项 | plan schema 测试 |
| R4 | 确认前零副作用 | 测试断言无文件写入 |
| R5 | 同步禁写原文 / baseline / production_candidate | 禁写路径测试 |
| R6 | 同步产物：TM / glossary / character / fix plan / revised output / audit report 齐全 | 端到端 fixture 演练 |
| R7 | 局部重译计划可被调度器消费 | task planner 测试 |

## 10. Local scheduler 完成标准

| # | 条件 | 验证方式 |
| --- | --- | --- |
| L1 | status 输出规格 §9.2 全部 13 字段 | `local_scheduler_status.py --json` |
| L2 | tick 每次只执行一个主任务并干净退出 | `test_local_scheduler_tick.py` |
| L3 | pause file 生效时不启动真实 API | 专项测试 |
| L4 | lock 互斥 + stale 安全清理 | `test_scheduler_control.py` |
| L5 | tick 结束 no orphan worker | tick 后置检查 + CLEAN 断言 |
| L6 | launchd install / uninstall / status 幂等 | 脚本实测记录 |
| L7 | runbook 覆盖安装 / 暂停 / 恢复 / 故障排查 | `docs/local_scheduler_runbook.md` 存在 |
| L8 | 真实 API smoke tick 成功记录在案 | FS-007 报告 |

## 11. Production candidate 完成标准

| # | 条件 | 验证方式 |
| --- | --- | --- |
| P1 | `production_candidate/` 生成且章节完整 | 目录核对 = 613 |
| P2 | `production_candidate_metadata.json` 含版本链哈希 | schema 校验 |
| P3 | `production_candidate_go_decision.md` 存在且引用 Phase E 报告 | 文件核对 |
| P4 | 写保护生效 | 同 baseline 测试方式 |
| P5 | 未标记 human_approved_final | metadata 字段 = false / 缺省 |
| P6 | 未对外发布 | 无发布动作记录 |
| P7 | 正文未入 Git | `git status` + agent_gate ignore 检查 |
