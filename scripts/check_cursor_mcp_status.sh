#!/usr/bin/env bash
# Check Cursor MCP status via cursor-agent CLI (if available).
# Does NOT print secrets. CLI ready ≠ current Agent thread tool registry.

set -u

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MCP_JSON="${REPO_ROOT}/.cursor/mcp.json"

echo "=== Cursor MCP Status Check (CLI layer) ==="
echo "repo: ${REPO_ROOT}"
echo ""
echo "IMPORTANT: This script checks CLI / cursor-agent only."
echo "It does NOT prove the current Agent conversation thread exposes MCP tools."
echo "See docs/cursor_tool_registry_check.md for thread-level checks."
echo ""

if ! command -v cursor-agent >/dev/null 2>&1; then
  echo "cursor-agent: NOT FOUND"
  echo "  Install or ensure cursor-agent is on PATH to run mcp list / list-tools."
  echo "  Fallback: npm run check:mcp && npm run check:stitch"
  echo ""
  echo "result: SKIP (cursor-agent missing)"
  exit 0
fi

echo "cursor-agent: found ($(command -v cursor-agent))"
echo ""

echo "--- cursor-agent mcp list ---"
if ! cursor-agent mcp list 2>&1; then
  echo "  (mcp list returned non-zero; server may need approval in Cursor Settings)"
fi
echo ""

SERVERS=(chrome-devtools playwright stitch filesystem context7 github)

if [[ -f "${MCP_JSON}" ]]; then
  if grep -q '"wechat-chrome-session"' "${MCP_JSON}" 2>/dev/null; then
    SERVERS+=(wechat-chrome-session wechat_chrome_session)
  fi
else
  echo "warning: ${MCP_JSON} not found"
fi

list_tools() {
  local name="$1"
  echo "--- cursor-agent mcp list-tools ${name} ---"
  if cursor-agent mcp list-tools "${name}" 2>&1; then
    :
  else
    echo "  (list-tools failed or server not loaded for: ${name})"
  fi
  echo ""
}

for s in "${SERVERS[@]}"; do
  list_tools "${s}"
done

echo "=== Next steps if MCP not loaded / needs approval ==="
echo "1. Cursor Settings → Tools & MCP → approve required servers"
echo "2. Fully quit Cursor (not just Reload Window)"
echo "3. Reopen this repository"
echo "4. Start a NEW ordinary foreground Agent chat (disable Multitask)"
echo "5. Verify tools appear in the current thread before browser tasks"
echo ""
echo "result: DONE (CLI check complete; thread registry not verified)"
