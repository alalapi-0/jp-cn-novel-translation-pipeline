# Translation Consistency Protocol

Status: current protocol for full-book consistency governance.
Created: 2026-06-18.
Applies to: any future JP_TO_CN or CN_TO_JP novel project that wants the same deterministic consistency effect. Pair with `docs/translation_production_protocol.md` for the translation execution path.

## 1. Purpose

This protocol turns the current full-book consistency work into a repeatable process for future agents and future works.

The goal is not to memorize this novel's names. The goal is to preserve the method:

1. Treat current source segments and current target segments as the factual base.
2. Treat glossary, character profile, old QA reports, and round notes as hints until revalidated.
3. Build source-conditioned rules only when evidence supports them.
4. Dry-run before apply.
5. Finish with a zero-change dry-run and one canonical final translation file.

## 2. Authority Order

When consistency evidence conflicts, use this order:

1. Original source segment for the same `segment_id`.
2. Current canonical target segment selected by the latest canonical run discovery.
3. Locked and user-approved glossary or character profile entry.
4. Current structured consistency report.
5. Older CA/Round reports.
6. Free-form notes.

Old reports can explain why a rule exists, but they are not proof that the current text is wrong.

## 3. Required Inputs

For each work:

- source chapter files or parsed source segments;
- canonical segment store with stable `chapter_id`, `paragraph_id`, and `segment_id`;
- glossary with `source_term`, `target_term`, `aliases`, `locked`, `approved_by_user`, `category`;
- character profile with source names, target names, aliases, forbidden variants, voice notes;
- optional world bible and style profile;
- ignored local workspace for generated reports and patch logs.

For this repository, the implementation reads canonical segments through `run_consistency_fix_all.discover_canonical_files()`.
For a new work, implement an equivalent resolver before writing any fix rule.

## 4. Progressive Disclosure Workflow

Use this order. Do not start by expanding or loading the full book into model context.

1. Level 0: manifest and chapter coverage.
2. Level 1: segment index and entity/glossary registry.
3. Level 2: conflict statistics, residual counts, and variant buckets.
4. Level 3: expand only conflict segment IDs and short references.
5. Level 4: model arbitration only for unresolved high-impact conflicts under explicit budget.
6. Level 5: source-conditioned local fix, retranslation, or human decision.

Every report must state how many items reached each level.

## 5. Rule Admission Criteria

A replacement rule may be automatic only when all conditions are true:

- The rule has a source guard: the relevant source term or source phrase occurs in the same segment.
- The target-side variant is unambiguous in that source context.
- The canonical replacement is locked, approved, or explicitly decided by the user.
- The rule does not rewrite an accepted contextual rendering.
- The rule is idempotent: a second dry-run reports 0 changed segments.
- The rule preserves segment boundaries and does not alter source text, human-edited text, or legacy baseline body snapshots.

If any condition is false, write a review issue or deferred decision instead of a replacement rule.

## 6. Denylist and Suppression Rules

Keep two separate concepts:

- `AUTO_FIX_DENYLIST`: target surfaces that should remain visible in reports but must never be mechanically rewritten.
- Contextual suppression: source/target pairs that are correct in context and should not become glossary aliases.

Do not put natural contextual renderings into glossary aliases just to silence a checker. That turns a local exception into a global replacement rule.

Examples of contextual categories that need suppression rather than replacement:

- common words that also occur inside names;
- honorific or nickname forms;
- forum/player handles that should be romanized;
- species or role names whose Chinese rendering depends on nearby nouns;
- in-world opaque literals or mojibake that intentionally survive in both source and target;
- source phrases whose target is idiomatic rather than literal.

## 7. Checker Expectations

At minimum, future projects need these deterministic checks:

- chapter coverage and missing chapter check;
- segment alignment and orphan segment check;
- target source-language residual check;
- placeholder or replacement-character residual check;
- locked term violation check;
- name/term variant report;
- old workbench/export duplicate check;
- final singleton export check.

The checker output should be structured JSON with counts, segment IDs, and short references only. Do not store full real text in tracked reports.

## 8. Fix Execution Protocol

Use this sequence for every full-book consistency pass:

1. Run current actual-content audit.
2. Run current term/name variant report.
3. Run fixer dry-run and write a diff log.
4. Review non-zero changes for overbroad aliases.
5. Apply only high-confidence source-conditioned fixes.
6. Run fixer dry-run again.
7. Repeat until dry-run changed segments = 0.
8. Re-run actual-content audit and variant report.
9. Export singleton final translation.
10. Run final singleton check.
11. Write final report and append agent audit log.
12. Clean old round logs and stale exported copies. Preserve runs, checkpoints, source, patch logs, and legacy baseline history unless the user explicitly asks to remove obsolete baseline body text from the current workspace.

For this repository, the command shape is:

```bash
python3 scripts/audit_actual_chapter_content.py --chapters 1 612
python3 scripts/build_term_variant_report.py --chapters 1 612
python3 scripts/run_consistency_fix_all.py --dry-run
python3 scripts/run_consistency_fix_all.py
python3 scripts/export_consistency_final_volume.py --json
python3 scripts/check_final_translation_singleton.py --json
python3 scripts/finalize_consistency_run.py --cleanup-round-logs --json
```

New projects should keep the same command semantics even if filenames differ.

## 9. Final Artifact Rule

The final translation handoff must have exactly one canonical target text file.

For this repository:

- canonical final translation: `output_cn/translated/full_volume_cn.md`;
- manifest: `output_cn/final_export_manifest.json`;
- singleton check: `reports/final_translation_singleton_check.json`.

Per-chapter files, bilingual exports, Workbench exports, old CA logs, and round logs are regenerable working artifacts. They must not be presented as final versions.

If a project needs bilingual or per-chapter output, generate it with explicit flags and mark it as auxiliary, not as the canonical final translation.

## 10. Safety Rules

Agents must not:

- read or print `.env`;
- call real API during a governance consistency pass;
- auto-mark `human_approved_final`;
- overwrite source, human_approved_final, human-edited text, or legacy baseline body snapshots;
- delete runs, checkpoints, patch logs, or review history;
- commit real source text or real translation text;
- use old reports as the factual base for new fixes;
- add broad aliases from a single local exception.

Agents may:

- clean generated round logs after writing a final report;
- delete stale exported copies under ignored output directories;
- update scripts, docs, manifests, and tracked summary reports;
- archive or disable legacy launchers that bypass current scheduler gates.

## 11. New Work Bootstrap Checklist

Before translating a new work, create or adapt:

- stable chapter and segment ID rules;
- canonical segment resolver;
- locked glossary and character profile schema;
- source residual checker for the target language;
- placeholder checker;
- term/name variant report;
- source-conditioned fixer with denylist and suppression support;
- singleton final export manifest and checker;
- final consistency report template.

Do not copy this novel's actual names or replacements to a new work. Copy only the workflow, schemas, checker categories, and guardrails.

## 12. Done Criteria

A consistency pass is done only when:

- fixer dry-run changed segments = 0;
- target source-language residual count = 0 or all residuals are documented protected literals;
- placeholder/replacement-character residual count = 0;
- term variance count = 0 for locked/approved terms;
- unrecognized variant count = 0 or all remaining items are deferred with segment IDs;
- singleton final translation check passes;
- final report exists;
- audit log was appended;
- no active or orphan worker exists;
- no real API was called unless the round explicitly authorized it.
