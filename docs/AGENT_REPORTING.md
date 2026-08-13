# Agent Reporting

Structured outputs every round must produce or update.

## Primary artifacts

| File | Purpose |
|------|---------|
| `reports/current-cohort-report.json` | Handoff to next agent |
| `reports/latest-agent-report.json` | Protected pre-policy historical snapshot; never use as current completion/next authority |
| `reports/agent_audit_log.jsonl` | Append-only history |
| `reports/gate_result.json` | Gate summary |
| `reports/tool_probe_report.json` | Tool capability snapshot |
| `schemas/agent_round_report.schema.json` | JSON schema |

## Required fields (summary)

See schema for full list. The current schema requires the delivery-policy fields below. Only the exact protected `reports/latest-agent-report.json` path may use the pre-policy compatibility validator; a backdated current or alternate report cannot. The legacy snapshot is read-only and is not a template for new reports. Minimum:

- `round_id`, `timestamp`, `agent`, `agent_surface`, `mode`, `goal`
- `tool_probe_status`, `tools_used`, `tools_not_used`
- `gate_status`, `severity_summary`
- `next_recommended_round`, `human_decisions_required`
- current reports also require `policy_version=git_safe_cohort_delivery_v1`, `cohort_status`, and `git_delivery`. A tracked candidate report must keep `remote_sha_verified=false`; while a Git-safe cohort is pending, `next_recommended_round` must be empty.

Tracked reports cannot self-attest remote completion because doing so would create a self-referential follow-up commit. Completion authority is a fresh remote SHA lookup plus the gitignored finalizer receipt; the next cohort must reverify the prior HEAD remotely.

## tool_usage example

```json
{
  "tools_used": [
    {"tool": "shell", "purpose": "run agent_gate", "result": "warning", "fallback_used": false},
    {"tool": "web_search", "purpose": "Cursor/Codex official docs", "result": "logged in RESEARCH_NOTES", "fallback_used": false}
  ],
  "tools_not_used": [
    {"tool": "playwright", "reason": "no UI code changed this round"}
  ]
}
```

## Audit log format

One JSON object per line in `reports/agent_audit_log.jsonl`:

```json
{"timestamp":"2026-06-09T12:00:00Z","round_id":"AL-002","agent":"cursor","gate_status":"warning","summary":"Agent Layer 2.0 bootstrap"}
```

## Markdown reports

Legacy human report: `docs/reports/agent_gate_report.md` (from `agent_gate.py`).

Do not commit sensitive content in any report path.

## Validate latest report

```bash
python3 scripts/validate_agent_report.py
python3 scripts/validate_agent_report.py --json
```

Also runs directly inside the live-safe `npm run check:tooling` entrypoint. That entrypoint does not run the full `agent_gate.py`; a full gate is isolated-copy-only with no output writeback. Exit 0 = valid; 1 = schema errors; 2 = missing file or parse error.

## Audit log retention (AL-014)

| Artifact | Retention | Rotation |
|----------|-----------|----------|
| `reports/agent_audit_log.jsonl` | Keep in repo; append-only | No auto-truncate; archive to `reports/archives/agent_audit_YYYY.jsonl` when >500 lines or quarterly |
| `reports/current-cohort-report.json` | Single file; overwritten each round | Previous content recoverable from git history |
| `reports/latest-agent-report.json` | Frozen legacy compatibility snapshot | Do not overwrite; retain until a separately authorized archival decision |
| `reports/gate_result.json` | Overwritten each gate run | CI may upload artifact (AL-030) |
| `reports/tool_probe_report.json` | Overwritten on probe | — |
| `reports/user_view_test.json` | Overwritten on user_view_test | — |
| `.agent_runtime/inspection_reports/` | Local only; gitignored | Manual cleanup after 30 days |

Agents must not commit secrets, raw novel text, or `.env` in any report path. Large audit archives stay local unless user opts in.

## Write / update report

The commands below mutate report files. They run only when the current scoped task explicitly owns the report update; they are not implicit live-tree validation and cannot expand standing Git authority.

```bash
# Print template JSON (stdout)
python3 scripts/write_agent_report.py --round-id AL-013 --goal "My round goal"

# Write current-cohort-report.json + append audit log (validates first)
python3 scripts/write_agent_report.py \
  --round-id AL-013 \
  --goal "My round goal" \
  --mode implement \
  --next AL-014 \
  --write \
  --append-audit "one-line summary"

# Merge extra fields from JSON patch file
python3 scripts/write_agent_report.py \
  --round-id AL-013 \
  --goal "..." \
  --merge reports/round_patch.json \
  --write
```

Auto-fills `tool_probe_status` and `gate_status` from `reports/tool_probe_report.json` and `reports/gate_result.json` when omitted.
