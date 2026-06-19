# Phase Acceptance Criteria

> 阶段验收标准（v2.0，2026-06-18）。锚点：`docs/product_final_state_spec.md` v2.0。
> 所有条目必须可检查：以命令输出、报告文件、测试结果或 Playwright 断言为证据。

## 1. Phase A：全书翻译完成标准

| # | 条件 | 验证方式 |
| --- | --- | --- |
| A1 | 全部编号章存在 translation / draft 输出 | `phase_a_completion_check.py --json` 或等价章节计数 |
| A2 | 全部 segment status=completed | 运行进度 / segments 统计 |
| A3 | failed segment = 0 | 同上 |
| A4 | blocking validation_failed = 0 | 同上 |
| A5 | 无章节错位 / 无漏段 | `audit_draft_structure.py` 或一致性报告 |
| A6 | checkpoint 完整可续跑 | 抽样 run 的 checkpoint hydrate 测试通过 |
| A7 | round reports 完整 | `workspace/round_reports/` 或 latest report |
| A8 | no active / orphan worker | `check_orphan_workers.py --json` decision=CLEAN |
| A9 | 执行模式记录明确 | run metadata 含 `api_translation` / `agent_quota_translation` / mock / dry_run |

## 2. Phase B：一致性检查完成标准

| # | 条件 | 验证方式 |
| --- | --- | --- |
| B1 | chapter manifest 已构建且覆盖全部编号章 | `build_chapter_manifest.py --json` 或等价报告 |
| B2 | segment index 已构建 | `build_segment_index.py` 输出存在且漏段=0 |
| B3 | entity / term index 已构建 | entity / term report 存在 |
| B4 | glossary 冲突已统计 | glossary conflict / term variant report 可复现 |
| B5 | blocking conflicts = 0 | 报告 blocking 计数 = 0 |
| B6 | 必要局部修正 / 重译已完成 | local fix plan 全项 closed 或 dry-run changed=0 |
| B7 | 一致性报告完整 | `docs/final_consistency_report.md` 或对应作品报告 |
| B8 | progressive disclosure 合规 | 报告记录 Level 展开；Level 4 调用数受预算限制 |

## 3. Phase C：singleton final export 完成标准

| # | 条件 | 验证方式 |
| --- | --- | --- |
| C1 | Phase A、B 验收全部 PASS | 两份核对表或最终一致性报告 |
| C2 | canonical segments 已完成必要一致性修正 | `run_consistency_fix_all.py --scope all-runs --update-all-target-fields --dry-run` changed=0，或对应 final-only dry-run changed=0 |
| C3 | 唯一最终译文生成 | `output_cn/translated/full_volume_cn.md` 存在 |
| C4 | final export manifest 指向唯一最终译文 | `output_cn/final_export_manifest.json` schema v2 |
| C5 | singleton check PASS | `python3 scripts/check_final_translation_singleton.py --json` |
| C6 | no active / orphan worker | `check_orphan_workers.py --json` CLEAN |

## 4. Web UI MVP 完成标准

| # | 条件 | 验证方式 |
| --- | --- | --- |
| U1 | Dashboard / 项目设置 / API-Agent 设置 / Pipeline 控制台 / 章节 / 术语库 CRUD / 报告 / 导出入口可用 | Playwright spec |
| U2 | Dashboard 显示 current phase / next task / active worker / orphan / final translation 状态，且与 `local_scheduler_status.py --json` 一致 | Playwright 断言 |
| U3 | 控制台可暂停 / 恢复，pause file 真实写入 | Playwright + 文件断言 |
| U4 | 术语库 CRUD + 三格式导入导出可用 | Playwright + roundtrip 测试 |
| U5 | 全部页面接入统一布局壳与设计系统 | grep / screenshot |
| U6 | 危险操作全部二次确认 | Playwright 断言 confirm 流程 |
| U7 | 界面中文优先 | 抽样页面无未翻译英文主文案 |
| U8 | 无未解释 console 错误；关键 API 请求正常 | 浏览器检查记录 |
| U9 | API Key 永不明文出现在 DOM / 响应 | Playwright network 断言 |

