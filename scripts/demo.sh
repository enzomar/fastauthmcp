#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════════════════
# FastAuthMCP E2E Demo
# ═══════════════════════════════════════════════════════════════════════════════
#
# Demonstrates FastAuthMCP's auth pipeline with a real OAuth2 flow.
#
# Usage:
#   ./scripts/demo.sh              # default: stdio (most reliable)
#   ./scripts/demo.sh stdio        # spawns server as subprocess
#   ./scripts/demo.sh sse          # starts SSE server + client
#   ./scripts/demo.sh http         # starts streamable-http server + client
#
# ═══════════════════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv-demo"
EXAMPLE_DIR="$PROJECT_ROOT/examples/zitadel"

TRANSPORT="${1:-stdio}"
MCP_PORT="${DEMO_MCP_PORT:-8000}"
SERVER_LOG="$VENV_DIR/server.log"
SERVER_PID=""

# --- Setup ---

echo "┌────────────────────────────────────────────────────────────────────┐"
echo "│                    FastAuthMCP E2E Demo                                │"
echo "├────────────────────────────────────────────────────────────────────┤"
echo "│  Transport: $TRANSPORT"
echo "│  IDP:       Zitadel Cloud (fastauthmcp-oss)"
echo "└────────────────────────────────────────────────────────────────────┘"
echo ""

# Create or reuse virtualenv
if [ ! -d "$VENV_DIR" ]; then
  echo "→ Creating virtualenv at $VENV_DIR..."
  python3 -m venv "$VENV_DIR"
else
  echo "→ Reusing existing virtualenv at $VENV_DIR"
fi

# Activate
source "$VENV_DIR/bin/activate"

# Install fastauthmcp in editable mode
echo "→ Installing fastauthmcp..."
pip install -e "$PROJECT_ROOT[dev]" --quiet
echo "→ Installed: $(pip show fastauthmcp 2>/dev/null | grep Version || echo 'editable')"
echo ""

# Change to example directory so fastauthmcp.yaml is found
cd "$EXAMPLE_DIR"

# --- Clear stored tokens so the demo always starts fresh ---
echo "→ Clearing stored tokens (fresh OAuth flow)..."
python3 -c "
try:
    import keyring
    keyring.delete_password('fastauthmcp', 'fastauthmcp-oss-agq8i8.eu1.zitadel.cloud')
    print('  ✓ Cleared token from Keychain')
except Exception:
    print('  ✓ No stored token to clear')
" 2>/dev/null || echo "  ✓ No stored token to clear"
echo ""

# --- Kill any stale process on the callback port ---
echo "→ Ensuring callback port 9876 is free..."
lsof -ti:9876 | xargs kill -9 2>/dev/null || true
echo "  ✓ Port 9876 available"
echo ""

# --- Cleanup ---

cleanup() {
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# --- Transport-specific logic ---

case "$TRANSPORT" in
  stdio)
    python mcp_client.py --transport stdio
    ;;

  sse)
    echo "→ Starting Pet Store server (SSE on :${MCP_PORT})..."
    FASTAUTHMCP_TRANSPORT=sse FASTAUTHMCP_PORT="$MCP_PORT" FASTAUTHMCP_LOG_LEVEL=INFO python petstore_server.py > "$SERVER_LOG" 2>&1 &
    SERVER_PID=$!
    printf "  Waiting for server"
    for i in $(seq 1 30); do
      if curl -s -o /dev/null --max-time 1 "http://localhost:${MCP_PORT}/" 2>/dev/null; then break; fi
      printf "."; sleep 0.5
    done
    echo " ✓"
    echo ""
    python mcp_client.py --transport sse --url "http://localhost:${MCP_PORT}/sse"
    ;;

  http|streamable-http)
    echo "→ Starting Pet Store server (streamable-http on :${MCP_PORT})..."
    FASTAUTHMCP_TRANSPORT=streamable-http FASTAUTHMCP_PORT="$MCP_PORT" FASTAUTHMCP_LOG_LEVEL=INFO python petstore_server.py > "$SERVER_LOG" 2>&1 &
    SERVER_PID=$!
    printf "  Waiting for server"
    for i in $(seq 1 30); do
      if curl -s -o /dev/null --max-time 1 "http://localhost:${MCP_PORT}/" 2>/dev/null; then break; fi
      printf "."; sleep 0.5
    done
    echo " ✓"
    echo ""
    python mcp_client.py --transport streamable-http --url "http://localhost:${MCP_PORT}/mcp"
    ;;

  login)
    fastauthmcp login
    ;;

  logout)
    fastauthmcp logout
    ;;

  whoami)
    fastauthmcp whoami
    ;;

  doctor)
    fastauthmcp doctor
    ;;

  run)
    exec env FASTAUTHMCP_TRANSPORT=sse FASTAUTHMCP_HOST=localhost FASTAUTHMCP_PORT="$MCP_PORT" FASTAUTHMCP_LOG_LEVEL=INFO python petstore_server.py
    ;;

  test)
    pytest test_server.py -v
    ;;

  clean)
    deactivate 2>/dev/null || true
    rm -rf "$VENV_DIR"
    echo "Done."
    ;;

  *)
    echo "Usage: ./scripts/demo.sh [stdio|sse|http|login|logout|whoami|doctor|run|test|clean]"
    exit 1
    ;;
esac
