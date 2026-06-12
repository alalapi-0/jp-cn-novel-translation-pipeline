# Phase D Handoff — R-MR 润色推进

> FS-039 产物 · baseline go **GO** · Phase C 完成 → S8 启动  
> 锚点：`docs/product_final_state_spec.md` §15 · `docs/translation_recovery_3ch_task_list.md`

## 1. 队列起点

| 项 | 值 |
|----|-----|
| 首个 micro round | **R-MR-001** |
| 章节范围 | **171–173** |
| 队列规模 | **148** 轮（R-MR-001 … R-MR-148） |
| 待润色章节 | 442 章（ch171–612；历史 refined ch1–170 保留） |
| 每轮章数 | 3（末批可能不足 3 章） |
| 输入基线 | `draft_full_baseline/`（只读，aggregate hash 见 go decision） |
| 调度 phase | `refinement`（`collect_status` 在 go decision GO 后切换） |
| 执行入口（规划后） | `scripts/run_micro_round.py --phase refine`（FS-041 落地） |

### R-MR 编号公式

```
chapter_start = 171 + (N - 1) * 3
R-MR-N 覆盖 [chapter_start, min(chapter_start + 2, 612)]
```

完整列表见 `docs/translation_recovery_3ch_roadmap.md` §3.5。

### 调度器配置（可选覆盖）

`workspace/control/scheduler_queue.json`：

```json
{
  "rmr_anchor_chapter": 171,
  "chapters_per_round": 3
}
```

---

## 2. 模型 Profile

生产润色主力（`configs/model_profiles.yaml`）：

| 字段 | 值 |
|------|-----|
| profile_id | `refine_primary` |
| role | refine |
| provider | model_router |
| model | `deepseek/deepseek-v4-pro` |
| temperature | 0.4 |
| fallback | `deepseek/deepseek-chat` |
| cost_guard | max $1.5/round · max 200 API calls/round |

**注意**：

- FS-039 **未调用真实 API**；FS-044 首 1–2 个 R-MR 验证后才批量推进。
- 更强模型 / 提价 / 并发变更需用户确认（`AGENTS.md`）。
- 润色 prompt 约束：**不得重新翻译**；输入严格来自 baseline（只读）。

---

## 3. Checker 清单（R-MR 收尾自动执行，FS-043 落地）

每个 R-MR 完成后须跑三 checker（`scripts/check_refinement_quality.py`，待 FS-043）：

| Checker | 检查内容 | Blocking 条件（草案） |
|---------|----------|----------------------|
| **over-refinement** | baseline vs refined diff 比例 / 长度膨胀 | 超阈值 segment 比例 > 配置上限 |
| **terminology preservation** | locked glossary 术语在 refined 中不被改写 | 任一 locked 术语被替换 |
| **character voice** | character_profile 关键标记词 / 语气特征保持 | 关键标记词丢失或统一化 |

### 伴随产物（FS-042）

- segment 级 **diff**（`build_refine_diff.py`）
- 结构化 **change_log**（修改类型 + 比例统计）
- round report：`workspace/round_reports/R-MR-NNN/`

### Phase D 完成闸门（FS-045）

对照 `docs/phase_acceptance_criteria.md` §4（D1–D9）：全书 refined、三 checker 无 blocking、baseline 哈希不变、orphan CLEAN。

---

## 4. 并行非阻塞工作

| 工作流 | 状态 | 说明 |
|--------|------|------|
| source_residual 重译 | 1055 segments 剩余 | `run_consistency_retranslate.py`；不阻塞 R-MR |
| baseline 写保护 | 已启用 | refine 不得写 `draft_full_baseline/` |

---

## 5. FS-040 就绪检查

| 前置 | 状态 |
|------|------|
| go decision GO | ✅ |
| scheduler `current_phase=refinement` | ✅（go decision 文件存在后） |
| task_planner R-MR 分支 | ✅ FS-040（`refine_micro_round` 已实现；命令 `run_micro_round --phase refine`） |
| refine micro round runner | ✅ FS-041（`run_micro_round --phase refine` supervised + checkpoint） |
| diff / change_log | ✅ FS-042（`build_refine_diff.py` → run 目录） |
| 三 checker | ⏳ FS-043 |
| 真实 API 首验 | ⏳ FS-044 |

**推荐下一 FS 轮**：FS-040 — `plan_refine_micro_rounds.py` + task planner R-MR 分支 + dry-run 首个 R-MR 批次计划。
