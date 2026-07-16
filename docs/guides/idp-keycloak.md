# FastAuthMCP + Keycloak

Integrate FastAuthMCP with [Keycloak](https://www.keycloak.org/) — self-hosted or managed.

## Supported Grant Types

| Grant Type | Use Case | Keycloak Support |
|------------|----------|------------------|
| Authorization Code + PKCE | Local dev, CLI tools | ✓ Public client |
| Client Credentials | Remote M2M services | ✓ Confidential client |
| Token Exchange | Cloud headless MCP | ✓ Built-in |

## Authorization Code + PKCE (Interactive)

### Keycloak Configuration

1. Realm → Clients → Create
2. Client type: **OpenID Connect**
3. Client authentication: **OFF** (public client for PKCE)
4. Standard flow: **ON**
5. Valid redirect URIs: `http://localhost:9876/callback`
6. Save → copy the Client ID

### FastAuthMCP Config

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://keycloak.your-org.com/realms/your-realm
  client_id: my-mcp-app
  scopes:
    - openid
    - profile
    - email
    - roles
  callback_port: 9876
```

### Claude Desktop Config

```json
{
  "mcpServers": {
    "my-keycloak-server": {
      "command": "python",
      "args": ["server.py"]
    }
  }
}
```

## Client Credentials (M2M)

### Keycloak Configuration

1. Realm → Clients → Create
2. Client type: **OpenID Connect**
3. Client authentication: **ON** (confidential client)
4. Service accounts roles: **ON**
5. Save → Credentials tab → copy Secret

### FastAuthMCP Config

```yaml
auth:
  provider: oidc
  issuer: https://keycloak.your-org.com/realms/your-realm
  client_id: mcp-service
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: client_credentials
  scopes:
    - openid
    - profile
```

## Role-Based Access Control

Keycloak puts roles in `realm_access.roles` by default — this matches FastAuthMCP's default claim path.

### Keycloak Setup

1. Realm → Realm roles → Create role (e.g., `admin`, `viewer`)
2. Users → Assign roles

### Server code

```python
from fastauthmcp import FastMCP, require_roles, identity

mcp = FastMCP("rbac-server", config="fastauthmcp.yaml")

@mcp.tool()
@require_roles("admin")
def admin_dashboard() -> dict:
    user = identity()
    return {"user": user.email, "access": "admin"}

@mcp.tool()
def public_info() -> str:
    return "anyone can see this"
```

Roles are automatically extracted from `realm_access.roles` in the JWT.

## Group-Based Access Control

Keycloak groups appear in the `groups` claim when the "groups" client scope is configured.

### Keycloak Setup

1. Client scopes → Create → Name: `groups`
2. Mappers → Add → Type: Group Membership → Token claim name: `groups`
3. Client → Client scopes → Add `groups`

### FastAuthMCP

```python
from fastauthmcp import require_groups

@mcp.tool()
@require_groups("platform-team")
def deploy(service: str) -> str:
    return f"deploying {service}"
```

## Docker (local development)

```yaml
# docker-compose.yml
services:
  keycloak:
    image: quay.io/keycloak/keycloak:25.0
    command: start-dev
    environment:
      KC_BOOTSTRAP_ADMIN_USERNAME: admin
      KC_BOOTSTRAP_ADMIN_PASSWORD: admin
    ports:
      - "8080:8080"
```

```bash
docker compose up -d
# Access admin: http://localhost:8080/admin
# Issuer: http://localhost:8080/realms/your-realm
```

Config for local Keycloak:

```yaml
auth:
  provider: oidc
  issuer: http://localhost:8080/realms/my-realm
  client_id: my-local-app
  scopes: [openid, profile, email]
```
