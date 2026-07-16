# FastAuthMCP + Cursor IDE

Run a development MCP server with SSE transport and browser-based authentication for Cursor.

## Scenario

```
Cursor IDE → SSE (http://localhost:8000/sse) → FastAuthMCP server
                                                    ↓
                                          Browser login (first call)
                                          Token stored in Keychain
                                                    ↓
                                            Downstream APIs
```

## Setup

### 1. Server code

```python
# server.py
from fastauthmcp import FastMCP, identity, access_token
import httpx

mcp = FastMCP("dev-tools", config="fastauthmcp.yaml")

@mcp.tool()
def whoami() -> dict:
    """Show the current authenticated developer."""
    user = identity()
    return {"email": user.email, "roles": sorted(user.roles)}

@mcp.tool()
def list_repos() -> list:
    """List GitHub repos using the developer's token."""
    token = access_token()
    resp = httpx.get(
        "https://api.github.com/user/repos",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"},
        params={"per_page": 10, "sort": "updated"},
    )
    return [{"name": r["name"], "url": r["html_url"]} for r in resp.json()]

@mcp.tool()
def create_issue(repo: str, title: str, body: str) -> dict:
    """Create a GitHub issue."""
    token = access_token()
    resp = httpx.post(
        f"https://api.github.com/repos/{repo}/issues",
        headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github.v3+json"},
        json={"title": title, "body": body},
    )
    data = resp.json()
    return {"number": data["number"], "url": data["html_url"]}
```

### 2. Configuration

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: cursor-dev-tools
  scopes:
    - openid
    - profile
    - email
  callback_port: 9876

observability:
  enabled: true
  exporter: console
  log_format: text
  log_level: info
```

### 3. Run the server

```bash
# Start with SSE transport
FASTAUTHMCP_TRANSPORT=sse python server.py
```

### 4. Configure Cursor

In Cursor settings, add the MCP server:

```json
{
  "mcpServers": {
    "dev-tools": {
      "url": "http://localhost:8000/sse"
    }
  }
}
```

Or via Cursor's MCP settings UI: add a new server with URL `http://localhost:8000/sse`.

### 5. First use

When you use a tool in Cursor for the first time, your browser will open for authentication. After login, all subsequent calls are authenticated automatically.

## With Makefile

```makefile
dev-server: ## Start the MCP dev server for Cursor
	FASTAUTHMCP_TRANSPORT=sse FASTAUTHMCP_LOG_LEVEL=info python server.py
```

## IDP Examples

### GitHub as IDP (via Auth0/Zitadel)

If your team uses GitHub for SSO:

```yaml
# With Auth0 + GitHub social connection
auth:
  provider: oidc
  issuer: https://your-team.auth0.com
  client_id: cursor-mcp-app
  scopes: [openid, profile, email]
```

### Google Workspace

```yaml
auth:
  provider: oidc
  issuer: https://accounts.google.com
  client_id: your-app-id.apps.googleusercontent.com
  scopes: [openid, profile, email]
```

Google Cloud Console:
- Create OAuth client → Desktop application
- Authorized redirect URIs: `http://localhost:9876/callback`

### Okta (corporate SSO)

```yaml
auth:
  provider: oidc
  issuer: https://your-company.okta.com/oauth2/default
  client_id: cursor-dev-tools-app
  scopes: [openid, profile, email, groups]
```
