# Agent Safety

Default-deny rules for autonomous agents in `light_novel`.

## Hard denies (P0 if violated)

- Leak API keys, cookies, tokens, `.env` contents
- Commit real novel source or unauthorized translations
- Force push, hard reset without user approval
- Real publish to external platforms
- Real paid API calls without explicit env + user intent
- Delete user data or `input_*` originals
- Disable tests or gates to fake success
- Filesystem MCP outside workspace root

## Soft denies (require user confirmation)

- git commit
- git push
- PR create/merge
- Enabling `REAL_API_TESTS_ENABLED`
- Increasing cost caps
- Stitch/API design generation (cost)

## Environment flags (reference only — do not read `.env`)

| Flag | Meaning |
|------|---------|
| `REAL_API_TESTS_ENABLED` | Allows small real API smokes |
| `MAX_TEST_COST_USD` | Cost ceiling |
| `OPENROUTER_API_KEY` | Provider auth |

Scripts read env at runtime; agents must not print values.

## Translation pipeline

- Dry-run / mock default for agent governance rounds
- `governance/novel_pipeline_contract.yaml` is authoritative for pipeline safety
- Workbench shows REAL_API / MOCK / DRY_RUN modes — do not hide mode indicators

## Incident response

1. Stop further API/publish commands
2. Record in `reports/latest-agent-report.json` blockers
3. `python3 scripts/agent.py block --reason "..."` if using continuous agent
4. Notify user with severity P0/P1

## Related

- `docs/COST_CONTROL.md`
- `docs/agent_operating_manual.md` §5.4
- `governance/agent_policy.yaml`