## 5. Web UI Final 完成标准

| # | 条件 | 验证方式 |
| --- | --- | --- |
| F1 | 规格 §8 的主页面全部实现 | 导航无置灰占位 |
| F2 | 对照页支持原文 / 译文 / 用户修改稿模式 | Playwright spec |
| F3 | 上传 → 对齐 → diff → sync plan → 确认 → 同步 旅程可走通（fixture） | 跨页旅程测试 |
| F4 | 导出页可导出 singleton final translation 与辅助包 | Playwright spec |
| F5 | 标准状态标签全站统一 | 审计报告 P1=0 |
| F6 | 1280 / 1024 视口核心流程可用 | 双视口测试 |
| F7 | 键盘可达性与对比度基础达标 | a11y 基础检查 |
| F8 | `npm run test:ui` 全套通过 | CI / 本地输出 |

## 6. Glossary system 完成标准

| # | 条件 | 验证方式 |
| --- | --- | --- |
| G1 | 13 字段 + 分类 schema 校验通过 | `test_configs_schema.py` |
| G2 | CRUD / locked / approved 状态机有测试 | `test_glossary_store.py` |
| G3 | CSV / YAML / JSON roundtrip 无损 | `test_glossary_io.py` |
| G4 | locked 术语不被机器建议与导入覆盖 | 专项测试 |
| G5 | term usage index 可增量构建 | `test_term_usage_index.py` |
| G6 | prompt 注入仅含当前 batch 命中子集 | `test_prompt_builder_assets.py` |
| G7 | UI CRUD + 导入导出可用 | U4 |

## 7. User revision sync 完成标准

| # | 条件 | 验证方式 |
| --- | --- | --- |
| R1 | 未改动文本自动对齐率 100%（fixture） | `test_user_revision_align.py` |
| R2 | 对齐失败进入人工对齐而非强行覆盖 | 测试 + Playwright |
| R3 | sync plan 含规格要求字段 | plan schema 测试 |
| R4 | 确认前零副作用 | 测试断言无文件写入 |
| R5 | 同步禁写原文 / human_approved_final / legacy baseline body | 禁写路径测试 |
| R6 | 同步产物：TM / glossary / character / fix plan / revised output / audit report 齐全 | 端到端 fixture |
| R7 | 局部重译计划可被调度器消费 | task planner 测试 |

## 8. Local scheduler 完成标准

| # | 条件 | 验证方式 |
| --- | --- | --- |
| L1 | status 输出最终规格 §9.2 字段 | `local_scheduler_status.py --json` |
| L2 | completed project 状态为 `final_ready`，无 R-MR next task | `local_scheduler_status.py --json` |
| L3 | tick 每次只执行一个主任务并干净退出 | `test_local_scheduler_tick.py` |
| L4 | pause file 生效时不启动真实 API 或 Agent 翻译任务 | 专项测试 |
| L5 | lock 互斥 + stale 安全清理 | `test_scheduler_control.py` |
| L6 | tick 结束 no orphan worker | tick 后置检查 + CLEAN 断言 |
| L7 | launchd install / uninstall / status 幂等 | 脚本实测记录 |
| L8 | legacy refinement / production_candidate route 不会被 planner 执行 | `test_scheduler_task_planner.py` |

## 9. Singleton final translation 完成标准

| # | 条件 | 验证方式 |
| --- | --- | --- |
| P1 | `output_cn/translated/full_volume_cn.md` 存在 | 文件核对 |
| P2 | `output_cn/final_export_manifest.json` 指向该文件 | manifest |
| P3 | `canonical_final_translation_count = 1` | manifest |
| P4 | 无额外分章 final Markdown / old workbench bilingual final | singleton checker |
| P5 | 未标记 human_approved_final | metadata / manifest |
| P6 | 未对外发布 | 无发布动作记录 |
| P7 | 正文未入 Git | `git status` + agent_gate ignore 检查 |
