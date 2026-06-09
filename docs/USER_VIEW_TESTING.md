# User-View Testing

Validation from the user's perspective — not code-only inference.

## Project type

Web workbench (static frontend + Python API) for translation review, quality issues, multi-project manifests.

## Static checks (no server)

```bash
python3 scripts/user_view_test.py
```

Verifies frontend files exist, playwright config, optional HTTP if port 5174 open.

## Full UI flow

### 1. Start server

```bash
npm run dev:frontend
# http://127.0.0.1:5174/
```

### 2. Browser tools (Cursor foreground Agent)

- Navigate to home, review, issues pages
- Snapshot visible content
- Check console errors
- Check failed network (API paths under `/api/`)
- Narrow viewport optional

### 3. Automated E2E

```bash
npm run test:ui
```

### 4. Inspection script

```bash
python3 scripts/run_browser_inspection.py
```

## Translation pipeline user-view (non-UI)

| Check | Command / artifact |
|-------|-------------------|
| Dry-run smoke | `python3 scripts/run_real_api_smoke.py` |
| E2E trial | `python3 scripts/run_round_50_e2e_trial.py` |
| Quality review | `python3 scripts/run_quality_review.py --segments data/examples/...` |
| Chapter completeness | segment JSON schema + manifest |
| Terminology | glossary fixtures + review UI |
| Resume | run metadata / `scripts/agent.py status` |
| Cost | dry-run ledger; no real API in agent rounds |

## Before / after

Store notes under `artifacts/` (gitignored): screenshot paths, console summary, network failures.

## When blocked

- Dev server down → start server, retry
- Browser MCP missing → `BLOCKED: MISSING_FROM_THREAD_TOOL_REGISTRY`
- Playwright browsers missing → `npx playwright install`

## Related

- `docs/cursor_browser_ui_runbook.md`
- `docs/testing/BROWSER_TESTING.md`
- `.cursor/rules/user-view-testing.mdc`
