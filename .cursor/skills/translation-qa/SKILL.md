---
name: translation-qa
description: Run deterministic translation quality review, interpret issue reports, and guide human review on the Workbench. Use when checking terminology consistency, segment alignment, refinement diffs, review issues, glossary violations, or before marking chapters final.
---

# Translation QA

## When to use

- User asks for quality review, terminology check, or issue triage on segments/glossary fixtures
- Before export/final on translated chapters (dry-run or pilot)
- After draft/refine pipeline runs — validate machine checkers before human sign-off
- Workbench `issues.html` / `review.html` verification tasks

## Defaults (agent rounds)

- **No real API** — use deterministic checkers and synthetic fixtures unless user explicitly enables real API
- **Do not auto-fix** translated text from issue reports; issues are advisory
- **Do not read/print `.env`**
- Locked glossary terms: report `LOCKED_TERM_VIOLATION`; never silently rewrite target text

## Quick commands

```bash
# Deterministic review on default fixtures (stdout)
python3 scripts/run_quality_review.py

# Write example report + validate schema
python3 scripts/run_quality_review.py --write-example

# Custom fixtures
python3 scripts/run_quality_review.py \
  --segments data/examples/segments.fixture.json \
  --glossary data/examples/glossary.fixture.json \
  -o /tmp/issue_report.json

# Workbench workspace report path
python3 scripts/run_quality_review.py --workspace
```

Exit codes: `0` = issues found (review needed), `1` = no issues, `2` = validation error.

## Issue taxonomy

Use stable labels from `docs/translation_quality_taxonomy_reference_inspired.md`. Common machine tags:

| Tag | Meaning |
|-----|---------|
| `LOCKED_TERM_VIOLATION` | Glossary locked term mismatch |
| `INCONSISTENT_TERM` | Term drift vs glossary |
| `SEGMENT_ALIGNMENT_ERROR` | Segment id / pairing mismatch |
| `OMISSION` | Suspected missing translation (heuristic) |
| `OVER_REFINEMENT` | Draft vs refined surface drift |

Schema: `data/schemas/review_issue.schema.json`  
Example: `data/examples/review_issue_report.example.json`

## Human review workflow

1. Run deterministic review → JSON report
2. Open Workbench: `npm run dev:frontend` → `http://127.0.0.1:5174/issues.html`
3. Confirm REAL_API / MOCK / DRY_RUN indicators if API-backed
4. Triage by severity; high+ blocks final export unless human confirms (see workflow doc)
5. Status changes in UI → localStorage only; **does not** overwrite `human_edited` segments

Full process: `docs/quality_review_workflow.md`

## UI verification (when changing review UI)

1. Start dev server
2. Browser snapshot of issues/review pages
3. `npm run test:ui` if specs touch workbench routes
4. Notes in `artifacts/` (not committed)

See `docs/USER_VIEW_TESTING.md` and `.cursor/rules/user-view-testing.mdc`

## Related code

| Path | Role |
|------|------|
| `src/quality_review/checkers.py` | Deterministic checkers |
| `src/quality_review/runner.py` | Orchestration + schema validate |
| `scripts/run_quality_review.py` | CLI entry |
| `frontend/issues.html` | Issue list UI |

## Docs pointer

Human-readable skill index: `docs/agent_skills/translation_qa_skill.md`
