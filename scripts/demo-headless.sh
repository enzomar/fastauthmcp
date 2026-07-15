#!/usr/bin/env bash
set -euo pipefail

# ═══════════════════════════════════════════════════════════════════════════════
# FastAuthMCP Headless Demo — Token Exchange & Downstream Token Propagation
# ═══════════════════════════════════════════════════════════════════════════════
#
# Simulates a CLOUD-DEPLOYED MCP server that:
#   - Has NO browser (headless)
#   - Receives a user token from the calling platform (Claude, Gemini, etc.)
#   - Exchanges it at the IDP for a downstream-scoped token (RFC 8693)
#   - Propagates the token to downstream APIs via access_token()
#
# This is NOT a stdio demo — it starts an SSE/HTTP server because that's
# how a cloud MCP server is deployed.
#
# Usage:
#   ./scripts/demo-headless.sh              # Start server + simulate client call
#   ./scripts/demo-headless.sh server       # Start the headless server only
#   ./scripts/demo-headless.sh client       # Simulate a client call with token
#   ./scripts/demo-headless.sh explain      # Explain the architecture & flow
#   ./scripts/demo-headless.sh clean        # Remove demo venv
#
# ═══════════════════════════════════════════════════════════════════════════════

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV_DIR="$PROJECT_ROOT/.venv-demo"
EXAMPLE_DIR="$PROJECT_ROOT/examples"

MODE="${1:-explain}"
MCP_PORT="${DEMO_MCP_PORT:-8001}"
SERVER_PID=""

echo "┌────────────────────────────────────────────────────────────────────┐"
echo "│              FastAuthMCP Headless Demo                                 │"
echo "├────────────────────────────────────────────────────────────────────┤"
echo "│  Mode: $MODE"
echo "│  Transport: SSE (cloud deployment, no browser)                     │"
echo "│  Port: $MCP_PORT"
echo "│                                                                    │"
echo "│  Scenario:                                                         │"
echo "│    Your MCP server runs in the cloud. The calling platform         │"
echo "│    (Claude, Gemini) passes a user token. FastAuthMCP exchanges it      │"
echo "│    for a downstream-scoped token. Your tool calls access_token()   │"
echo "│    to authenticate downstream API calls.                           │"
echo "└────────────────────────────────────────────────────────────────────┘"
echo ""

# --- Setup ---

setup_venv() {
  if [ ! -d "$VENV_DIR" ]; then
    echo "→ Creating virtualenv at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
  else
    echo "→ Reusing existing virtualenv at $VENV_DIR"
  fi

  source "$VENV_DIR/bin/activate"
  pip install -e "$PROJECT_ROOT[dev]" --quiet
  echo "→ Installed: $(pip show fastauthmcp 2>/dev/null | grep Version || echo 'editable')"
  echo ""
}

