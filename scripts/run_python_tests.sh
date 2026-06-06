#!/usr/bin/env sh
set -eu

REPO_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$REPO_ROOT"

VENV_PY=".venv/bin/python"

if [ ! -x "$VENV_PY" ]; then
  echo "error: Python venv not found at .venv/bin/python" >&2
  echo "hint: python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt" >&2
  exit 1
fi

exec "$VENV_PY" -m pytest "$@"
