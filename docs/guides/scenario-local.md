# Local Development Deployment

Run FastAuthMCP on your developer laptop with browser-based authentication.

## Architecture

```
MCP Client (Claude/Cursor)
        │ stdio
        ▼
FastAuthMCP Server (local process)
        │
        ├── Browser login (first call only)
        ├── Token stored in Keychain/Credential Manager
        │
        ▼
Downstream APIs (authenticated with user's token)
```

## When to Use

- Development and testing
- Personal tools
- CLI-based workflows
- Any scenario where a browser is available

## Config Template

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://YOUR_IDP_HERE
  client_id: YOUR_CLIENT_ID
  scopes:
    - openid
    - profile
    - email
  callback_port: 9876
  callback_timeout: 120

observability:
  enabled: true
  exporter: console
  log_format: text
  log_level: info
```

## Server Template

```python
# server.py
from fastauthmcp import FastMCP, identity, access_token
import httpx

mcp = FastMCP("my-tools", config="fastauthmcp.yaml")

@mcp.tool()
def whoami() -> dict:
    """Show authenticated user."""
    user = identity()
    return {"email": user.email, "roles": sorted(user.roles)}

@mcp.tool()
def call_api(endpoint: str) -> dict:
    """Call a downstream API with the user's token."""
    token = access_token()
    resp = httpx.get(
        f"https://api.your-org.com{endpoint}",
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp.json()

if __name__ == "__main__":
    mcp.run()  # stdio by default
```

## Platform Configs

### Claude Desktop

```json
{
  "mcpServers": {
    "my-tools": {
      "command": "python",
      "args": ["/path/to/server.py"]
    }
  }
}
```

### Cursor IDE (SSE mode)

```bash
FASTAUTHMCP_TRANSPORT=sse python server.py
```

Then in Cursor: add MCP server URL `http://localhost:8000/sse`

## Token Lifecycle

1. **First tool call** → browser opens → login → token stored
2. **Subsequent calls** → token loaded from storage → tool executes
3. **Token expired** → auto-refresh (if refresh_token available) → tool executes
4. **Refresh failed** → browser login again
5. **Manual logout** → `fastauthmcp logout`

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Browser doesn't open | Check `callback_port` isn't blocked |
| Login succeeds but tool fails | Check IDP redirect URI includes `/callback` |
| Token expired immediately | Check system clock sync |
| "Callback not received" | Increase `callback_timeout` |
