#!/usr/bin/env bash
# Full production pipeline: refine ch1-50, translate+refine batches 50..560, export.
# Requires user-authorized real API env (OPENROUTER_API_KEY in .env or environment).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

export REAL_API_TESTS_ENABLED=1
export CONTROLLED_RUN_ENABLED=1
export PYTHONUNBUFFERED=1
export DRAFT_MODEL="${DRAFT_MODEL:-deepseek/deepseek-v4-pro}"
export REFINE_MODEL="${REFINE_MODEL:-x-ai/grok-4.3}"
export TRANSLATE_MAX_TEST_COST_USD="${TRANSLATE_MAX_TEST_COST_USD:-2.5}"
export MAX_TEST_COST_USD="${MAX_TEST_COST_USD:-2.0}"
export PILOT_SKIP_OFFSETS="${PILOT_SKIP_OFFSETS:-0}"

PYTHON="${PYTHON:-/Users/alalapi/.local/bin/python3.12}"

LOG="$REPO_ROOT/workspace/production_pipeline.log"
PIDFILE="$REPO_ROOT/workspace/.production_pipeline.pid"

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" | tee -a "$LOG"; }

remove_stale_locks() {
  local lock_dir="$REPO_ROOT/workspace/.locks"
  [[ -d "$lock_dir" ]] || return 0
  for lock in "$lock_dir"/*.lock; do
    [[ -f "$lock" ]] || continue
    local pid
    pid="$(tr -d ' \n' <"$lock" 2>/dev/null || true)"
    if [[ -z "$pid" ]] || ! kill -0 "$pid" 2>/dev/null; then
      rm -f "$lock"
      log "removed stale lock $(basename "$lock")"
    fi
  done
}

echo $$ >"$PIDFILE"
log "production_pipeline start pid=$$"

remove_stale_locks

# Drop incomplete offset-50 runs (no segments.json); checkpoints cannot resume without it.
for partial in \
  run_20260604_132246_draft_stage_b_50ch \
  run_20260604_133044_draft_stage_b_50ch; do
  if [[ ! -f "workspace/runs/$partial/segments.json" ]]; then
    rm -rf "workspace/runs/$partial"
    rm -f "workspace/checkpoints/$partial.json"
    log "cleaned partial run $partial"
  fi
done

bash scripts/pilot_batch_chain.sh >>"$LOG" 2>&1

log "production_pipeline COMPLETE"
