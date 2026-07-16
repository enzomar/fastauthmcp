# Enterprise Deployment

Full enterprise stack: multi-IDP, RBAC, SOAP backends, audit logging, rate limiting.

## Architecture

```
Multiple Clients (Claude, Cursor, custom agents)
        │
        ▼
FastAuthMCP Gateway
        │
        ├── Multi-IDP routing (corporate + partner IDPs)
        ├── Role-based access control
        ├── Rate limiting
        ├── Audit logging
        ├── Circuit breaker (IDP resilience)
        │
        ├── REST APIs (httpx + Bearer token)
        ├── SOAP/XML APIs (zeep + WS-Security)
        └── Internal gRPC services
```

## Config Template

```yaml
# fastauthmcp.yaml — Enterprise configuration

auth:
  provider: oidc
  issuer: https://login.corporate.com/realms/main
  client_id: mcp-gateway
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: client_credentials
  scopes:
    - openid
    - profile
    - email
    - roles
  circuit_breaker:
    failure_threshold: 5
    cooldown_seconds: 30
  jwks_cache_ttl: 600

observability:
  enabled: true
  exporter: otlp
  otlp_endpoint: http://otel-collector:4317
  log_format: json
  log_level: info
  metrics_port: 9090

sessions:
  enabled: true
  ttl: 3600
```

## Server with RBAC + SOAP + REST

```python
from fastauthmcp import (
    FastMCP, identity, access_token,
    require_roles, require_groups,
    authenticated_soap_client,
)
import httpx

mcp = FastMCP("enterprise-gateway", config="fastauthmcp.yaml")


# ─── Public tools ─────────────────────────────────────────────────────────

@mcp.tool()
def whoami() -> dict:
    """Show the authenticated user's identity and access."""
    user = identity()
    return {
        "email": user.email,
        "subject": user.subject,
        "roles": sorted(user.roles),
        "groups": sorted(user.groups),
    }


# ─── Role-protected tools ─────────────────────────────────────────────────

@mcp.tool()
@require_roles("analyst", "admin")
def query_data(sql: str) -> list:
    """Execute a read-only data query."""
    token = access_token()
    resp = httpx.post(
        "https://data-api.internal.com/v1/query",
        headers={"Authorization": f"Bearer {token}"},
        json={"sql": sql, "read_only": True},
    )
    return resp.json()


@mcp.tool()
@require_roles("admin")
def manage_users(action: str, user_id: str) -> dict:
    """Admin-only: manage user accounts."""
    token = access_token()
    resp = httpx.post(
        f"https://iam-api.internal.com/v1/users/{user_id}/{action}",
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp.json()


# ─── Group-protected tools ────────────────────────────────────────────────

@mcp.tool()
@require_groups("ops-team", "platform-team")
def deploy_service(service: str, version: str) -> dict:
    """Deploy a service to production (ops/platform team only)."""
    token = access_token()
    resp = httpx.post(
        "https://deploy-api.internal.com/v1/deploy",
        headers={"Authorization": f"Bearer {token}"},
        json={"service": service, "version": version},
    )
    return resp.json()


# ─── SOAP backend tools ───────────────────────────────────────────────────

@mcp.tool()
@require_roles("finance", "admin")
def get_invoice(invoice_id: str) -> dict:
    """Retrieve an invoice from the legacy billing system (SOAP)."""
    soap = authenticated_soap_client(
        "https://billing.internal.com/InvoiceService?wsdl"
    )
    result = soap.service.GetInvoice(invoice_id)
    return {
        "id": result.Id,
        "amount": float(result.Amount),
        "currency": result.Currency,
        "status": result.Status,
    }


@mcp.tool()
@require_roles("hr", "admin")
def get_employee(employee_id: str) -> dict:
    """Look up employee info from HR system (SOAP)."""
    soap = authenticated_soap_client(
        "https://hr.internal.com/EmployeeService?wsdl"
    )
    result = soap.service.GetEmployee(employee_id)
    return {
        "name": result.FullName,
        "department": result.Department,
        "title": result.JobTitle,
    }
```

## Multi-IDP Routing

When your organization trusts tokens from multiple IDPs:

```yaml
auth:
  multi_idp:
    enabled: true
    providers:
      - id: corporate
        issuer: https://login.corporate.com/realms/main
        client_id: mcp-gateway-corp
      - id: partner
        issuer: https://auth.partner.io
        client_id: mcp-gateway-partner
      - id: contractor
        issuer: https://contractor-org.okta.com/oauth2/default
        client_id: mcp-gateway-contractor
    routing:
      strategy: issuer_claim
```

## Audit Configuration

```yaml
audit:
  enabled: true
  sink: structured_log
  include_tool_args: false    # Don't log sensitive arguments
  include_identity: true      # Log who did what
```

## Rate Limiting

```yaml
rate_limiting:
  enabled: true
  default_rpm: 60
  per_tool:
    query_data: 30        # Expensive queries
    deploy_service: 5     # Dangerous operations
    manage_users: 10
  per_user: true
```

## Monitoring

### Prometheus metrics

```
fastauthmcp_tool_requests_total{tool_name="query_data", status="success"} 142
fastauthmcp_tool_requests_total{tool_name="deploy_service", status="denied"} 3
fastauthmcp_tool_duration_milliseconds_bucket{tool_name="get_invoice", le="500"} 98
```

### Grafana Dashboard

Import the FastAuthMCP Grafana dashboard (coming soon) or build your own from the Prometheus metrics.

### Alert Rules

```yaml
# prometheus-rules.yml
groups:
  - name: fastauthmcp
    rules:
      - alert: HighAuthFailureRate
        expr: rate(fastauthmcp_tool_requests_total{status="denied"}[5m]) > 0.1
        for: 5m
        labels:
          severity: warning
      - alert: IDPCircuitBreakerOpen
        expr: fastauthmcp_circuit_breaker_state == 2
        for: 1m
        labels:
          severity: critical
```
