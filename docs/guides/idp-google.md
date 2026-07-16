# FastAuthMCP + Google Cloud IAM

Integrate FastAuthMCP with Google accounts and Google Cloud workload identity.

## Supported Grant Types

| Grant Type | Use Case | Google Support |
|------------|----------|----------------|
| Authorization Code + PKCE | Local dev (personal Google) | ✓ OAuth client |
| Service Account | Remote M2M services | ✓ Service account key |
| Token Exchange (STS) | Cloud headless MCP | ✓ Workload Identity Federation |

## Authorization Code + PKCE (Interactive)

For local tools authenticated with a Google account.

### Google Cloud Console Configuration

1. **APIs & Services** → Credentials → Create OAuth Client ID
2. Application type: **Desktop application**
3. Name: `fastauthmcp-local`
4. Authorized redirect URIs: `http://localhost:9876/callback`
5. Copy **Client ID**

### FastAuthMCP Config

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://accounts.google.com
  client_id: "your-client-id.apps.googleusercontent.com"
  scopes:
    - openid
    - profile
    - email
    - "https://www.googleapis.com/auth/calendar.readonly"
  callback_port: 9876
```

### Claude Desktop Config

```json
{
  "mcpServers": {
    "google-tools": {
      "command": "python",
      "args": ["server.py"]
    }
  }
}
```

### Server code

```python
from fastauthmcp import FastMCP, access_token
import httpx

mcp = FastMCP("google-tools", config="fastauthmcp.yaml")

@mcp.tool()
def my_calendar() -> list:
    """Get upcoming Google Calendar events."""
    token = access_token()
    resp = httpx.get(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        headers={"Authorization": f"Bearer {token}"},
        params={"maxResults": 5, "orderBy": "startTime", "singleEvents": True},
    )
    events = resp.json().get("items", [])
    return [{"summary": e.get("summary"), "start": e["start"].get("dateTime")} for e in events]
```

## Token Exchange (Workload Identity Federation)

For cloud MCP servers that receive a user token from the calling platform and exchange it for Google API access.

### Google Cloud Setup

1. **Workload Identity Federation** → Create pool
2. Add OIDC provider (your calling platform's issuer)
3. Create a service account
4. Bind the service account to the pool

### FastAuthMCP Config

```yaml
auth:
  provider: oidc
  issuer: https://accounts.google.com
  client_id: "your-cloud-app.apps.googleusercontent.com"
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: token_exchange
  token_exchange_provider: google
  upstream_token_header: x-user-token
  token_exchange_audience: "//iam.googleapis.com/projects/PROJECT_NUM/locations/global/workloadIdentityPools/POOL/providers/PROVIDER"
  token_exchange_scope: "https://www.googleapis.com/auth/cloud-platform"
```

### How Google STS Exchange Works

```
Incoming user token → Google STS (sts.googleapis.com/v1/token)
                            ↓
                    Federated token → impersonate service account
                            ↓
                    Scoped access token for Google APIs
```

FastAuthMCP's `google` adapter handles the camelCase parameter format and the STS endpoint URL automatically.

## Service Account (M2M)

For server-to-server without user context. Uses a service account JWT to get an access token.

### Setup

1. Create a service account in Google Cloud Console
2. Download the JSON key file
3. Grant it the required roles/permissions

### FastAuthMCP Config

```yaml
auth:
  provider: oidc
  issuer: https://accounts.google.com
  client_id: "service-account@your-project.iam.gserviceaccount.com"
  client_secret: ${GOOGLE_SERVICE_ACCOUNT_KEY_JSON}
  grant_type: client_credentials
  scopes:
    - "https://www.googleapis.com/auth/drive.readonly"
```

Note: For Google service accounts, you may need a custom token acquisition flow using the `google-auth` library. The standard `client_credentials` grant works with Google's OAuth2 token endpoint when using a service account key.

## Google Workspace Integration

Access user data in Google Workspace (Drive, Gmail, Calendar):

```python
@mcp.tool()
def search_drive(query: str) -> list:
    """Search Google Drive files."""
    token = access_token()
    resp = httpx.get(
        "https://www.googleapis.com/drive/v3/files",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": query, "pageSize": 10},
    )
    files = resp.json().get("files", [])
    return [{"name": f["name"], "id": f["id"]} for f in files]
```

Required scope: `https://www.googleapis.com/auth/drive.readonly`
