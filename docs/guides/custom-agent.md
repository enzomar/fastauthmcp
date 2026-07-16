# FastAuthMCP + Custom MCP Agent

Build your own authenticated MCP client that connects to a FastAuthMCP-protected server.

## Scenario

```
Your Agent (Python/Node) → stdio/SSE/HTTP → FastAuthMCP server
                                                  ↓
                                        Authentication middleware
                                                  ↓
                                           Tools execute with identity
```

## Client-Side: Passing Tokens

### Option A: Let FastAuthMCP handle auth (stdio)

When using stdio transport, FastAuthMCP handles the entire OAuth flow inside the server process:

```python
from fastmcp import Client
from fastmcp.client.transports import PythonStdioTransport

async def main():
    transport = PythonStdioTransport(script_path="server.py")
    async with Client(transport, timeout=300) as client:
        # First tool call triggers browser login
        result = await client.call_tool("whoami", {})
        print(result)
```

### Option B: Pass token via metadata (SSE/HTTP)

For remote servers, your agent provides the token:

```python
import httpx
from fastmcp import Client

async def main():
    # Get a token from your auth system
    token = await get_access_token()

    # Connect to the MCP server
    async with Client("http://localhost:8000/sse") as client:
        # Pass token in metadata
        result = await client.call_tool(
            "whoami",
            {},
            metadata={"authorization": f"Bearer {token}"},
        )
        print(result)
```

### Option C: Token exchange (cloud deployment)

Your agent has a user token from its own auth. Pass it to the MCP server for exchange:

```python
async with Client("https://mcp.your-org.com/sse") as client:
    result = await client.call_tool(
        "get_data",
        {"query": "status"},
        metadata={"x-user-token": user_access_token},
    )
```

Server config for token exchange:

```yaml
auth:
  grant_type: token_exchange
  upstream_token_header: x-user-token
  token_exchange_audience: https://api.internal.com
```

## Server-Side Configurations

### Minimal (stdio, browser login)

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: your-app
  scopes: [openid, profile, email]
```

### Remote (SSE, client credentials)

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: mcp-service
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: client_credentials
  scopes: [openid, profile]
```

### Cloud (HTTP, token exchange)

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: mcp-cloud-server
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: token_exchange
  upstream_token_header: authorization
  token_exchange_audience: https://downstream-api.example.com
```

## Testing Your Agent

Use `FastAuthMCPTestClient` to test without a real IDP:

```python
from fastauthmcp.testing import FastAuthMCPTestClient

async def test_my_agent_flow():
    client = FastAuthMCPTestClient(
        app=my_server,
        email="agent@example.com",
        subject="agent-001",
        roles=["service"],
    )

    result = await client.call_tool("get_data", query="test")
    assert "error" not in result
```
