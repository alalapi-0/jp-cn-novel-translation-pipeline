# Translation QA Agent Skill

Date: 2026-06-09 (AL-010)  
Cursor skill path: `.cursor/skills/translation-qa/SKILL.md`  
Codex-compatible stub (AL-028): `.agents/skills/translation-qa/SKILL.md` (symlink or copy when needed)

## Purpose

Teach agents how to run **deterministic** translation quality review in this repo: terminology, segment alignment, refinement diff — without calling paid LLM APIs by default.

## When agents should load this

- Quality review, issue triage, glossary/terminology consistency tasks
- Pre-final checks on segment JSON fixtures or workspace review reports
- Workbench `issues.html` / `review.html` implementation or verification

## Machine skill (Cursor)

```
.cursor/skills/translation-qa/SKILL.md
```

Agents with project skills enabled should discover it via the `description` frontmatter trigger phrases.

## Core commands

```bash
python3 scripts/run_quality_review.py
python3 scripts/run_quality_review.py --write-example
python3 scripts/run_quality_review.py --workspace
```

## Authority chain

1. `docs/quality_review_workflow.md` — process and state machine
2. `docs/translation_quality_taxonomy_reference_inspired.md` — issue labels
3. `data/schemas/review_issue.schema.json` — report shape
4. `src/quality_review/checkers.py` — checker implementation

## Safety

- Issues **report only**; no auto-overwrite of human_edited segments
- Locked terms → report, do not auto-fix
- Agent Layer rounds: dry-run fixtures; real API gated per `docs/AGENT_SAFETY.md`

## UI

- Dev server: `npm run dev:frontend` → port 5174
- Issues page: `/issues.html`
- Browser rules: `.cursor/rules/user-view-testing.mdc`

## Sibling skills

| Skill | Path |
|-------|------|
| MCP usage | `docs/agent_skills/mcp_usage_skill.md` |
| Polish (novel-specific) | `.cursor/skills/polish-light-novel/SKILL.md` |

## Related roadmap

- AL-010 — this stub
- AL-028 — Codex `.agents/skills/` copy
- AL-T02 — terminology consistency report script
