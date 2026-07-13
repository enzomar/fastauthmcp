#!/usr/bin/env bash
set -euo pipefail

# Ceramic Terminal Demo
# Starts the MCP server in the background and drops into an interactive
# client REPL. First tool call triggers real OAuth2 browser login.
#
# Usage:
#   ./scripts/demo-terminal.sh

source "$(dirname "$0")/_setup.sh"

SERVER_LOG="$VENV_DIR/server.log"
MCP_PORT="${DEMO_MCP_PORT:-8000}"

echo ""
echo "┌──────────────────────────────────────────────────────────────┐"
echo "│          Ceramic Demo — Terminal REPL + MCP Server            │"
echo "├──────────────────────────────────────────────────────────────┤"
echo "│                                                              │"
echo "│  What's running:                                             │"
echo "│    • MCP server (SSE) with Zitadel OIDC authentication       │"
echo "│    • Interactive REPL that calls tools through Ceramic        │"
echo "│                                                              │"
echo "│  Middleware pipeline (every tool call goes through):          │"
echo "│    Observability → Session → Authentication → Authorization  │"
echo "│                                                              │"
echo "│  Available tools (role-based access):                         │"
echo "│    whoami               — any authenticated user              │"
echo "│    get_projects         — requires 'viewer' role             │"
echo "│    get_project_details  — requires 'viewer' role             │"
echo "│    create_project       — requires 'editor' role             │"
echo "│    update_project_status— requires 'editor' role             │"
echo "│    delete_project       — requires 'admin' role              │"
echo "│    get_audit_log        — requires 'admin' role              │"
echo "│                                                              │"
echo "│  First tool call will open your browser for OAuth2 login.    │"
echo "│  Type 'tools' for help, 'quit' to exit.                      │"
echo "│                                                              │"
echo "├──────────────────────────────────────────────────────────────┤"
echo "│  MCP Server: http://localhost:${MCP_PORT}/sse                         │"
echo "│  IDP:        Zitadel Cloud (ceramic-oss)                     │"
echo "│  Server log: .venv-demo/server.log                           │"
echo "└──────────────────────────────────────────────────────────────┘"
echo ""

echo "→ Starting MCP server in background..."

# Start server in background (runs server.py which has the tools registered)
CERAMIC_TRANSPORT=sse CERAMIC_PORT="$MCP_PORT" python server.py > "$SERVER_LOG" 2>&1 &
SERVER_PID=$!

# Cleanup on exit
trap 'echo ""; echo "→ Stopping server (PID $SERVER_PID)..."; kill $SERVER_PID 2>/dev/null; wait $SERVER_PID 2>/dev/null; echo "  Done."' EXIT

# Wait for server to be ready
printf "  Waiting for server"
for i in $(seq 1 30); do
  if curl -s -o /dev/null --max-time 1 "http://localhost:${MCP_PORT}/" 2>/dev/null; then
    break
  fi
  printf "."
  sleep 0.5
done
echo " ✓"
echo ""

python live_client.py
