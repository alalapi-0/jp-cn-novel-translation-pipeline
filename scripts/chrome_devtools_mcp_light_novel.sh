#!/usr/bin/env bash
# Project-isolated launcher for chrome-devtools MCP (light_novel).
# Avoids sharing ~/.cache/chrome-devtools-mcp/chrome-profile with other projects.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROFILE_DIR="${CHROME_DEVTOOLS_MCP_USER_DATA_DIR:-${HOME}/.cache/chrome-devtools-mcp/light_novel-chrome-profile}"
DEBUG_PORT="${CHROME_DEVTOOLS_MCP_DEBUG_PORT:-9321}"

mkdir -p "${PROFILE_DIR}"

exec npx -y chrome-devtools-mcp@latest \
  --userDataDir="${PROFILE_DIR}" \
  --chromeArg="--remote-debugging-port=${DEBUG_PORT}" \
  "$@"