cleanup() {
  if [ -n "$SERVER_PID" ]; then
    echo ""
    echo "→ Stopping server (PID $SERVER_PID)..."
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT

# --- Mode-specific logic ---

case "$MODE" in

  explain)
    echo "═══════════════════════════════════════════════════════════════"
    echo "  HOW IT WORKS — Cloud MCP with User-Scoped Downstream Tokens"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "  The Problem:"
    echo "    Your MCP server runs headless in the cloud. It needs to call"
    echo "    downstream APIs (Stripe, GitHub, your internal service) on"
    echo "    behalf of the USER — not a shared service account."
    echo ""
    echo "  The Solution: Token Exchange (RFC 8693)"
    echo ""
    echo "  ┌──────────────┐     ┌──────────────────┐     ┌──────────────┐"
    echo "  │ Claude/Gemini│────▶│ FastAuthMCP MCP (SSE) │────▶│ Downstream   │"
    echo "  │  (has user   │     │                    │     │ API          │"
    echo "  │   token)     │     │ 1. Extract token   │     │              │"
    echo "  └──────────────┘     │ 2. Exchange at IDP │     │ Authed with  │"
    echo "                       │ 3. access_token()  │────▶│ user's scoped│"
    echo "                       │    → downstream    │     │ token        │"
    echo "                       └──────────────────┘     └──────────────┘"
    echo ""
    echo "  Configuration (fastauthmcp.yaml):"
    echo ""
    echo "    auth:"
    echo "      provider: oidc"
    echo "      issuer: https://your-idp.example.com"
    echo "      client_id: my-mcp-server"
    echo "      client_secret: \${FASTAUTHMCP_AUTH_CLIENT_SECRET}"
    echo "      grant_type: token_exchange              # ← RFC 8693"
    echo "      upstream_token_header: x-user-token     # ← where to find it"
    echo "      token_exchange_audience: https://api.internal.com"
    echo "      token_exchange_scope: \"read:data\""
    echo ""
    echo "  In your tool code:"
    echo ""
    echo "    from fastauthmcp import FastMCP, access_token"
    echo ""
    echo "    mcp = FastMCP(\"cloud-server\", config=\"fastauthmcp.yaml\")"
    echo ""
    echo "    @mcp.tool()"
    echo "    def get_orders() -> list:"
    echo "        token = access_token()  # ← user-scoped downstream token"
    echo "        resp = httpx.get("
    echo "            \"https://api.internal.com/orders\","
    echo "            headers={\"Authorization\": f\"Bearer {token}\"},"
    echo "        )"
    echo "        return resp.json()"
    echo ""
    echo "  The calling platform (Claude, Gemini) sends the user's token"
    echo "  in the MCP request metadata. FastAuthMCP:"
    echo "    1. Extracts it from the configured header/key"
    echo "    2. Exchanges it at the IDP token endpoint (RFC 8693)"
    echo "    3. Makes the downstream token available via access_token()"
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "  Supported IDPs:"
    echo "    • Zitadel       ✓ (native RFC 8693)"
    echo "    • Keycloak      ✓ (built-in token exchange)"
    echo "    • Auth0         ✓ (via Actions)"
    echo "    • Okta          ✓ (via Authorization Servers)"
    echo "    • Entra ID      ✓ (On-Behalf-Of / OBO flow)"
    echo "    • Google IAM    ✓ (STS API)"
    echo ""
    echo "═══════════════════════════════════════════════════════════════"
    echo ""
    echo "  Run the demo:"
    echo "    ./scripts/demo-headless.sh server    # Start headless MCP server"
    echo "    ./scripts/demo-headless.sh client    # Simulate platform call with token"
    echo ""
    ;;

  server)
    setup_venv
    cd "$EXAMPLE_DIR"

    echo "═══════════════════════════════════════════════════════════════"
    echo "  Starting Headless MCP Server (SSE on :${MCP_PORT})"
    echo ""
    echo "  grant_type: token_exchange"
    echo "  upstream_token_header: x-user-token"
    echo ""
    echo "  The server expects an upstream user token in request metadata."
    echo "  Use './scripts/demo-headless.sh client' to send a test call."
    echo "═══════════════════════════════════════════════════════════════"
    echo ""

    # Use a config that enables token_exchange
    cat > "$VENV_DIR/headless-demo.yaml" << 'EOF'
# Headless demo config — token_exchange mode
auth:
  provider: oidc
  issuer: https://ceramic-oss-agq8i8.eu1.zitadel.cloud
  client_id: "380842820363183891"
  grant_type: token_exchange
  upstream_token_header: x-user-token
  scopes:
    - openid
    - profile
    - email
    - "urn:zitadel:iam:org:project:roles"
  token_exchange_timeout: 30

observability:
  enabled: true
  exporter: console
  log_format: text
  log_level: info

sessions:
  enabled: false
