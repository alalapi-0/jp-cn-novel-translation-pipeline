# Round 51：Phase 2 — OpenRouter 冒烟与 OMISSION 启发式

## 轮次类型

implementation + controlled_api_validation

## 目标

1. 添加 `scripts/run_openrouter_smoke.py`（dry-run 默认；真实 API 需双开关）。
2. 改进 `OMISSION` checker：JP_TO_CN / 含假名汉字原文用字符长度比较。
3. 编写 `docs/roadmap_phase2_rounds_51_plus.md` 并更新 `governance/round_state.yaml`。

## 验收

- agent_gate PASS 或 WARN 已记录
- smoke 脚本 dry-run exit 0
- 相关 pytest 通过
- Playwright smoke（换端口若占用）
- git diff 无密钥与未授权正文

## 不做

- 全书批量翻译
- 无预算真实 API
- 提交 workspace 运行产物
