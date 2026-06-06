#!/usr/bin/env bash
# Persistent watchdog: restart production_pipeline only when no pipeline or worker is alive.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${PYTHON:-/Users/alalapi/.local/bin/python3.12}"
LOG="$REPO_ROOT/workspace/watchdog_poll.log"
PIDFILE="$REPO_ROOT/workspace/.production_watchdog.pid"
LOCKFILE="$REPO_ROOT/workspace/.production_watchdog.lock"
INTERVAL="${WATCHDOG_INTERVAL_SEC:-240}"

export REAL_API_TESTS_ENABLED=1 CONTROLLED_RUN_ENABLED=1 PYTHONUNBUFFERED=1
export TRANSLATE_MAX_TEST_COST_USD="${TRANSLATE_MAX_TEST_COST_USD:-2.5}"
export MAX_TEST_COST_USD="${MAX_TEST_COST_USD:-2.0}"
export DRAFT_MODEL="${DRAFT_MODEL:-deepseek/deepseek-v4-pro}"
export REFINE_MODEL="${REFINE_MODEL:-x-ai/grok-4.3}"
export PILOT_SKIP_OFFSETS="${PILOT_SKIP_OFFSETS:-0}"

wlog() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" >>"$LOG"; }

pid_alive() {
  local pid="${1:-}"
  [[ -n "$pid" ]] && kill -0 "$pid" 2>/dev/null
}

pipeline_alive() {
  local ps_out
  ps_out="$(ps aux 2>/dev/null || true)"
  if echo "$ps_out" | grep -E '[s]cripts/production_pipeline\.sh' >/dev/null 2>&1; then
    return 0
  fi
  if echo "$ps_out" | grep -E '[s]cripts/pilot_batch_chain\.sh' >/dev/null 2>&1; then
    return 0
  fi
  return 1
}

work_in_progress() {
  local ps_out reg_out
  ps_out="$(ps aux 2>/dev/null || true)"
  if echo "$ps_out" | grep -E '[s]cripts/translate\.py' >/dev/null 2>&1; then
    return 0
  fi
  if echo "$ps_out" | grep -E '[s]cripts/refine_stage_c\.py' >/dev/null 2>&1; then
    return 0
  fi
  reg_out="$("$PYTHON" scripts/pipeline_worker_registry.py --json 2>/dev/null || true)"
  if echo "$reg_out" | grep -q '"active_count": [1-9]'; then
    return 0
  fi
  return 1
}

all_batches_done() {
  grep -q 'pilot_batch_chain ALL BATCHES DONE' "$REPO_ROOT/workspace/pilot_batch_chain.log" 2>/dev/null \
    || grep -q 'pilot_batch_chain ALL BATCHES DONE' "$REPO_ROOT/workspace/production_pipeline.log" 2>/dev/null
}

draft_progress() {
  local run_id=""
  local progress_file="$REPO_ROOT/workspace/stage_state.json"
  if [[ -f "$progress_file" ]]; then
    run_id="$("$PYTHON" -c "
import json
from pathlib import Path
p = Path('$progress_file')
if p.is_file():
    d = json.loads(p.read_text())
    print(d.get('run_id', ''))
" 2>/dev/null || true)"
  fi
  if [[ -z "$run_id" ]]; then
    run_id="$("$PYTHON" -c "
import json
from pathlib import Path
runs = sorted(Path('$REPO_ROOT/workspace/runs').glob('run_*_draft_stage_b_50ch/run_progress.json'))
if runs:
    d = json.loads(runs[-1].read_text())
    print(d.get('run_id', ''))
" 2>/dev/null || true)"
  fi
  if [[ -z "$run_id" ]]; then
    echo 0
    return
  fi
  local d="$REPO_ROOT/workspace/runs/$run_id/draft"
  if [[ -d "$d" ]]; then
    find "$d" -name '*.md' 2>/dev/null | wc -l | tr -d ' '
  else
    "$PYTHON" -c "
import json
from pathlib import Path
p = Path('$REPO_ROOT/workspace/runs/$run_id/run_progress.json')
if p.is_file():
    d = json.loads(p.read_text())
    print(d.get('completed_segments', 0))
else:
    print(0)
" 2>/dev/null || echo 0
  fi
}

restart_pipeline() {
  wlog "RESTART production_pipeline (no alive pipeline or worker)"
  nohup env PYTHON="$PYTHON" REAL_API_TESTS_ENABLED=1 CONTROLLED_RUN_ENABLED=1 \
    TRANSLATE_MAX_TEST_COST_USD="${TRANSLATE_MAX_TEST_COST_USD}" \
    MAX_TEST_COST_USD="${MAX_TEST_COST_USD}" \
    DRAFT_MODEL="${DRAFT_MODEL}" REFINE_MODEL="${REFINE_MODEL}" \
    PILOT_SKIP_OFFSETS="${PILOT_SKIP_OFFSETS}" \
    bash "$REPO_ROOT/scripts/production_pipeline.sh" >>"$REPO_ROOT/workspace/production_pipeline.log" 2>&1 &
  sleep 5
}

if [[ -f "$PIDFILE" ]]; then
  old_pid="$(tr -d ' \n' <"$PIDFILE" 2>/dev/null || true)"
  if pid_alive "$old_pid"; then
    echo "watchdog already running pid=$old_pid"
    exit 0
  fi
  rm -f "$PIDFILE"
fi

if [[ -d "${LOCKFILE}.d" ]]; then
  lock_pid="$(tr -d ' \n' <"${LOCKFILE}.d/pid" 2>/dev/null || true)"
  if pid_alive "$lock_pid"; then
    echo "watchdog lock held by pid=$lock_pid"
    exit 0
  fi
  rm -rf "${LOCKFILE}.d"
fi

if ! mkdir "${LOCKFILE}.d" 2>/dev/null; then
  echo "watchdog lock busy"
  exit 0
fi
echo $$ >"${LOCKFILE}.d/pid"
trap 'rm -rf "${LOCKFILE}.d"; rm -f "$PIDFILE"' EXIT

echo $$ >"$PIDFILE"
wlog "watchdog start pid=$$ interval=${INTERVAL}s PILOT_SKIP_OFFSETS=${PILOT_SKIP_OFFSETS}"
sleep 15

while true; do
  ch51_drafts="$(draft_progress)"
  ps_lines="$(ps aux 2>/dev/null | grep -v grep | grep -E 'production_pipeline|pilot_batch_chain|translate\.py|refine_stage_c' | awk '{print $2,$11,$12,$13,$14}' | head -6 | tr '\n' ' ')"
  wlog "poll ch51-100_draft_md=${ch51_drafts}/50 ps: ${ps_lines:-NONE}"

  if all_batches_done; then
    wlog "ALL BATCHES DONE -> export_refined_runs.py --require-refined"
    if "$PYTHON" scripts/export_refined_runs.py --require-refined >>"$LOG" 2>&1; then
      wlog "export DONE"
    else
      wlog "export FAILED exit=$?"
    fi
    wlog "STOP_REASON=all_batches_complete"
    rm -f "$PIDFILE"
    exit 0
  fi

  if ! pipeline_alive && ! work_in_progress; then
    if all_batches_done; then
      :
    else
      restart_pipeline
    fi
  fi

  errline="$(tail -30 "$REPO_ROOT/workspace/pilot_batch_chain.log" 2>/dev/null | grep -iE 'ERROR:|Traceback|CostGuard|missing.*key|401|403' | tail -1 || true)"
  if [[ -n "$errline" ]]; then
    wlog "log_alert: $errline"
  fi

  sleep "$INTERVAL"
done
