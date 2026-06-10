#!/usr/bin/env bash
# Local scheduler launchd integration (FS-005, spec §9.5).
#
# Usage:
#   bash scripts/local_scheduler_launchd.sh install [--dry-run]
#   bash scripts/local_scheduler_launchd.sh uninstall
#   bash scripts/local_scheduler_launchd.sh status
#   bash scripts/local_scheduler_launchd.sh run-tick     # invoked by launchd
#
# The installed agent runs one dry-run scheduler tick every
# SCHEDULER_INTERVAL_SECONDS (default 900). Real-API mode is never the
# default: switching it on is a deliberate manual step documented in
# docs/local_scheduler_runbook.md (FS-006/FS-007). No API keys are written
# to the plist; launchd jobs run without user shell secrets by design.
#
# All three management commands are idempotent.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LABEL="com.lightnovel.translation.scheduler"
TEMPLATE="$REPO_ROOT/scripts/launchd/$LABEL.plist.template"
PLIST_DEST="$HOME/Library/LaunchAgents/$LABEL.plist"
LOG_DIR="$REPO_ROOT/workspace/logs/scheduler"
TICK_LOG="$LOG_DIR/scheduler_tick.log"
INTERVAL_SECONDS="${SCHEDULER_INTERVAL_SECONDS:-900}"
GUI_DOMAIN="gui/$(id -u)"

python_bin() {
  if [[ -x "$REPO_ROOT/.venv/bin/python" ]]; then
    echo "$REPO_ROOT/.venv/bin/python"
  else
    command -v python3
  fi
}

render_plist() {
  sed \
    -e "s|{{REPO_ROOT}}|$REPO_ROOT|g" \
    -e "s|{{LABEL}}|$LABEL|g" \
    -e "s|{{INTERVAL_SECONDS}}|$INTERVAL_SECONDS|g" \
    -e "s|{{LOG_DIR}}|$LOG_DIR|g" \
    "$TEMPLATE"
}

cmd_install() {
  local dry_run=0
  if [[ "${1:-}" == "--dry-run" ]]; then
    dry_run=1
  fi
  if [[ ! -f "$TEMPLATE" ]]; then
    echo "error: template not found: $TEMPLATE" >&2
    return 1
  fi
  if [[ $dry_run -eq 1 ]]; then
    echo "[dry-run] would create log dir: $LOG_DIR"
    echo "[dry-run] would write plist:    $PLIST_DEST"
    echo "[dry-run] would run: launchctl bootout $GUI_DOMAIN/$LABEL (ignore-missing)"
    echo "[dry-run] would run: launchctl bootstrap $GUI_DOMAIN $PLIST_DEST"
    echo "[dry-run] rendered plist follows:"
    render_plist
    return 0
  fi
  mkdir -p "$LOG_DIR" "$(dirname "$PLIST_DEST")"
  render_plist > "$PLIST_DEST"
  # Re-install cleanly when already loaded (idempotent install).
  launchctl bootout "$GUI_DOMAIN/$LABEL" 2>/dev/null || true
  launchctl bootstrap "$GUI_DOMAIN" "$PLIST_DEST"
  echo "installed: $LABEL"
  echo "  interval: ${INTERVAL_SECONDS}s (tick mode: dry-run)"
  echo "  plist:    $PLIST_DEST"
  echo "  tick log: $TICK_LOG"
  echo "  kickstart now: launchctl kickstart $GUI_DOMAIN/$LABEL"
}

cmd_uninstall() {
  launchctl bootout "$GUI_DOMAIN/$LABEL" 2>/dev/null || true
  rm -f "$PLIST_DEST"
  echo "uninstalled: $LABEL (agent unloaded, plist removed if present)"
}

cmd_status() {
  echo "label: $LABEL"
  if [[ -f "$PLIST_DEST" ]]; then
    echo "plist: present ($PLIST_DEST)"
  else
    echo "plist: absent"
  fi
  if launchctl print "$GUI_DOMAIN/$LABEL" >/dev/null 2>&1; then
    echo "launchd: loaded"
    launchctl print "$GUI_DOMAIN/$LABEL" 2>/dev/null \
      | grep -E "state =|last exit code =|run interval =" \
      | sed 's/^[[:space:]]*/  /' || true
  else
    echo "launchd: not loaded"
  fi
  if [[ -f "$TICK_LOG" ]]; then
    echo "tick log tail ($TICK_LOG):"
    tail -n 10 "$TICK_LOG" | sed 's/^/  /'
  else
    echo "tick log: none yet ($TICK_LOG)"
  fi
}

cmd_run_tick() {
  # Invoked by launchd. launchd provides no user shell environment, so we
  # rely only on the plist PATH, an explicit cd, and the repo's venv python.
  # Tick mode is pinned to dry-run; real mode is a manual runbook step.
  mkdir -p "$LOG_DIR"
  cd "$REPO_ROOT"
  local py ts rc
  py="$(python_bin)"
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "[$ts] tick start (mode=dry-run, python=$py)" >> "$TICK_LOG"
  set +e
  "$py" scripts/local_scheduler_tick.py --dry-run >> "$TICK_LOG" 2>&1
  rc=$?
  set -e
  ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "[$ts] tick exit code=$rc" >> "$TICK_LOG"
  return "$rc"
}

usage() {
  sed -n '2,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

case "${1:-}" in
  install)
    shift
    cmd_install "$@"
    ;;
  uninstall)
    cmd_uninstall
    ;;
  status)
    cmd_status
    ;;
  run-tick)
    cmd_run_tick
    ;;
  *)
    usage
    exit 64
    ;;
esac
