"""Headless MCP server demonstrating token propagation to downstream APIs.

This example shows two key Ceramic features for cloud/headless deployments:

1. **access_token()** — Exposes the authenticated user's token to tool code
   so it can be propagated to downstream API calls.

2. **token_exchange** — Accepts an upstream user token (from the MCP transport
   layer / calling platform) and exchanges it at the IDP for a scoped
   downstream token via RFC 8693.

This server is meant to run as an SSE or HTTP server (not stdio) because
headless = no browser = cloud deployment.

Usage:
    # Start as SSE server (the headless/cloud way)
    CERAMIC_TRANSPORT=sse python examples/headless_server.py

    # Start as streamable-http server
    CERAMIC_TRANSPORT=streamable-http python examples/headless_server.py

    # Or use the demo script:
    ./scripts/demo-headless.sh server

Configuration:
    See examples/headless_ceramic.yaml for the token_exchange config.
"""

from __future__ import annotations

import os

import httpx

from ceramic import FastMCP, access_token, identity

# ---------------------------------------------------------------------------
# Server setup
# ---------------------------------------------------------------------------

config_file = os.environ.get("CERAMIC_CONFIG", "headless_ceramic.yaml")
mcp = FastMCP("headless-api", config=config_file)


# ---------------------------------------------------------------------------
# Tools that propagate tokens to downstream APIs
# ---------------------------------------------------------------------------


@mcp.tool()
def whoami() -> dict:
    """Show current authenticated user and confirm token availability."""
    user = identity()
    token = access_token()
    return {
        "email": user.email,
        "subject": user.subject,
        "roles": sorted(user.roles),
        "token_available": bool(token),
        "token_preview": token[:20] + "..." if len(token) > 20 else token,
    }


@mcp.tool()
def call_downstream_api(endpoint: str) -> dict:
    """Call a downstream API using the authenticated user's token.

    This demonstrates the key use case: your MCP tool needs to call an
    internal API on behalf of the user. The token is automatically valid
    and scoped to the user.

    Args:
        endpoint: The downstream API URL to call (e.g. https://api.example.com/orders)
    """
    user = identity()
    token = access_token()

    # Propagate the user's token to the downstream API
    try:
        resp = httpx.get(
            endpoint,
            headers={
                "Authorization": f"Bearer {token}",
                "X-Request-Source": "ceramic-mcp",
            },
            timeout=10,
        )
        return {
            "status": resp.status_code,
            "called_as": user.email,
            "response_preview": resp.text[:200],
        }
    except httpx.RequestError as exc:
        return {
            "error": "downstream_unreachable",
            "message": str(exc),
            "called_as": user.email,
        }


@mcp.tool()
def get_user_data() -> dict:
    """Fetch user profile from the IDP's userinfo endpoint.

    Demonstrates calling the IDP's userinfo endpoint directly with the
    user's access token — proving the token is valid and user-scoped.
    """
    token = access_token()

    try:
        # Most OIDC providers have a /userinfo endpoint
        resp = httpx.get(
            "https://ceramic-oss-agq8i8.eu1.zitadel.cloud/oidc/v1/userinfo",
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        if resp.status_code == 200:
            return {"userinfo": resp.json()}
        return {"error": f"userinfo returned {resp.status_code}"}
    except httpx.RequestError as exc:
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import logging

    log_level = os.environ.get("CERAMIC_LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    transport = os.environ.get("CERAMIC_TRANSPORT", "sse")
    host = os.environ.get("CERAMIC_HOST", "localhost")
    port = int(os.environ.get("CERAMIC_PORT", "8001"))
    mcp.run(transport=transport, host=host, port=port)
