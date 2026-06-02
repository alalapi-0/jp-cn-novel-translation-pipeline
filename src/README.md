# src

Provider adapter 与 cost guard 实现（Round 47+）。

- `providers/fake_provider.py` — 固定响应，无 network
- `providers/dry_run_provider.py` — 记录 request，不发 network
- `providers/cost_guard.py` — token 估算、budget ceiling、超限 abort
- `providers/controlled_run.py` — 受控试跑开关与 checkpoint
- `providers/registry.py` — `get_provider(ProviderMode)`
