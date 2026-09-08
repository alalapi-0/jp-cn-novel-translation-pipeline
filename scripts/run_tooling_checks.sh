#!/usr/bin/env sh
# Deterministic checks. Only documented gate/protocol warnings may continue.
set -eu
cd "$(dirname "$0")/.."
surface=legacy
if [ "$#" -gt 0 ]; then
  [ "$#" -eq 2 ] && [ "$1" = "--surface" ] && [ "$2" = "codex" ] || {
    echo "usage: $0 [--surface codex]" >&2; exit 2;
  }
  surface=codex
fi
if [ -x .venv/bin/python ]; then
  check_python=.venv/bin/python
elif [ "${CI:-}" = "true" ]; then
  check_python=python3
else
  echo "error: missing project .venv; install requirements-dev.txt first" >&2
  exit 2
fi
if [ "$surface" = codex ] || [ "${CI:-}" = "true" ]; then
  export REAL_API_TESTS_ENABLED=false
fi
run_gate() {
  gate_exit=0
  "$check_python" "$@" || gate_exit=$?
  if [ "$gate_exit" -gt 1 ]; then exit "$gate_exit"; fi
}
run_gate scripts/agent_gate.py
"$check_python" scripts/validate_agent_report.py
"$check_python" scripts/check_prompts_refs.py
if [ "$surface" = legacy ]; then
  "$check_python" scripts/tool_probe.py --sync-docs
fi
run_gate scripts/check_protocol_standard.py
if [ "$surface" = legacy ]; then
  "$check_python" scripts/scan_repo_inventory.py
else
  echo "Codex scope: Cursor/tool and MCP inventory probes are excluded; all repository quality tests remain enabled."
fi
"$check_python" -m pytest tests/ -q
