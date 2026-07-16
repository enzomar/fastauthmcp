# FastAuthMCP + Azure Entra ID

Integrate FastAuthMCP with [Microsoft Entra ID](https://learn.microsoft.com/en-us/entra/identity/) (formerly Azure AD).

## Supported Grant Types

| Grant Type | Use Case | Entra ID Support |
|------------|----------|------------------|
| Authorization Code + PKCE | Local dev, CLI tools | ✓ Public client |
| Client Credentials | Remote M2M services | ✓ App registration + secret |
| On-Behalf-Of (OBO) | Cloud headless MCP | ✓ Confidential client |

## Authorization Code + PKCE (Interactive)

### Azure Portal Configuration

1. **App registrations** → New registration
2. Name: `fastauthmcp-local`
3. Supported account types: Single tenant (or multi-tenant)
4. Redirect URI: **Mobile and desktop applications** → `http://localhost:9876/callback`
5. Save → copy **Application (client) ID** and **Directory (tenant) ID**
6. **Authentication** → Allow public client flows: **Yes**

### FastAuthMCP Config

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://login.microsoftonline.com/YOUR_TENANT_ID/v2.0
  client_id: "your-application-client-id"
  scopes:
    - openid
    - profile
    - email
    - "api://your-api-id/read"
  callback_port: 9876
```

### Claude Desktop Config

```json
{
  "mcpServers": {
    "azure-tools": {
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

### Azure Portal Configuration

1. **App registrations** → New registration
2. **Certificates & secrets** → New client secret → copy value
3. **API permissions** → Add required permissions

### FastAuthMCP Config

```yaml
auth:
  provider: oidc
  issuer: https://login.microsoftonline.com/YOUR_TENANT_ID/v2.0
  client_id: "service-app-client-id"
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: client_credentials
  scopes:
    - "https://graph.microsoft.com/.default"
```

## On-Behalf-Of (Token Exchange)

The OBO flow lets your MCP server call Microsoft Graph or other APIs on behalf of the signed-in user.

### Azure Portal Configuration

1. Create an app registration for the MCP server (confidential client)
2. **API permissions** → Add Graph permissions (delegated)
3. **Expose an API** → Add a scope (e.g., `api://mcp-server/access`)
4. The calling app must request this scope

### FastAuthMCP Config

```yaml
auth:
  provider: oidc
  issuer: https://login.microsoftonline.com/YOUR_TENANT_ID/v2.0
  client_id: "mcp-server-app-id"
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: token_exchange
  token_exchange_provider: entra
  upstream_token_header: authorization
  token_exchange_scope: "https://graph.microsoft.com/User.Read https://graph.microsoft.com/Calendar.Read"
  scopes:
    - openid
    - profile
```

### Server code

```python
from fastauthmcp import FastMCP, access_token
import httpx

mcp = FastMCP("azure-tools", config="fastauthmcp.yaml")

@mcp.tool()
def my_profile() -> dict:
    """Get the user's Microsoft profile via Graph API."""
    token = access_token()  # OBO-exchanged token scoped for Graph
    resp = httpx.get(
        "https://graph.microsoft.com/v1.0/me",
        headers={"Authorization": f"Bearer {token}"},
    )
    data = resp.json()
    return {"name": data.get("displayName"), "email": data.get("mail")}

@mcp.tool()
def my_calendar() -> list:
    """Get upcoming calendar events."""
    token = access_token()
    resp = httpx.get(
        "https://graph.microsoft.com/v1.0/me/events",
        headers={"Authorization": f"Bearer {token}"},
        params={"$top": 5, "$orderby": "start/dateTime"},
    )
    events = resp.json().get("value", [])
    return [{"subject": e["subject"], "start": e["start"]["dateTime"]} for e in events]
```

## Role-Based Access (Entra ID App Roles)

### Azure Portal

1. App registration → **App roles** → Create role (e.g., `Admin`, `Reader`)
2. Assign users to roles in **Enterprise applications**

### Token claim path

Entra ID puts app roles in the `roles` claim at the top level of the access token.

```python
from fastauthmcp import require_roles

@mcp.tool()
@require_roles("Admin")
def admin_action() -> str:
    return "admin access via Entra ID"
```

## Group Claims

Enable group claims in the token:
1. App registration → **Token configuration** → Add groups claim
2. Select: Security groups / All groups

Groups appear in the `groups` claim as object IDs. Map them using a custom middleware or use group names if your tenant supports it.
