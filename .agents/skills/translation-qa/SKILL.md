---
name: translation-qa
description: Run deterministic translation quality review, interpret issue reports, and guide human review on the Workbench. Use when checking terminology consistency, segment alignment, refinement diffs, review issues, glossary violations, or before marking chapters final.
---

# Translation QA (Codex stub)

> **AL-028 stub.** Canonical project skill: `.cursor/skills/translation-qa/SKILL.md`  
> Docs index: `docs/agent_skills/translation_qa_skill.md`

Read the canonical skill file in this repository for full workflow. Codex sessions should:

1. Read `docs/quality_review_workflow.md` and `docs/AGENT_SAFETY.md`
2. Run `python3 scripts/run_quality_review.py --write-example` on fixtures (no real API)
3. Never auto-apply fixes from issue reports to human_edited segments
4. Log tool usage in `reports/latest-agent-report.json` when running agent rounds

Do not duplicate skill body here — keep single source in `.cursor/skills/translation-qa/SKILL.md`.
