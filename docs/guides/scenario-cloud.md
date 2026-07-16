# Cloud Deployment

Deploy FastAuthMCP in the cloud with headless authentication (no browser).

## Architecture

```
Calling Platform (Claude/Gemini/Custom)
        │ SSE or streamable-http
        │ + user token in metadata
        ▼
FastAuthMCP Server (cloud container)
        │
        ├── Extract upstream token
        ├── Exchange at IDP (RFC 8693)
        ├── Get downstream-scoped token
        │
        ▼
Downstream APIs (user-scoped access)
```

## When to Use

- Cloud-hosted MCP servers (Cloud Run, K8s, ECS)
- Multi-user environments
- When the calling platform provides a user token
- No browser available

## Grant Type Options

| Pattern | Config | Best For |
|---------|--------|----------|
| Token Exchange | `grant_type: token_exchange` | Per-user downstream access |
| Client Credentials | `grant_type: client_credentials` | Service identity (shared) |

## Token Exchange Config Template

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://YOUR_IDP
  client_id: mcp-cloud-server
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: token_exchange
  upstream_token_header: x-user-token
  token_exchange_audience: https://api.downstream.com
  token_exchange_scope: "read:data write:data"
  scopes:
    - openid
    - profile
    - email

sessions:
  enabled: false  # Stateless — each request carries its own token

observability:
  enabled: true
  exporter: otlp
  otlp_endpoint: ${OTEL_ENDPOINT:-http://localhost:4317}
  log_format: json
  log_level: info
```

## Client Credentials Config Template

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://YOUR_IDP
  client_id: mcp-service-account
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: client_credentials
  scopes:
    - openid
    - "api://downstream/read"

observability:
  enabled: true
  exporter: otlp
  log_format: json
```

## Server Template

```python
# server.py
from fastauthmcp import FastMCP, identity, access_token
import httpx
import os

mcp = FastMCP("cloud-server", config="fastauthmcp.yaml")

@mcp.tool()
def get_data(query: str) -> dict:
    """Fetch data from downstream API using the user's scoped token."""
    token = access_token()
    resp = httpx.get(
        "https://api.downstream.com/v1/data",
        headers={"Authorization": f"Bearer {token}"},
        params={"q": query},
    )
    return resp.json()

if __name__ == "__main__":
    transport = os.environ.get("FASTAUTHMCP_TRANSPORT", "sse")
    host = os.environ.get("FASTAUTHMCP_HOST", "0.0.0.0")
    port = int(os.environ.get("FASTAUTHMCP_PORT", "8080"))
    mcp.run(transport=transport, host=host, port=port)
```

## Deployment

### Docker

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["python", "server.py"]
```

### Kubernetes

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: mcp-server
spec:
  template:
    spec:
      containers:
        - name: mcp
          image: your-registry/mcp-server:latest
          ports:
            - containerPort: 8080
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
            - name: OTEL_ENDPOINT
              value: http://otel-collector:4317
```

### Cloud Run

```bash
gcloud run deploy mcp-server \
  --image your-registry/mcp-server:latest \
  --port 8080 \
  --set-env-vars "FASTAUTHMCP_TRANSPORT=streamable-http,FASTAUTHMCP_PORT=8080" \
  --set-secrets "FASTAUTHMCP_AUTH_CLIENT_SECRET=mcp-client-secret:latest"
```

## Security Checklist

- [ ] TLS termination at load balancer (HTTPS)
- [ ] Client secret stored in secret manager (not env file)
- [ ] Token exchange audience restricted to specific APIs
- [ ] Scopes minimized to required access
- [ ] Circuit breaker configured for IDP resilience
- [ ] Observability enabled for audit trail
- [ ] Rate limiting enabled in production
