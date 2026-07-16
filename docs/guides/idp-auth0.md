# FastAuthMCP + Auth0

Integrate FastAuthMCP with [Auth0](https://auth0.com/) (by Okta).

## Supported Grant Types

| Grant Type | Use Case | Auth0 Support |
|------------|----------|---------------|
| Authorization Code + PKCE | Local dev, CLI tools | ✓ Native app |
| Client Credentials | Remote M2M services | ✓ Machine-to-Machine app |
| Token Exchange | Cloud headless MCP | ✓ Via Actions/custom |

## Authorization Code + PKCE (Interactive)

### Auth0 Configuration

1. **Applications** → Create Application
2. Type: **Native**
3. Settings:
   - Allowed Callback URLs: `http://localhost:9876/callback`
   - Grant Types: Authorization Code
4. Copy **Domain**, **Client ID**

### FastAuthMCP Config

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://your-tenant.auth0.com
  client_id: "your-client-id"
  scopes:
    - openid
    - profile
    - email
  callback_port: 9876
```

### Claude Desktop Config

```json
{
  "mcpServers": {
    "auth0-server": {
      "command": "python",
      "args": ["server.py"]
    }
  }
}
```

## Client Credentials (M2M)

### Auth0 Configuration

1. **Applications** → Create Application
2. Type: **Machine to Machine**
3. Authorize the APIs you need
4. Copy **Client ID** and **Client Secret**

### FastAuthMCP Config

```yaml
auth:
  provider: oidc
  issuer: https://your-tenant.auth0.com
  client_id: "m2m-client-id"
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: client_credentials
  scopes:
    - "read:data"
    - "write:data"
```

## Role-Based Access Control

### Auth0 Setup — RBAC

1. **User Management** → Roles → Create Role (e.g., `admin`, `editor`)
2. Assign roles to users
3. **APIs** → Your API → Settings → Enable RBAC + Add Permissions in Access Token

### Add roles to token via Auth0 Action

Create a **Login** action:

```javascript
exports.onExecutePostLogin = async (event, api) => {
  const namespace = 'https://fastauthmcp.dev';
  if (event.authorization) {
    api.accessToken.setCustomClaim(
      `${namespace}/roles`,
      event.authorization.roles
    );
    api.idToken.setCustomClaim(
      `${namespace}/roles`,
      event.authorization.roles
    );
  }
};
```

### Server code

```python
from fastauthmcp import FastMCP, require_roles

mcp = FastMCP("auth0-server", config="fastauthmcp.yaml")

@mcp.tool()
@require_roles("admin")
def admin_dashboard() -> dict:
    return {"status": "admin access granted"}
```

Note: Auth0 puts custom claims in a namespaced key. You may need to configure the role claim path if not using the default.

## Token Exchange (via Auth0 Actions)

Auth0 doesn't natively support RFC 8693, but you can implement token exchange using Actions or the Management API.

### Alternative: Use Client Credentials + custom claims

For cloud MCP deployments, the simpler approach with Auth0 is:

1. Your agent authenticates with client credentials
2. Pass user context via custom metadata
3. Use Auth0 Actions to enrich the token with user-specific claims

```yaml
auth:
  provider: oidc
  issuer: https://your-tenant.auth0.com
  client_id: "cloud-mcp-client"
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: client_credentials
  scopes: ["read:data"]
```

## Custom Domain

If you use a custom domain with Auth0:

```yaml
auth:
  issuer: https://auth.your-company.com
  client_id: "your-client-id"
```

The OIDC discovery URL will be `https://auth.your-company.com/.well-known/openid-configuration`.
