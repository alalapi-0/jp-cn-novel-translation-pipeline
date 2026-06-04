# Phase 2 路线图（Round 51+）

Round 41–50 已在合成样章上验证工具链；Phase 2 在用户授权与预算内推进**受控真实 API**、长篇试点与语义 checker 硬化。

## Round 51：OpenRouter 冒烟 + 日语漏译启发式

### 目标

- `scripts/run_openrouter_smoke.py`：单次低成本连通性验证（默认 dry-run；双开关开启时真实调用）。
- 强化 `checker.segment_alignment` 的 `OMISSION` 启发式：日文/混合 CJK 用字符长度而非西方分词。
- 更新 `governance/round_state.yaml` 进入 Phase 2。

### 验收

- `python3 scripts/run_openrouter_smoke.py` 在 dry-run 下 exit 0。
- 真实 API（若本地 Key + `REAL_API_TESTS_ENABLED`）单次花费 ≤ `MAX_TEST_COST_USD`。
- `pytest tests/test_quality_review_checkers.py tests/test_openrouter_smoke.py` 通过。
- `agent_gate` PASS/WARN；Playwright smoke 仍绿。

## Round 52：Stage C 受控润色试跑

### 目标

- `scripts/refine_stage_c.py`：小批量 refine（`REFINE_MODEL`），`human_edited` 保护，硬上限 30 段/次。
- 产物：`refine_diff.json`、`refine_quality_report.json`；`workspace/stage_state.json` 进入 `phase=refine`。

### 验收

- `refine_stage_c.py --dry-run` exit 0（本地存在 Stage B run 时）。
- `pytest tests/test_refine_stage_c.py` 通过。
- 可选真实 API 试跑 ≤ `MAX_TEST_COST_USD`。

## Round 53（建议）：多项目 manifest 后端

- `workspace/manifests/` 多 `project_id`；`workspace/workbench_state.json` 记录当前项目。
- `scripts/serve_frontend.py` 暴露 `/api/projects` 与项目切换；Workbench 首页/审核页可切换。
- `data/examples/workbench_project.*.example.json` 为可提交样例；gate 自动 seed 到 workspace。

### 验收

- `pytest tests/test_multi_project_manifest.py` 通过。
- `agent_gate` 含 `round_53_*` 检查项 PASS/WARN。
- Playwright smoke 仍绿（双项目卡片可见）。

## Round 54：语义 checker MVP

- `src/quality_review/checkers.py`：`check_mistranslation`（日源否定 vs 中译肯定动作）、`check_placeholder_lost`（`{{}}` / URL / `{PH_*}`）。
- `src/quality_review/workbench_adapter.py` + `GET /api/projects/{id}/quality-review`。
- 前端 `fetchIssueReport` 优先 API，静态 JSON 回退；fixture `seg-004`/`seg-005` 可复现。

### 验收

- `pytest tests/test_semantic_checkers.py tests/test_quality_review_checkers.py`
- `agent_gate` 含 `round_54_*` PASS/WARN。
- Playwright smoke 仍绿（issues/review 无 console error）。

## Round 55：CI 工具链集成

### 目标

- `.github/workflows/ci.yml`：`check:tooling` 在 push/PR 上必跑；`test:ui` 在 main push 与 `workflow_dispatch` 可选开启（PR 默认仅 tooling）。
- `scripts/run_tooling_checks.sh` 在 `CI=true` 时强制 `REAL_API_TESTS_ENABLED=false`。
- `agent_gate` 含 `round_55_*` 检查项。

### 验收

- `npm run check:tooling` exit 0 或 1（无 BLOCKED）。
- `npm run check:mcp` 可 WARN（无 token 不阻塞）。
- `agent_gate` 含 `round_55_ci_workflow_exists` PASS。
- 本地 `npm run test:ui` 仍绿（非 CI 硬阻塞）。

## 安全与成本

- 不得提交 `.env`、真实原文/译文、API Key。
- 所有真实调用须 `REAL_API_TESTS_ENABLED` + `MAX_TEST_COST_USD` + 用户授权范围。
- 产物默认落在 `workspace/`（gitignore）。
