# FastAuthMCP + Claude Desktop

Secure your MCP server for Claude Desktop with browser-based OAuth2 login.

## Scenario

```
Claude Desktop → stdio → FastAuthMCP server → downstream APIs
                              ↓
                    Browser login (first call)
                    Token stored in Keychain
```

## Setup

### 1. Create your server

```python
# server.py
from fastauthmcp import FastMCP, identity, access_token
import httpx

mcp = FastMCP("my-secure-server", config="fastauthmcp.yaml")

@mcp.tool()
def whoami() -> dict:
    """Show who is authenticated."""
    user = identity()
    return {"email": user.email, "roles": sorted(user.roles)}

@mcp.tool()
def get_orders() -> list:
    """Fetch orders from internal API using the user's token."""
    token = access_token()
    resp = httpx.get(
        "https://api.internal.com/v1/orders",
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp.json()
```

### 2. Configure authentication

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: my-claude-mcp-app
  scopes:
    - openid
    - profile
    - email
  callback_port: 9876
```

### 3. Configure Claude Desktop

Edit `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "my-secure-server": {
      "command": "python",
      "args": ["/path/to/server.py"],
      "env": {
        "FASTAUTHMCP_CONFIG": "/path/to/fastauthmcp.yaml"
      }
    }
  }
}
```

### 4. First use

When Claude calls a tool for the first time:

1. Your browser opens to the IDP login page
2. You log in with your credentials
3. Browser redirects to `localhost:9876/callback`
4. Token is stored in macOS Keychain
5. All subsequent calls use the stored token (auto-refreshes)

## IDP-Specific Examples

### With Zitadel

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://your-org.zitadel.cloud
  client_id: "your-app-client-id"
  scopes:
    - openid
    - profile
    - email
    - "urn:zitadel:iam:org:project:roles"
```

Zitadel app config:
- Type: **Native** (PKCE, no client secret)
- Redirect URI: `http://localhost:9876/callback`

### With Keycloak

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://keycloak.your-org.com/realms/your-realm
  client_id: claude-mcp
  scopes:
    - openid
    - profile
    - email
    - roles
```

Keycloak client config:
- Client type: **Public**
- Standard flow enabled: Yes
- Valid redirect URIs: `http://localhost:9876/callback`

### With Auth0

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://your-tenant.auth0.com
  client_id: your-app-client-id
  scopes:
    - openid
    - profile
    - email
```

Auth0 application config:
- Type: **Native**
- Allowed Callback URLs: `http://localhost:9876/callback`
- Grant Types: Authorization Code

### With Azure Entra ID

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://login.microsoftonline.com/your-tenant-id/v2.0
  client_id: your-app-registration-id
  scopes:
    - openid
    - profile
    - email
    - "api://your-api/read"
```

Azure App Registration:
- Platform: **Mobile and desktop** (for public client)
- Redirect URI: `http://localhost:9876/callback`
- Allow public client flows: Yes

### With Okta

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://your-org.okta.com/oauth2/default
  client_id: your-app-client-id
  scopes:
    - openid
    - profile
    - email
```

Okta application config:
- Type: **Native App**
- Sign-in redirect URIs: `http://localhost:9876/callback`
- Grant type: Authorization Code + PKCE

## Tips

- **Token refresh**: FastAuthMCP auto-refreshes expired tokens before each tool call. No user interaction needed after the initial login.
- **Logout**: Run `fastauthmcp logout` to clear stored tokens.
- **Multiple IDPs**: Use separate `fastauthmcp.yaml` files for different servers.
- **Firewall**: No inbound ports needed — the callback server only listens during login.
