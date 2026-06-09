# Environment flags audit (AL-024)

Date: 2026-06-09  
Scope: Agent Layer dry-run defaults vs README / AGENT_SAFETY

| Variable | README | AGENT_SAFETY / agent_layer | agent_gate |
|----------|--------|----------------------------|------------|
| `REAL_API_TESTS_ENABLED` | Documented; default off | `allow_real_api: false` | **FAIL** if set during gate (AL-025) |
| `MAX_TEST_COST_USD` | Documented | Cost guard default 0 | Not read by gate |
| `MAX_TOKENS_PER_RUN` | Referenced in roadmap | CostGuard | Not read by gate |
| `OPENROUTER_API_KEY` | Via `.env` (not committed) | Never read by agent scripts | N/A |

**Alignment:** README and `docs/AGENT_SAFETY.md` agree — agent rounds stay dry-run; real API only via explicit human-approved scripts (`run_real_api_smoke.py --real`).

**Gap (P3):** `MAX_TOKENS_PER_RUN` not mentioned in README table — optional follow-up.
