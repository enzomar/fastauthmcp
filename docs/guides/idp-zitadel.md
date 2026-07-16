# FastAuthMCP + Zitadel

Complete guide for integrating FastAuthMCP with [Zitadel](https://zitadel.com/) — cloud or self-hosted.

## Supported Grant Types

| Grant Type | Use Case | Zitadel Support |
|------------|----------|-----------------|
| Authorization Code + PKCE | Local dev, CLI tools | ✓ Native app |
| Client Credentials | Remote M2M services | ✓ Service user |
| Token Exchange (RFC 8693) | Cloud headless MCP | ✓ Native support |

## Authorization Code + PKCE (Interactive)

### Zitadel Configuration

1. Go to your Zitadel project → Applications → New
2. Type: **Native**
3. Redirect URI: `http://localhost:9876/callback`
4. Auth method: None (PKCE)
5. Copy the Client ID

### FastAuthMCP Config

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://your-org-xyz.zitadel.cloud
  client_id: "your-client-id"
  scopes:
    - openid
    - profile
    - email
    - "urn:zitadel:iam:org:project:roles"
  callback_port: 9876
```

### Claude Desktop Config

```json
{
  "mcpServers": {
    "my-server": {
      "command": "python",
      "args": ["server.py"],
      "env": {
        "FASTAUTHMCP_CONFIG": "fastauthmcp.yaml"
      }
    }
  }
}
```

## Client Credentials (M2M)

### Zitadel Configuration

1. Go to your project → Users → Service Users → New
2. Create a service user
3. Go to the service user → Personal Access Tokens or Keys
4. For client credentials: set up machine key or use basic auth

### FastAuthMCP Config

```yaml
auth:
  provider: oidc
  issuer: https://your-org-xyz.zitadel.cloud
  client_id: "service-user-client-id"
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: client_credentials
  scopes:
    - openid
    - "urn:zitadel:iam:org:project:roles"
```

### Run

```bash
export FASTAUTHMCP_AUTH_CLIENT_SECRET="your-service-user-secret"
FASTAUTHMCP_TRANSPORT=sse python server.py
```

## Token Exchange (RFC 8693)

Zitadel natively supports RFC 8693 token exchange — ideal for cloud MCP deployments.

### Zitadel Configuration

1. Create an application (API type) for the MCP server
2. Enable "Token Exchange" on the application
3. Configure allowed token exchange targets

### FastAuthMCP Config

```yaml
auth:
  provider: oidc
  issuer: https://your-org-xyz.zitadel.cloud
  client_id: "mcp-server-client-id"
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: token_exchange
  upstream_token_header: x-user-token
  token_exchange_audience: "your-downstream-api-project-id"
  token_exchange_scope: "openid profile email"
  scopes:
    - openid
    - profile
    - email
```

## Role-Based Access Control

Zitadel includes project roles in the `urn:zitadel:iam:org:project:id:{project_id}:roles` claim.

### Server code

```python
from fastauthmcp import FastMCP, require_roles

mcp = FastMCP("secure-server", config="fastauthmcp.yaml")

@mcp.tool()
@require_roles("admin")
def admin_action() -> str:
    return "admin access granted"
```

### Custom role claim path

```yaml
# In fastauthmcp.yaml, specify the claim path for roles:
auth:
  provider: oidc
  issuer: https://your-org-xyz.zitadel.cloud
  client_id: "your-client-id"
  scopes:
    - openid
    - "urn:zitadel:iam:org:project:roles"
```

In your server initialization, configure the role claim path:

```python
# Zitadel uses a nested structure for roles
# The middleware default is "realm_access.roles" (Keycloak style)
# For Zitadel, roles appear at the top level of the token
```

## Complete Example

See `examples/zitadel/` in the repository for a working petstore server with full Zitadel integration.

```bash
cd examples/zitadel
python petstore_server.py
```
