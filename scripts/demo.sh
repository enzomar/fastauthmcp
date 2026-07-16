#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════════════════
# FastAuthMCP E2E Demo
# ═══════════════════════════════════════════════════════════════════════════════
#
# Demonstrates FastAuthMCP's auth pipeline with a real OAuth2 browser flow.
#
# Usage:
#   ./scripts/demo.sh              # default: sse
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
SERVER_PID=""

# ─── Setup ────────────────────────────────────────────────────────────────────

echo "┌────────────────────────────────────────────────────────────────┐"
echo "│               FastAuthMCP E2E Demo                             │"
echo "├────────────────────────────────────────────────────────────────┤"
echo "│  Transport: $TRANSPORT"
echo "│  IDP:       Zitadel Cloud (ceramic-oss)"
echo "└────────────────────────────────────────────────────────────────┘"
echo ""

# Create or reuse virtualenv
if [ ! -d "$VENV_DIR" ]; then
  echo "→ Creating virtualenv at $VENV_DIR..."
  python3 -m venv "$VENV_DIR"
else
  echo "→ Reusing virtualenv at $VENV_DIR"
fi

source "$VENV_DIR/bin/activate"

echo "→ Installing fastauthmcp..."
pip install -e "$PROJECT_ROOT[dev]" --quiet 2>&1 | grep -v "^\[notice\]" || true
echo ""

cd "$EXAMPLE_DIR"

# ─── Cleanup ──────────────────────────────────────────────────────────────────

# Clear stored tokens so the demo always starts fresh
python3 -c "
try:
    import keyring
    keyring.delete_password('fastauthmcp', 'ceramic-oss-agq8i8.eu1.zitadel.cloud')
except Exception:
    pass
" 2>/dev/null || true

# Kill anything on our ports
lsof -ti:9876 | xargs kill -9 2>/dev/null || true
lsof -ti:${MCP_PORT} | xargs kill -9 2>/dev/null || true
sleep 0.3

cleanup() {
  if [ -n "$SERVER_PID" ]; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  lsof -ti:9876 | xargs kill -9 2>/dev/null || true
  lsof -ti:${MCP_PORT} | xargs kill -9 2>/dev/null || true
}
trap cleanup EXIT

# ─── Run ──────────────────────────────────────────────────────────────────────

case "$TRANSPORT" in
  stdio)
    echo "→ Running demo (stdio — server as subprocess)..."
    echo ""
    python mcp_client.py --transport stdio
    ;;

  sse)
    echo "→ Starting server (SSE on :${MCP_PORT})..."
    FASTAUTHMCP_TRANSPORT=sse \
    FASTAUTHMCP_PORT="$MCP_PORT" \
    FASTAUTHMCP_LOG_LEVEL="${FASTAUTHMCP_LOG_LEVEL:-WARNING}" \
      python petstore_server.py 2>/dev/null &
    SERVER_PID=$!

    # Wait for server to be ready (check if process is alive and port responds)
    printf "  Waiting for server"
    for i in $(seq 1 40); do
      if ! kill -0 "$SERVER_PID" 2>/dev/null; then
        echo ""
        echo "  ✗ Server process died. Run with FASTAUTHMCP_LOG_LEVEL=DEBUG for details."
        exit 1
      fi
      if curl -s -o /dev/null --max-time 1 "http://127.0.0.1:${MCP_PORT}/sse" 2>/dev/null; then
        break
      fi
      printf "."
      sleep 0.5
    done
    echo " ready"
    echo ""

    python mcp_client.py --transport sse --url "http://localhost:${MCP_PORT}/sse"
    ;;

  http|streamable-http)
    echo "→ Starting server (streamable-http on :${MCP_PORT})..."
    FASTAUTHMCP_TRANSPORT=streamable-http \
    FASTAUTHMCP_PORT="$MCP_PORT" \
    FASTAUTHMCP_LOG_LEVEL="${FASTAUTHMCP_LOG_LEVEL:-WARNING}" \
      python petstore_server.py &
    SERVER_PID=$!

    printf "  Waiting for server"
    for i in $(seq 1 40); do
      if curl -s -o /dev/null -w "%{http_code}" --max-time 1 "http://localhost:${MCP_PORT}/mcp" 2>/dev/null | grep -q "200\|404\|405"; then
        break
      fi
      printf "."
      sleep 0.3
    done
    echo " ready"
    echo ""

    python mcp_client.py --transport streamable-http --url "http://localhost:${MCP_PORT}/mcp"
    ;;

  clean)
    deactivate 2>/dev/null || true
    rm -rf "$VENV_DIR"
    echo "Removed demo virtualenv."
    ;;

  *)
    echo "Usage: ./scripts/demo.sh [stdio|sse|http|clean]"
    exit 1
    ;;
esac
