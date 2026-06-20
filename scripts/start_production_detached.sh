#!/usr/bin/env bash
# Detached launcher for production pipeline + watchdog (survives parent shell exit).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

if [[ "${ALLOW_LEGACY_PRODUCTION_PIPELINE:-0}" != "1" ]]; then
  echo "start_production_detached.sh is deprecated and disabled by default."
  echo "Use scripts/local_scheduler_launchd.sh or scripts/local_scheduler_tick.py for governed execution."
  exit 2
fi

export PYTHON="${PYTHON:-/Users/alalapi/.local/bin/python3.12}"
export REAL_API_TESTS_ENABLED="${REAL_API_TESTS_ENABLED:-1}"
export CONTROLLED_RUN_ENABLED="${CONTROLLED_RUN_ENABLED:-1}"
export PYTHONUNBUFFERED=1
export TRANSLATE_MAX_TEST_COST_USD="${TRANSLATE_MAX_TEST_COST_USD:-2.5}"
export MAX_TEST_COST_USD="${MAX_TEST_COST_USD:-2.0}"
export DRAFT_MODEL="${DRAFT_MODEL:-deepseek/deepseek-v4-pro}"
export REFINE_MODEL="${REFINE_MODEL:-x-ai/grok-4.3}"
export PILOT_SKIP_OFFSETS="${PILOT_SKIP_OFFSETS:-0}"

PIPE_LOG="$REPO_ROOT/workspace/production_pipeline.log"
WATCH_LOG="$REPO_ROOT/workspace/watchdog_poll.log"

"$PYTHON" - <<'PY'
import os
import subprocess
import sys
from pathlib import Path

repo = Path(__file__).resolve().parent if False else Path(os.getcwd())
env = os.environ.copy()
env.setdefault("PYTHON", "/Users/alalapi/.local/bin/python3.12")

def spawn(script: str, log_path: Path) -> int:
    log_fd = open(log_path, "a", encoding="utf-8")
    proc = subprocess.Popen(
        ["bash", str(repo / "scripts" / script)],
        cwd=repo,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=log_fd,
        stderr=subprocess.STDOUT,
        start_new_session=True,
    )
    log_fd.close()
    return proc.pid

pipe_pid = spawn("production_pipeline.sh", repo / "workspace" / "production_pipeline.log")
watch_pid = spawn("production_watchdog.sh", repo / "workspace" / "watchdog_poll.log")
print(f"pipeline_pid={pipe_pid}")
print(f"watchdog_pid={watch_pid}")
PY
