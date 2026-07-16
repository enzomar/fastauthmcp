# FastAuthMCP + Okta

Integrate FastAuthMCP with [Okta](https://www.okta.com/) workforce or customer identity.

## Supported Grant Types

| Grant Type | Use Case | Okta Support |
|------------|----------|--------------|
| Authorization Code + PKCE | Local dev, CLI tools | ✓ Native/SPA app |
| Client Credentials | Remote M2M services | ✓ Service app |
| Token Exchange | Cloud headless MCP | ✓ Via Authorization Servers |

## Authorization Code + PKCE (Interactive)

### Okta Configuration

1. **Applications** → Create App Integration
2. Sign-in method: **OIDC**
3. Application type: **Native Application**
4. Sign-in redirect URIs: `http://localhost:9876/callback`
5. Assignments: Assign users/groups
6. Copy **Client ID** and your **Okta domain**

### FastAuthMCP Config

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://your-org.okta.com/oauth2/default
  client_id: "your-client-id"
  scopes:
    - openid
    - profile
    - email
    - groups
  callback_port: 9876
```

### Claude Desktop Config

```json
{
  "mcpServers": {
    "okta-server": {
      "command": "python",
      "args": ["server.py"]
    }
  }
}
```

## Client Credentials (M2M)

### Okta Configuration

1. **Applications** → Create App Integration
2. Sign-in method: **API Services** (or OIDC → Service app)
3. Copy **Client ID** and **Client Secret**
4. **Security** → API → Your Authorization Server → Scopes → add custom scopes

### FastAuthMCP Config

```yaml
auth:
  provider: oidc
  issuer: https://your-org.okta.com/oauth2/default
  client_id: "service-client-id"
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: client_credentials
  scopes:
    - "mcp.read"
    - "mcp.write"
```

## Role-Based Access Control

### Okta Setup — Groups as Roles

1. **Directory** → Groups → Create groups (e.g., `mcp-admins`, `mcp-users`)
2. Assign users to groups
3. **Applications** → Your app → Sign On → OpenID Connect ID Token → Groups claim → Add `groups`

### Custom Authorization Server Claims

1. **Security** → API → default Authorization Server
2. Claims → Add Claim:
   - Name: `roles`
   - Include in: Access Token
   - Value: `appuser.getGroups()`
   - Filter: Matches regex `mcp-.*`

### Server code

```python
from fastauthmcp import FastMCP, require_roles

mcp = FastMCP("okta-server", config="fastauthmcp.yaml")

@mcp.tool()
@require_roles("mcp-admins")
def admin_action() -> str:
    return "Okta admin access granted"
```

## Custom Authorization Server

If you use a custom authorization server (not `default`):

```yaml
auth:
  issuer: https://your-org.okta.com/oauth2/your-auth-server-id
  client_id: "your-client-id"
```

## Okta Workforce Identity + Gemini/Cloud

For cloud MCP deployments where Okta is the corporate IDP:

```yaml
auth:
  provider: oidc
  issuer: https://your-org.okta.com/oauth2/default
  client_id: "cloud-mcp-server"
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: token_exchange
  upstream_token_header: x-user-token
  token_exchange_audience: "api://your-downstream-api"
  scopes: [openid, profile, email]
```

Note: Okta's token exchange support depends on your plan and authorization server configuration. Check Okta's documentation for your specific setup.
