#!/usr/bin/env bash
# Legacy production pipeline (disabled): historical translate+refine batches.
# Requires user-authorized real API env (OPENROUTER_API_KEY in .env or environment).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [[ "${ALLOW_LEGACY_PRODUCTION_PIPELINE:-0}" != "1" ]]; then
  echo "production_pipeline.sh is deprecated and disabled by default."
  echo "Use scripts/local_scheduler_tick.py with explicit --real-api --max-api-calls after pause/lock/orphan gates pass."
  echo "Set ALLOW_LEGACY_PRODUCTION_PIPELINE=1 only for audited historical reproduction."
  exit 2
fi

export PYTHONUNBUFFERED=1
export DRAFT_MODEL="${DRAFT_MODEL:-deepseek/deepseek-v4-pro}"
export REFINE_MODEL="${REFINE_MODEL:-x-ai/grok-4.3}"
export TRANSLATE_MAX_TEST_COST_USD="${TRANSLATE_MAX_TEST_COST_USD:-2.5}"
export MAX_TEST_COST_USD="${MAX_TEST_COST_USD:-2.0}"
export PILOT_SKIP_OFFSETS="${PILOT_SKIP_OFFSETS:-0}"
export PRODUCTION_STAGE_STATE_PATH="${PRODUCTION_STAGE_STATE_PATH:-workspace/stage_state_production.json}"

if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
  PYTHON="${PYTHON:-$REPO_ROOT/.venv/bin/python}"
else
  PYTHON="${PYTHON:-python3}"
fi

# Load .env into this shell (keys only; never log values)
"$PYTHON" -c "from pathlib import Path; import sys; sys.path.insert(0, 'scripts'); from local_env import apply_local_env; apply_local_env(Path('$REPO_ROOT'))" 2>/dev/null || true
export REAL_API_TESTS_ENABLED="${REAL_API_TESTS_ENABLED:-1}"
export CONTROLLED_RUN_ENABLED="${CONTROLLED_RUN_ENABLED:-1}"

LOG="$REPO_ROOT/workspace/production_pipeline.log"
PIDFILE="$REPO_ROOT/workspace/.production_pipeline.pid"
LOCKFILE="$REPO_ROOT/workspace/.production_pipeline.lock"

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" | tee -a "$LOG"; }

pid_alive() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

remove_stale_locks() {
  local lock_dir="$REPO_ROOT/workspace/.locks"
  [[ -d "$lock_dir" ]] || return 0
  for lock in "$lock_dir"/*.lock; do
    [[ -f "$lock" ]] || continue
    local pid
    pid="$(tr -d ' \n' <"$lock" 2>/dev/null || true)"
    if [[ -z "$pid" ]] || ! pid_alive "$pid"; then
      rm -f "$lock"
      log "removed stale lock $(basename "$lock")"
    fi
  done
}

acquire_singleton() {
  if [[ -f "$PIDFILE" ]]; then
    local old_pid
    old_pid="$(tr -d ' \n' <"$PIDFILE" 2>/dev/null || true)"
    if pid_alive "$old_pid"; then
      log "production_pipeline already running pid=$old_pid; exiting"
      exit 0
    fi
    rm -f "$PIDFILE"
  fi
  if [[ -d "${LOCKFILE}.d" ]]; then
    local lock_pid
    lock_pid="$(tr -d ' \n' <"${LOCKFILE}.d/pid" 2>/dev/null || true)"
    if pid_alive "$lock_pid"; then
      log "production_pipeline lock held by pid=$lock_pid; exiting"
      exit 0
    fi
    rm -rf "${LOCKFILE}.d"
  fi
  if ! mkdir "${LOCKFILE}.d" 2>/dev/null; then
    log "production_pipeline lock busy; exiting"
    exit 0
  fi
  echo $$ >"${LOCKFILE}.d/pid"
  trap 'rm -rf "${LOCKFILE}.d"' EXIT
}

acquire_singleton
echo $$ >"$PIDFILE"
log "production_pipeline start pid=$$"

remove_stale_locks

bash scripts/pilot_batch_chain.sh >>"$LOG" 2>&1

log "production_pipeline COMPLETE"
rm -f "$PIDFILE"