EOF

    echo "→ Server starting on http://localhost:${MCP_PORT} ..."
    echo "  (Press Ctrl+C to stop)"
    echo ""

    FASTAUTHMCP_CONFIG="$VENV_DIR/headless-demo.yaml" \
    FASTAUTHMCP_TRANSPORT=sse \
    FASTAUTHMCP_HOST=localhost \
    FASTAUTHMCP_PORT="$MCP_PORT" \
    FASTAUTHMCP_LOG_LEVEL=INFO \
      python headless_server.py
    ;;

  client)
    setup_venv

    echo "═══════════════════════════════════════════════════════════════"
    echo "  Simulating Platform Call with User Token"
    echo ""
    echo "  This simulates what Claude/Gemini would do:"
    echo "    1. User is logged in on the platform"
    echo "    2. Platform has a user token"
    echo "    3. Platform sends MCP tool call + user token in metadata"
    echo "    4. FastAuthMCP exchanges the token and makes it available"
    echo "═══════════════════════════════════════════════════════════════"
    echo ""

    # First, we need a real user token to use as the "upstream" token.
    # In a real cloud deployment, the platform provides this.
    # For the demo, we get one via the stored login token.
    echo "→ Getting a user token to simulate the upstream platform..."
    echo "  (In production, the calling platform provides this)"
    echo ""

    python -c "
import asyncio
import sys

async def main():
    from fastauthmcp.auth.token_storage import get_token_storage

    storage = get_token_storage()
    token_set = await storage.retrieve('ceramic-oss-agq8i8.eu1.zitadel.cloud')
    if not token_set:
        token_set = await storage.retrieve('default')
    if not token_set:
        print('❌ No stored token. Run the interactive demo first:')
        print('   cd examples/zitadel && FASTAUTHMCP_CONFIG=fastauthmcp.yaml fastauthmcp login')
        sys.exit(1)

    token = token_set.access_token
    print(f'✓ Got upstream user token: {token[:40]}...')
    print()
    print('→ In production, the calling platform (Claude/Gemini) would')
    print('  include this token in the MCP request metadata as:')
    print(f'  {{\"x-user-token\": \"{token[:20]}...\"}}')
    print()
    print('→ FastAuthMCP would then:')
    print('  1. Extract it from metadata[\"x-user-token\"]')
    print('  2. POST to IDP: grant_type=urn:ietf:params:oauth:grant-type:token-exchange')
    print('  3. Get back a scoped downstream token')
    print('  4. Make it available via access_token()')
    print()
    print('→ Your tool code simply does:')
    print('    token = access_token()')
    print('    resp = httpx.get(url, headers={\"Authorization\": f\"Bearer {token}\"})')
    print()

    # Prove the token is valid by calling userinfo
    import httpx
    print('→ Proving the token is valid (calling IDP userinfo)...')
    try:
        resp = httpx.get(
            'https://ceramic-oss-agq8i8.eu1.zitadel.cloud/oidc/v1/userinfo',
            headers={'Authorization': f'Bearer {token}'},
            timeout=10,
        )
        if resp.status_code == 200:
            info = resp.json()
            print(f'  ✓ Token is valid! User: {info.get(\"email\", info.get(\"sub\", \"unknown\"))}')
        else:
            print(f'  ⚠ Userinfo returned {resp.status_code} (token may be expired)')
            print(f'    Re-login: cd examples/zitadel && FASTAUTHMCP_CONFIG=fastauthmcp.yaml fastauthmcp login')
    except Exception as e:
        print(f'  ⚠ Could not reach IDP: {e}')

    print()
    print('═══════════════════════════════════════════════════════════════')
    print('  Summary: In a cloud deployment, access_token() gives your')
    print('  tool the user-scoped token for downstream API calls.')
    print('  No browser needed. No service account. Per-user scoping.')
    print('═══════════════════════════════════════════════════════════════')

asyncio.run(main())
"
    ;;

  clean)
    if [ -d "$VENV_DIR" ]; then
      rm -rf "$VENV_DIR"
      echo "Done — removed demo virtualenv."
    else
      echo "Nothing to clean."
    fi
    ;;

  *)
    echo "Usage: ./scripts/demo-headless.sh [explain|server|client|clean]"
    echo ""
    echo "  explain  — Show the architecture and flow (default)"
    echo "  server   — Start the headless MCP server (SSE, token_exchange mode)"
    echo "  client   — Simulate a platform call with a user token"
    echo "  clean    — Remove demo virtualenv"
    exit 1
    ;;
esac
