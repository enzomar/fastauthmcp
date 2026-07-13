#!/usr/bin/env bash
set -euo pipefail

# Dev demo script for ceramic-fwk
# Builds and installs the package in a temporary virtualenv,
# then runs the Zitadel example server.
#
# Usage:
#   ./scripts/dev-demo.sh          # install + run server
#   ./scripts/dev-demo.sh login    # install + login only
#   ./scripts/dev-demo.sh whoami   # install + show identity

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv-demo"
EXAMPLE_DIR="$PROJECT_ROOT/examples/zitadel"

ACTION="${1:-demo}"

echo "=== Ceramic Dev Demo ==="
echo "Project root: $PROJECT_ROOT"
echo "Virtualenv:   $VENV_DIR"
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

# Install ceramic-fwk in editable mode with dev deps
echo "→ Installing ceramic-fwk (editable + dev dependencies)..."
pip install -e "$PROJECT_ROOT[dev]" --quiet

echo "→ Installed: $(pip show ceramic-fwk 2>/dev/null | grep Version || echo 'ceramic-fwk (editable)')"
echo ""

# Change to example directory so ceramic.yaml is picked up
cd "$EXAMPLE_DIR"

case "$ACTION" in
  demo)
    echo "→ Starting Ceramic Chat Demo (Web UI + MCP Server)..."
    echo "  (working dir: $EXAMPLE_DIR)"
    echo ""
    exec python demo.py
    ;;
  interactive)
    SERVER_LOG="$PROJECT_ROOT/.venv-demo/server.log"

    echo "→ Starting Zitadel example server in background..."
    echo "  (working dir: $EXAMPLE_DIR)"
    echo "  (server logs: $SERVER_LOG)"
    echo ""

    # Start server in background, redirect output to log file
    CERAMIC_TRANSPORT=sse CERAMIC_HOST=localhost CERAMIC_PORT=8000 \
      python server.py > "$SERVER_LOG" 2>&1 &
    SERVER_PID=$!

    # Cleanup on exit
    trap 'echo ""; echo "→ Stopping server (PID $SERVER_PID)..."; kill $SERVER_PID 2>/dev/null; wait $SERVER_PID 2>/dev/null; echo "  Done."' EXIT

    # Wait for server to be ready
    printf "  Waiting for server to be ready"
    for i in $(seq 1 30); do
      if curl -s -o /dev/null --max-time 1 http://localhost:8000/ 2>/dev/null; then
        break
      fi
      printf "."
      sleep 0.5
    done
    echo " ✓"
    echo ""

    # Drop into interactive live client
    echo "→ Starting interactive client (first tool call will open browser for login)"
    echo "  Type a tool name to call it. Type 'tools' for a list, 'quit' to exit."
    echo ""
    python live_client.py
    ;;
  run)
    echo "→ Starting Zitadel example server..."
    echo "  (working dir: $EXAMPLE_DIR)"
    echo ""
    exec env CERAMIC_TRANSPORT=sse CERAMIC_HOST=localhost CERAMIC_PORT=8000 python server.py
    ;;
  client)
    echo "→ Starting interactive MCP client..."
    echo "  (simulated identity — no live IDP needed)"
    echo ""
    exec python client.py "${@:2}"
    ;;
  login)
    echo "→ Running ceramic login..."
    echo ""
    exec ceramic login
    ;;
  logout)
    echo "→ Running ceramic logout..."
    echo ""
    exec ceramic logout
    ;;
  whoami)
    echo "→ Running ceramic whoami..."
    echo ""
    exec ceramic whoami
    ;;
  doctor)
    echo "→ Running ceramic doctor..."
    echo ""
    exec ceramic doctor
    ;;
  live-client)
    echo "→ Starting live MCP client (connects to running server via SSE)..."
    echo "  Make sure the server is running: ./scripts/dev-demo.sh run"
    echo "  (First call will trigger real OAuth2 browser login)"
    echo ""
    exec python live_client.py "${@:2}"
    ;;
  server)
    echo "→ Starting server directly with python..."
    echo ""
    exec python server.py
    ;;
  clean)
    echo "→ Removing demo virtualenv..."
    deactivate 2>/dev/null || true
    rm -rf "$VENV_DIR"
    echo "  Done. Removed $VENV_DIR"
    ;;
  *)
    echo "Unknown action: $ACTION"
    echo ""
    echo "Usage: ./scripts/dev-demo.sh [action]"
    echo ""
    echo "Actions:"
    echo "  (no arg)     Start Chat Demo UI + MCP server (default)"
    echo "  interactive  Start server + interactive terminal REPL with real OAuth2"
    echo "  run          Start only the Zitadel example server with SSE transport"
    echo "  client       Interactive REPL with simulated identity (no server needed)"
    echo "  live-client  Interactive REPL against running server (real OAuth2 flow)"
    echo "  login        Run OAuth2 login flow"
    echo "  logout       Clear stored tokens"
    echo "  whoami       Show current identity"
    echo "  doctor       Health check"
    echo "  server       Run server.py directly (python server.py, stdio transport)"
    echo "  clean        Remove the demo virtualenv"
    exit 1
    ;;
esac
