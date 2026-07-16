# FastAuthMCP + Google Gemini

Deploy a cloud MCP server that receives user tokens from Google Gemini and exchanges them for downstream API access.

## Scenario

```
Gemini (has user token) → SSE/HTTP → FastAuthMCP server (cloud)
                                          ↓
                                   Token Exchange (RFC 8693)
                                          ↓
                                   Downstream API (user-scoped)
```

This is the **headless/cloud** pattern. No browser. The calling platform (Gemini) passes a user token in the MCP request metadata. FastAuthMCP exchanges it for a downstream-scoped token.

## Setup

### 1. Server code

```python
# server.py
from fastauthmcp import FastMCP, identity, access_token
import httpx

mcp = FastMCP("gemini-backend", config="fastauthmcp.yaml")

@mcp.tool()
def get_calendar() -> list:
    """Fetch the user's calendar events."""
    token = access_token()  # ← user-scoped downstream token
    resp = httpx.get(
        "https://www.googleapis.com/calendar/v3/calendars/primary/events",
        headers={"Authorization": f"Bearer {token}"},
        params={"maxResults": 10},
    )
    return resp.json().get("items", [])

@mcp.tool()
def whoami() -> dict:
    """Show the authenticated user."""
    user = identity()
    return {"email": user.email, "subject": user.subject}
```

### 2. Configuration

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://accounts.google.com
  client_id: your-project-id.apps.googleusercontent.com
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: token_exchange
  token_exchange_provider: google
  upstream_token_header: x-goog-user-token
  token_exchange_audience: "//iam.googleapis.com/projects/YOUR_PROJECT/locations/global/workloadIdentityPools/YOUR_POOL/providers/YOUR_PROVIDER"
  token_exchange_scope: "https://www.googleapis.com/auth/calendar.readonly"
  scopes:
    - openid
    - email
```

### 3. Run

```bash
# Cloud deployment (SSE transport)
FASTAUTHMCP_TRANSPORT=sse \
FASTAUTHMCP_HOST=0.0.0.0 \
FASTAUTHMCP_PORT=8080 \
FASTAUTHMCP_AUTH_CLIENT_SECRET="your-secret" \
  python server.py
```

### 4. How it works

1. Gemini sends an MCP `tools/call` request with the user's Google token in metadata (`x-goog-user-token`)
2. FastAuthMCP extracts the token
3. FastAuthMCP calls Google's STS endpoint to exchange it for a calendar-scoped token
4. Your tool calls `access_token()` → gets the calendar-scoped token
5. Your tool calls the Calendar API with that token

## Google Cloud Setup

### Workload Identity Federation

1. Go to **IAM & Admin → Workload Identity Federation**
2. Create a pool (e.g., `gemini-mcp-pool`)
3. Add a provider (OIDC, issuer: `https://accounts.google.com`)
4. Map attributes (e.g., `google.subject = assertion.sub`)

### Service Account

1. Create a service account for the MCP server
2. Grant it the required API scopes
3. Allow the workload identity pool to impersonate it

### IAM Binding

```bash
gcloud iam service-accounts add-iam-policy-binding \
  mcp-server@your-project.iam.gserviceaccount.com \
  --role=roles/iam.workloadIdentityUser \
  --member="principalSet://iam.googleapis.com/projects/PROJECT_NUMBER/locations/global/workloadIdentityPools/POOL_ID/*"
```

## Alternative: Client Credentials (M2M)

If you don't need per-user token exchange and just want a service identity:

```yaml
auth:
  provider: oidc
  issuer: https://accounts.google.com
  client_id: your-service-account@your-project.iam.gserviceaccount.com
  client_secret: ${GOOGLE_SERVICE_ACCOUNT_KEY}
  grant_type: client_credentials
  scopes:
    - https://www.googleapis.com/auth/calendar.readonly
```

## Deployment on Cloud Run

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY . .
CMD ["python", "server.py"]
```

```yaml
# cloud-run.yaml
env:
  - name: FASTAUTHMCP_TRANSPORT
    value: streamable-http
  - name: FASTAUTHMCP_PORT
    value: "8080"
  - name: FASTAUTHMCP_AUTH_CLIENT_SECRET
    valueFrom:
      secretKeyRef:
        name: mcp-secrets
        key: client-secret
```
