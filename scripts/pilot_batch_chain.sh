#!/usr/bin/env bash
# Chain Stage B translate (50-ch batches) + Stage C refine until input_jp exhausted.
# Skips work when translate/refine locks are held by live PIDs. Requires user-authorized real API env.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

export REAL_API_TESTS_ENABLED=1
export CONTROLLED_RUN_ENABLED=1
export PYTHONUNBUFFERED=1
export DRAFT_MODEL="${DRAFT_MODEL:-deepseek/deepseek-v4-pro}"
export REFINE_MODEL="${REFINE_MODEL:-x-ai/grok-4.3}"

PYTHON="${PYTHON:-/Users/alalapi/.local/bin/python3.12}"

LOG="$REPO_ROOT/workspace/pilot_batch_chain.log"
TOTAL_CHAPTERS=613
BATCH=50

log() { echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*" >>"$LOG"; }

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

lock_holder_alive() {
  local lock_path="$1"
  [[ -f "$lock_path" ]] || return 1
  local pid
  pid="$(tr -d ' \n' <"$lock_path" 2>/dev/null || true)"
  pid_alive "$pid"
}

wait_translate_idle() {
  local lock="$REPO_ROOT/workspace/.locks/translate_stage_b_stage_b_default.lock"
  while lock_holder_alive "$lock"; do
    log "translate lock busy (pid $(cat "$lock" 2>/dev/null)); waiting 60s"
    sleep 60
  done
}

wait_refine_idle() {
  local run_id="$1"
  local lock="$REPO_ROOT/workspace/.locks/refine_stage_c_${run_id}.lock"
  while lock_holder_alive "$lock"; do
    log "refine lock busy for $run_id; waiting 30s"
    sleep 30
  done
}

refine_eligible() {
  local run_id="$1"
  "$PYTHON" -c "
import json
from pathlib import Path
p = Path('workspace/runs/$run_id/segments.json')
if not p.is_file():
    print(0)
    raise SystemExit
d = json.loads(p.read_text())
n = sum(
    1 for ch in d.get('chapters', [])
    for s in ch.get('segments', [])
    if not s.get('human_edited')
    and (s.get('draft_text') or '').strip()
    and not (s.get('refined_text') or '').strip()
)
print(n)
"
}

draft_complete() {
  local run_id="$1"
  "$PYTHON" -c "
import json
from pathlib import Path
p = Path('workspace/runs/$run_id/segments.json')
if not p.is_file():
    raise SystemExit(1)
d = json.loads(p.read_text())
segs = [s for ch in d.get('chapters',[]) for s in ch.get('segments',[])]
if not segs:
    raise SystemExit(1)
missing = sum(1 for s in segs if not (s.get('draft_text') or '').strip())
print('ok' if missing == 0 else 'partial')
" 2>/dev/null
}

refine_run_until_done() {
  local run_id="$1"
  log "refine loop start: $run_id"
  while true; do
    local eligible
    eligible="$(refine_eligible "$run_id")"
    log "refine $run_id eligible=$eligible"
    [[ "$eligible" -eq 0 ]] && { log "refine DONE $run_id"; return 0; }
    wait_refine_idle "$run_id"
    export MAX_TEST_COST_USD="${MAX_TEST_COST_USD:-2.0}"
    if ! "$PYTHON" scripts/refine_stage_c.py --run-id "$run_id" --limit-segments 30 >>"$LOG" 2>&1; then
      log "refine batch FAILED exit=$? for $run_id"
      sleep 30
    fi
    sleep 2
  done
}

latest_run_for_offset() {
  local offset="$1"
  "$PYTHON" -c "
import json
from pathlib import Path
root = Path('workspace/runs')
best = None
for meta in sorted(root.glob('run_*_draft_stage_b_50ch/run_metadata.json'), reverse=True):
    try:
        d = json.loads(meta.read_text())
    except Exception:
        continue
    if d.get('chapter_offset') != int('$offset'):
        co = d.get('chapter_offset')
        if not (co is None and int('$offset') == 0):
            continue
    rid = d.get('run_id') or meta.parent.name
    if (meta.parent / 'segments.json').is_file():
        best = rid
        break
if best:
    print(best)
"
}

resumable_run_for_offset() {
  local offset="$1"
  "$PYTHON" -c "
import json
from pathlib import Path
offset = int('$offset')
ck_dir = Path('workspace/checkpoints')
runs = Path('workspace/runs')
for ck_path in sorted(ck_dir.glob('run_*_draft_stage_b_50ch.json'), reverse=True):
    rid = ck_path.stem
    try:
        ck = json.loads(ck_path.read_text())
    except Exception:
        continue
    status = ck.get('status') or ''
    if status == 'completed':
        continue
    run_dir = runs / rid
    if not run_dir.is_dir():
        continue
    meta = run_dir / 'run_metadata.json'
    if meta.is_file():
        off = int(json.loads(meta.read_text()).get('chapter_offset') or 0)
    else:
        segs = ck.get('completed_segments') or []
        if not segs:
            continue
        ch_num = int(segs[0].split('-seg-')[0].split('-')[1])
        off = ch_num - 1
    if off != offset:
        continue
    seg_path = run_dir / 'segments.json'
    if seg_path.is_file():
        doc = json.loads(seg_path.read_text())
        segs = [s for ch in doc.get('chapters', []) for s in ch.get('segments', [])]
        if segs and all((s.get('draft_text') or '').strip() for s in segs):
            continue
    print(rid)
    break
"
}

run_translate_batch() {
  local offset="$1"
  wait_translate_idle
  local resume_id
  resume_id="$(resumable_run_for_offset "$offset")"
  log "translate offset=$offset limit=$BATCH${resume_id:+ resume=$resume_id}"
  export MAX_TEST_COST_USD="${TRANSLATE_MAX_TEST_COST_USD:-2.5}"
  local -a translate_args=(
    scripts/translate.py --phase draft --stage stage_b
    --chapter-offset "$offset" --limit-chapters "$BATCH"
  )
  if [[ -n "${resume_id:-}" ]]; then
    translate_args+=(--run-id "$resume_id")
  fi
  while true; do
    if "$PYTHON" "${translate_args[@]}" >>"$LOG" 2>&1; then
      break
    fi
    rc=$?
    if [[ "$rc" -eq 2 ]] && lock_holder_alive "$REPO_ROOT/workspace/.locks/translate_stage_b_${resume_id:-stage_b_default}.lock"; then
      log "translate lock busy (exit=$rc); waiting 60s"
      sleep 60
      continue
    fi
    log "translate FAILED exit=$rc offset=$offset"
    return "$rc"
  done
}

# Offsets with completed draft runs (skip re-translate, still refine)
SKIP_OFFSETS="${PILOT_SKIP_OFFSETS:-0}"

remove_stale_locks
log "pilot_batch_chain start TOTAL=$TOTAL_CHAPTERS BATCH=$BATCH skip=$SKIP_OFFSETS"

# Finish in-flight translate/refine started outside this script
IFS=',' read -ra SKIP_ARR <<< "$SKIP_OFFSETS"
for skip_off in "${SKIP_ARR[@]}"; do
  [[ -n "$skip_off" ]] || continue
  log "drain skip-offset=$skip_off (refine existing draft, no re-translate)"
  wait_translate_idle
  rid="$(latest_run_for_offset "$skip_off")"
  if [[ -n "${rid:-}" ]] && [[ "$(draft_complete "$rid" 2>/dev/null || echo partial)" == "ok" ]]; then
    refine_run_until_done "$rid"
  elif [[ -n "${rid:-}" ]]; then
    log "waiting draft for in-flight $rid"
    while [[ "$(draft_complete "$rid" 2>/dev/null || echo partial)" != "ok" ]]; do
      sleep 120
    done
    refine_run_until_done "$rid"
  fi
done

offset=0
while [[ "$offset" -lt "$TOTAL_CHAPTERS" ]]; do
  if [[ ",$SKIP_OFFSETS," == *",$offset,"* ]]; then
    log "skip offset $offset (external worker)"
    offset=$((offset + BATCH))
    continue
  fi
  run_translate_batch "$offset"
  run_id="$(latest_run_for_offset "$offset")"
  if [[ -z "${run_id:-}" ]]; then
    run_id="$("$PYTHON" -c "import json;print(json.load(open('workspace/stage_state.json'))['run_id'])" 2>/dev/null || true)"
  fi
  if [[ -z "${run_id:-}" ]]; then
    log "ERROR: no run_id after translate offset=$offset"
    exit 1
  fi
  while [[ "$(draft_complete "$run_id" 2>/dev/null || echo partial)" != "ok" ]]; do
    log "waiting draft complete for $run_id"
    sleep 120
  done
  refine_run_until_done "$run_id"
  offset=$((offset + BATCH))
done

log "pilot_batch_chain ALL BATCHES DONE"
log "export start"
if "$PYTHON" scripts/export_refined_runs.py --require-refined >>"$LOG" 2>&1; then
  log "export DONE"
else
  log "export FAILED (may retry after refine completes)"
fi
