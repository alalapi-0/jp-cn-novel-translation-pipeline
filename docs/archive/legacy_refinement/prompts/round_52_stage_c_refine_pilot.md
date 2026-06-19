# Round 52：Stage C 受控润色试跑

## 轮次类型

implementation + controlled_api_validation

## 目标

1. `scripts/refine_stage_c.py`：在 Stage B 草稿完成后小批量润色（`REFINE_MODEL`），默认 `--limit-segments 12`。
2. `src/translation/refine_runner.py`：跳过 `human_edited`、已润色段；写入 `refine_diff.json` 与 `refine_quality_report.json`。
3. 更新 `workspace/stage_state.json`：`phase=refine`，`refine_blocked=false`（试跑完成时）。

## 验收

- `refine_stage_c.py --dry-run` exit 0（本地有 Stage B run 时）
- `pytest tests/test_refine_stage_c.py` 通过
- 可选真实 API：`REAL_API_TESTS_ENABLED` + Key，花费 ≤ `MAX_TEST_COST_USD`
- `agent_gate` PASS/WARN
- git diff 无密钥与未授权正文

## 不做

- 全书批量润色
- 提交 `workspace/.locks/` 或运行产物正文
