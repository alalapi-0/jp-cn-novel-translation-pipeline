# Light-novel approval binding contract

`ALL-PROJECTS-CODEX-GOVERNANCE-V1-LIGHT-NOVEL-APPROVAL-BINDING-v1` — GOVERNED.
Read-only Governor `/root/hub_connection_governor` established this contract under the existing Goal.
Base: `main@77e4b57ca2baa67f0646b72c7d28823d4a683a7a`; repository `alalapi-0/jp-cn-novel-translation-pipeline`.

## Frozen objective

Bind formal segment approval to exact project ID, segment ID, language direction, source and target content. Existing project write lock performs compare-and-set against a client-supplied expected identity. Manifest export and manifest translation-memory consumers use the same binding. Repair the sole governance state, establish a Codex-only offline gate route, and add a truthful Hub 2.0 declaration. Implementation paths, helpers, schemas and tests remain adaptive.

## Boundaries and ownership

Write only this isolated worktree. Original checkout remains read-only, preserving dirty consistency/runtime/storage/prompt/helper work. No .cursor, .env, credentials, real corpus/raw translations, original/baseline/final text, real queues/checkpoints/run artifacts or unrelated runtime state access or mutation. Scheduler remains paused; no translation, refinement, paid API, publishing or revival of completed export task 01a07f3d-aafc-7472-a8e9-4fd2c16bd32f. Run-level translation memory is a separate unchanged authority; do not claim manifest guarantees there. No Hub or global Codex writes in this unit; later Hub scope handles registry/projections.

Root owns control planes, state, evidence, candidate identity and Git. A Repair writer may receive disjoint bounded application/frontend/test files and must preserve other writers. No descendants without Root dispatch. Only normal exact-candidate delivery to verified remote main is authorized after fresh Judge PASS and Governor approval; no force, protection bypass, history rewrite, unrelated merge or original main update.

Governor clarification: fresh disposable test fixtures under temporary roots or ignored isolated paths are allowed; they must not read real payload or escape to original. An ignored worktree-local .venv and scoped cache using requirements-dev.txt are allowed. Package retrieval is read-only external access, with no global/installed runtime changes or staged dependencies. Standalone gate with bounded synthetic fixtures and task-owned reviewed reports is allowed. Do not invoke excluded Cursor/tool probes. This is v1 interpretation, not a contract/attempt/budget reset.

## Acceptance

1. Formal approval requires valid client expected identity equal to the currently locked manifest segment.
2. Unchanged A remains approved; same-ID B is rejected/omitted by manifest export and TM until fresh B approval.
3. Source, target, language, project or segment identity changes cannot inherit approval. Stale requests cannot overwrite newer content; fresh requests succeed.
4. Manifest and approval writes are atomic under existing project lock; concurrent stale CAS fails without partial writes or lost updates.
5. Both manifest consumers use the same approval rule and select the same approved segment set. Embedded approved status, legacy unbound approval and stale fallback never grant formal approval.
6. Preserve legacy notes/non-formal history and identify reapproval need. Reject duplicate segment IDs before lookup/export/TM and cross-project inheritance.
7. API failures are actionable; frontend never represents failed approval as formally accepted. Synthetic real-browser before/after covers unchanged A, changed B, rejected stale request and fresh B, with clean relevant console/network.
8. Original raw material, exports, scheduler pause, queues and unrelated dirty work remain unchanged.
9. governance/round_state.yaml is strict alias/anchor-free valid YAML; preserve history, truthfully record this unit and one next action, do not advance old rounds.
10. Codex startup/gate does not require Cursor or .cursor; offline runtime/repository/CI checks remain callable without weakened quality requirements.
11. hub.connection.yaml uses stable light-novel ID, sole governance/round_state.yaml source, typed Hub2.0 mappings, explicit unknowns, independent completed/accepted/delivered, no invented denominator. Validate/read locally without Hub mutation, traversal, project command execution, secrets or network.
12. Targeted and normal required checks pass; only independently established pre-existing failures may remain where acceptance is unaffected. Register original preimages, exact candidate, commands/exits/browser/preservation, fresh Judge then Governor decision.

## Evidence and delivery

Register base/remote/permission facts and original dirty paths. Run approval/API/export/manifest-TM/duplicate/legacy/cross-project/lock/concurrency regressions, npm run test:py, npm run test:ui, applicable repo/protocol checks, strict YAML, Hub declaration validation and git diff --check. Sequential read-only scheduler/orphan/singleton checks where usable must not mutate actual runtime. Exact semantic hash excludes decision/delivery metadata; no self-hash loop. Reverify remote/candidate before normal main delivery, then remote ancestry and CI.

Forward repair only; no original reset/clean/whole-branch merge. Necessary dirty fragments may be imported only with proven ownership and inverse preservation; otherwise implement independently. Same cumulative Goal budget/history applies; no explicit cap or cost telemetry. Reserve verification, review and delivery capacity. No partial-project or global completion claim.
