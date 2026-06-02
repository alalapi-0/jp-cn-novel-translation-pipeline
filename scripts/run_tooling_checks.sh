#!/usr/bin/env sh
# Run deterministic tooling checks (gate + protocol + unit tests).
# Exit 2 from gate/protocol stops the chain; exit 1 (WARNING) continues.
set -u
cd "$(dirname "$0")/.."

run_py() {
  python3 "$1"
  code=$?
  if [ "$code" -eq 2 ]; then
    exit 2
  fi
  return 0
}

run_py scripts/agent_gate.py
run_py scripts/check_protocol_standard.py
run_py scripts/scan_repo_inventory.py
PYTEST="${PYTEST:-pytest}"
if [ -x .venv/bin/pytest ]; then
  PYTEST=".venv/bin/pytest"
fi
$PYTEST tests/ -q
