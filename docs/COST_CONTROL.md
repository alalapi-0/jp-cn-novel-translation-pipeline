# Cost Control

AI spend guards for translation pipeline and agent tooling.

## Defaults (Agent Layer)

- `allow_real_api: false` in `agent_layer.yaml`
- Agent rounds use dry-run scripts only
- No Stitch real generation unless `STITCH_API_KEY` intentionally set

## Pipeline controls

- `model-router` centralizes provider calls
- `MAX_TEST_COST_USD` caps smoke tests
- `scripts/run_real_api_smoke.py` — status-only without keys
- `scripts/run_openrouter_smoke.py --dry-run` — gate-friendly

## Agent obligations

1. Before real API change: search current pricing (official docs)
2. Log estimated cost in round report `risks`
3. Never raise caps silently
4. Prefer mock/fixtures in tests

## Ledger / reporting

- Real API summaries → `.agent_runtime/real_api_reports/` (not committed by default)
- Round report should note if real API was used (should be `false` for Layer rounds)

## Translation batch runs

- Micro-round scripts should respect run metadata cost fields
- Continuous translation handoff docs in `workspace/handoff/` — local only

See also `docs/api_provider_strategy.md`, `model-router/README.md`.
