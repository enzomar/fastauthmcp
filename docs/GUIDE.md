# FastAuthMCP Framework — Integration & Development Guide

<p align="center">
  <img src="logo.svg" alt="FastAuthMCP logo" width="64" height="64">
</p>

> **FastAuthMCP** is a production-grade Python framework built on top of [FastMCP](https://github.com/jlowin/fastmcp).
> It adds authentication, observability, and session management to any MCP server — activated by a single import change.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Getting Started](#getting-started)
4. [Configuration Reference](#configuration-reference)
5. [Authentication](#authentication)
6. [Token Exchange Adapters](#token-exchange-adapters)
7. [Resilience](#resilience)
8. [Observability](#observability)
9. [Session Management](#session-management)
10. [Identity Context](#identity-context)
11. [Testing](#testing)
12. [CLI Reference](#cli-reference)
13. [Middleware Pipeline](#middleware-pipeline)
14. [Custom Plugins](#custom-plugins)
15. [Deployment Patterns](#deployment-patterns)
16. [Migration from FastMCP](#migration-from-fastmcp)
17. [Troubleshooting](#troubleshooting)
18. [Contributing](#contributing)

---

## Overview

FastAuthMCP wraps [FastMCP](https://github.com/jlowin/fastmcp) via composition — your existing tools, prompts, and resources work unchanged. The key idea is:

- **Change one import** (`from fastauthmcp import FastMCP` instead of `from fastmcp import FastMCP`)
- **Add a `fastauthmcp.yaml` config** to activate enterprise features
- **Zero changes to your tools** — FastAuthMCP intercepts at the transport layer

Without a config file, FastAuthMCP behaves identically to vanilla FastMCP. There is no overhead, no middleware, and no side effects.

### Why FastAuthMCP?

MCP servers often start as local prototypes. When it's time to deploy them for a team or organization, you need:

- **Authentication** — who is calling this tool?
- **Observability** — what happened, how long did it take, did it fail?
- **Sessions** — can identity persist across tool calls?

FastAuthMCP adds all of these as independent, configuration-driven middleware layers. Disable any feature by simply omitting its section from `fastauthmcp.yaml`.

### Language Support

FastAuthMCP currently supports **Python 3.11+** only. Node.js and Go SDKs are planned for future releases.

---

## Architecture

```
┌─────────────────────────────────────────┐
│              MCP Client                 │
│  (Claude, Cursor, custom agent, etc.)   │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│          FastAuthMCP Framework              │
│                                         │
│  ┌─────────┐ ┌────────────┐              │
│  │  Auth   │ │Observability│              │
│  └─────────┘ └────────────┘              │
│  ┌──────────┐ ┌─────────┐              │
│  │ Sessions │ │ Plugins │              │
│  └──────────┘ └─────────┘              │
└──────────────────┬──────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────┐
│              FastMCP                    │
│     (your tools, prompts, resources)    │
└─────────────────────────────────────────┘
```

FastAuthMCP sits between the transport layer and FastMCP. It intercepts every request, runs it through the configured middleware pipeline, and forwards it to FastMCP. After the tool executes, after-hooks run in reverse order.

### Middleware Execution Order

```
Request → Observability → Session → Authentication → [Plugins] → Tool
                                                                   │
Tool Result ← Observability ← Session ← Authentication ← [Plugins] ←─┘
```

Each layer is independent and activates only when its corresponding section is present in `fastauthmcp.yaml`.

---

## Getting Started

### Prerequisites

- Python 3.11 or later
- pip or [uv](https://docs.astral.sh/uv/)

### Installation

```bash
pip install fastauthmcp
```

Core dependencies installed automatically: FastMCP, httpx, PyJWT, Authlib, Pydantic, Click, Tenacity, and PyYAML.

Optional extras:

```bash
pip install fastauthmcp[keyring]   # Platform-native token storage (macOS Keychain, Windows Credential Manager)
pip install fastauthmcp[crypto]    # Encrypted file-based token storage (Linux)
pip install fastauthmcp[dev]       # Development dependencies (pytest, hypothesis, etc.)
```

### Minimal Example

```python
from fastauthmcp import FastMCP

mcp = FastMCP("my-server")

@mcp.tool()
def hello(name: str) -> str:
    return f"Hello, {name}!"

if __name__ == "__main__":
    mcp.run()
```

This is identical to a vanilla FastMCP server. No config means no middleware — FastAuthMCP is invisible.

### Adding Authentication

Create `fastauthmcp.yaml` in your project root:

```yaml
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: your-app-client-id
  scopes:
    - openid
    - profile
    - email
```

Update your server to load the config:

```python
from fastauthmcp import FastMCP, identity

mcp = FastMCP("my-server", config="fastauthmcp.yaml")

@mcp.tool()
def whoami() -> dict:
    user = identity()
    return {"email": user.email, "roles": sorted(user.roles)}

if __name__ == "__main__":
    mcp.run()
```

That's it. Every tool call now requires a valid OIDC token.

---

## Configuration Reference

All configuration lives in a single `fastauthmcp.yaml` file. Every section is optional — omit a section to disable that feature entirely.

### Full Example

```yaml
# Authentication (OAuth2/OIDC)
auth:
  provider: oidc
  issuer: https://idp.example.com
  client_id: your-client-id
  client_secret: null                     # Required for client_credentials grant
  grant_type: authorization_code          # authorization_code | client_credentials | token_exchange
  scopes:
    - openid
    - profile
    - email
  callback_port: 9876                     # Local port for OAuth callback (1-65535)
  callback_timeout: 120                   # Seconds to wait for browser callback (1-600)
  token_exchange_timeout: 30              # Seconds for token exchange HTTP call (1-120)
  # Token exchange (RFC 8693)
  upstream_token_header: null             # Metadata key with upstream user token
  token_exchange_audience: null           # Target downstream API audience
  token_exchange_scope: null              # Scopes for the downstream token
  token_exchange_provider: null           # Adapter: rfc8693 (default), google, entra
  # Resilience
  circuit_breaker:
    failure_threshold: 5                  # Consecutive failures before opening (1-100)
    cooldown_seconds: 30                  # Seconds before probe request (1-300)
  jwks_cache_ttl: 600                     # JWKS key cache TTL in seconds (60-86400)

# Observability (traces, metrics, structured logging)
observability:
  enabled: true
  metrics_path: /metrics
  metrics_port: 9090
  exporter: otlp                          # otlp | console | none
  otlp_endpoint: http://localhost:4317
  log_format: json                        # json | text
  log_level: info                         # debug | info | warning | error

# Session management
sessions:
  enabled: true
  ttl: 3600                               # Session TTL in seconds (60-86400)
  backend: memory                         # Only "memory" supported currently

# Custom plugins
plugins:
  - module: my_plugin_module
    config:
      custom_key: custom_value

# Hot reload
hot_reload:
  enabled: true
  watch_interval: 5                       # Seconds between file checks (1-60)
  reloadable_sections:
    - observability
```

### Environment Variable Overrides

Any scalar config value can be overridden via environment variables prefixed with `FASTAUTHMCP_`:

```bash
export FASTAUTHMCP_AUTH_CLIENT_SECRET="my-secret"
export FASTAUTHMCP_OBSERVABILITY_LOG_LEVEL="debug"
export FASTAUTHMCP_CONFIG="/path/to/fastauthmcp.yaml"
```

---

## Authentication

FastAuthMCP supports three OAuth2/OIDC grant types:

### Interactive Mode (authorization_code + PKCE)

Best for CLI/local deployments where a browser is available.

**Flow:**

1. User runs `fastauthmcp login` (or authentication triggers automatically on first tool call)
2. Browser opens to the identity provider's login page
3. After successful login, the IDP redirects to `http://localhost:{callback_port}/callback`
4. FastAuthMCP exchanges the authorization code for tokens
5. Tokens are stored securely using the platform-native credential store
6. Subsequent tool calls use the stored token (auto-refreshing when expired)

**Configuration:**

```yaml
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: your-app
  grant_type: authorization_code       # default
  scopes: [openid, profile, email]
  callback_port: 9876
```

### Machine-to-Machine Mode (client_credentials)

Best for remote/headless server deployments (SSE, HTTP) where no browser is available.

**Flow:**

1. FastAuthMCP authenticates using `client_id` + `client_secret` directly with the token endpoint
2. No user interaction required
3. Tokens auto-refresh when expired
4. Identity is derived from the service account's JWT claims

**Configuration:**

```yaml
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: my-service-account
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: client_credentials
  scopes: [openid, profile]
```

### Supported Identity Providers

FastAuthMCP works with any standard OIDC-compliant provider:

| Provider | Status |
|----------|--------|
| **Zitadel** | Tested (see `examples/zitadel/`) |
| **Google** | Supported |
| **Microsoft Entra ID** | Supported |
| **Okta** | Supported |
| **Auth0** | Supported |
| **Keycloak** | Supported |
| Any OIDC-compliant provider | Supported |

The only requirement is a working `.well-known/openid-configuration` endpoint.

### Token Storage

Tokens are stored securely based on available backends:

| Platform | Backend | Package |
|----------|---------|---------|
| macOS | Keychain | `fastauthmcp[keyring]` |
| Windows | Credential Manager | `fastauthmcp[keyring]` |
| Linux (keyring) | Secret Service (GNOME) | `fastauthmcp[keyring]` |
| Linux (no keyring) | Encrypted file | `fastauthmcp[crypto]` |
| Fallback | Plaintext file | Built-in (with warning) |

---

## Token Propagation to Downstream APIs

A key use case for authenticated MCP servers: your tool needs to call a downstream API (Stripe, GitHub, your internal service) **on behalf of the authenticated user**.

### `access_token()` — Get the raw token

Inside any tool function, call `access_token()` to get the current valid access token:

```python
from fastauthmcp import access_token
import httpx

@mcp.tool()
def get_orders() -> list:
    token = access_token()  # Always valid — auto-refreshed by middleware
    resp = httpx.get(
        "https://api.internal.com/v1/orders",
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp.json()
```

The token is guaranteed to be valid when your tool code runs — the authentication middleware refreshes expired tokens before passing control to your function.

### `authenticated_soap_client()` — Call SOAP/XML services

Many enterprise integrations still use SOAP/XML APIs. FastAuthMCP provides a pre-configured SOAP client that injects the user's token automatically:

```python
from fastauthmcp import authenticated_soap_client

@mcp.tool()
def get_invoice(invoice_id: str) -> dict:
    soap = authenticated_soap_client("https://legacy.internal.com/InvoiceService?wsdl")
    result = soap.service.GetInvoice(invoice_id)
    return {"invoice_id": result.Id, "amount": result.Amount, "status": result.Status}
```

The token is injected as an HTTP `Authorization` header on the transport layer. For services that expect the token inside the SOAP envelope (WS-Security), use the WS-Security variant:

```python
from fastauthmcp.downstream import authenticated_soap_client_wsse

@mcp.tool()
def get_claim(claim_id: str) -> dict:
    soap = authenticated_soap_client_wsse(
        "https://claims.internal.com/ClaimService?wsdl",
        token_type="http://docs.oasis-open.org/wss/oasis-wss-saml-token-profile-1.1#SAMLV2.0",
    )
    result = soap.service.GetClaim(claim_id)
    return {"claim_id": result.Id, "claimant": result.Claimant, "amount": result.Amount}
```

Both clients use `zeep` under the hood (install with `pip install fastauthmcp[soap]`). You can also specify `service_name` and `port_name` when the WSDL defines multiple services or ports.

### Token Exchange (RFC 8693) — Headless/Cloud Deployments

When your MCP server runs in the cloud (not locally), the calling platform (Claude, Gemini, etc.) may pass a user token in the request. FastAuthMCP can exchange this upstream token for a downstream-scoped token at the IDP:

```yaml
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: my-mcp-server
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: token_exchange
  upstream_token_header: x-user-token
  token_exchange_audience: https://api.internal.com
  token_exchange_scope: "read:data write:data"
```

**Flow:**

1. Calling platform sends MCP request with user token in metadata
2. FastAuthMCP extracts the upstream token from the configured header/key
3. FastAuthMCP POSTs to the IDP token endpoint with `grant_type=urn:ietf:params:oauth:grant-type:token-exchange`
4. IDP validates the upstream token, issues a scoped downstream token
5. Tool code calls `access_token()` to get the downstream token

**Supported IDPs:**

| Provider | Token Exchange Support |
|----------|----------------------|
| Zitadel | Native RFC 8693 |
| Keycloak | Built-in |
| Auth0 | Via Actions |
| Okta | Via Authorization Servers |
| Entra ID | On-Behalf-Of (OBO) flow |
| Google IAM | STS API |

### Demo

```bash
# Interactive login + token propagation
./scripts/demo-headless.sh interactive

# Prove token works with IDP userinfo call
./scripts/demo-headless.sh propagate

# Explain token exchange configuration
./scripts/demo-headless.sh exchange
```

---

## Token Exchange Adapters

When using `grant_type: token_exchange`, FastAuthMCP supports multiple IDP-specific wire formats via the adapter system. Configure the adapter with `token_exchange_provider`:

### RFC 8693 (default)

The standard OAuth 2.0 Token Exchange protocol. Compatible with Zitadel, Keycloak, and any RFC 8693-compliant provider.

```yaml
auth:
  grant_type: token_exchange
  token_exchange_provider: rfc8693  # default, can be omitted
```

### Google Cloud STS

Exchanges tokens via Google's Security Token Service. Uses camelCase parameter names and the fixed Google STS endpoint (`sts.googleapis.com/v1/token`).

```yaml
auth:
  grant_type: token_exchange
  token_exchange_provider: google
  token_exchange_audience: "//iam.googleapis.com/projects/PROJECT/locations/global/workloadIdentityPools/POOL/providers/PROVIDER"
```

### Microsoft Entra ID (On-Behalf-Of)

Uses the Entra ID OBO flow with `grant_type=urn:ietf:params:oauth:grant-type:jwt-bearer`. Requires `client_secret`.

```yaml
auth:
  grant_type: token_exchange
  token_exchange_provider: entra
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  token_exchange_scope: "https://graph.microsoft.com/.default"
```

### Custom Adapters

Register custom adapters by implementing the `TokenExchangeAdapter` protocol:

```python
from fastauthmcp.auth.adapters import TokenExchangeAdapter, AdapterRegistry

class MyCustomAdapter:
    @property
    def provider_id(self) -> str:
        return "my-provider"

    async def exchange(self, subject_token, config, endpoints, *, audience=None, scope=None):
        # Your custom exchange logic
        ...
```

---

## Per-Tool Authorization

FastAuthMCP provides decorator-based authorization that enforces access policies before tool execution.

### Decorators

```python
from fastauthmcp import FastMCP, require_roles, require_groups, require_scopes

mcp = FastMCP("my-server", config="fastauthmcp.yaml")

@mcp.tool()
@require_roles("admin", "editor")  # User needs ANY of these roles
async def admin_action() -> str:
    return "admin access granted"

@mcp.tool()
@require_groups("ops-team", "platform")  # User needs ANY of these groups
async def deploy(service: str) -> str:
    return f"deploying {service}"

@mcp.tool()
@require_scopes("read:data", "write:data")  # User needs ALL listed scopes
async def manage_data() -> str:
    return "data managed"
```

### Semantics

- `@require_roles(...)` — OR: user needs any one of the listed roles
- `@require_groups(...)` — OR: user needs membership in any one group
- `@require_scopes(...)` — AND: token must contain all listed scopes
- **Stack decorators** for AND across different check types
- Unauthorized requests return an error response without executing the tool body

### YAML-Defined Policies

You can also define policies in `fastauthmcp.yaml` using glob patterns:

```yaml
authorization:
  policies:
    - tool: "admin_*"
      require_role: "admin"
    - tool: "deploy_*"
      require_group: "ops-team"
    - tool: "data_*"
      require_scopes: "read:data write:data"
```

Both decorator-based and YAML-defined policies are evaluated (AND semantics between them).

---

## Rate Limiting

FastAuthMCP includes a built-in token bucket rate limiter supporting per-tool and per-user limits.

### Configuration

```yaml
rate_limiting:
  enabled: true
  default_rpm: 60           # Requests per minute (default for all tools)
  default_burst: 10         # Burst allowance above steady rate
  per_tool:
    expensive_tool: 5       # Override: only 5 rpm for this tool
    ai_generate: 10         # Override: 10 rpm
  per_user: true            # Apply limits per-user (vs global)
```

When rate-limited, the middleware returns an error response with `retry_after` indicating when the caller can retry.

---

## Audit Logging

FastAuthMCP emits structured audit events for security-relevant operations.

### Event Types

| Event | When |
|-------|------|
| `auth.success` | User successfully authenticated |
| `auth.failure` | Authentication attempt failed |
| `authz.granted` | Authorization policy passed |
| `authz.denied` | Authorization policy rejected |
| `token.exchange` | Token exchange completed |
| `tool.invoked` | Tool successfully called |
| `session.created` | New session established |
| `config.reload` | Configuration hot-reloaded |

### Configuration

```yaml
audit:
  enabled: true
  sink: structured_log     # structured_log | file
  file_path: /var/log/fastauthmcp/audit.jsonl
  include_tool_args: false
  include_identity: true
```

---

## Request Context Propagation

FastAuthMCP provides a request-scoped key-value store accessible throughout the middleware pipeline and tool functions.

```python
from fastauthmcp import get_context, set_context

# In a custom plugin (before_request hook):
async def inject_tenant(ctx, next):
    set_context("tenant_id", ctx.metadata.get("x-tenant-id"))
    set_context("correlation_id", ctx.request_id)
    return await next()

# In tool code:
@mcp.tool()
async def my_tool() -> dict:
    tenant = get_context("tenant_id")
    corr_id = get_context("correlation_id")
    return {"tenant": tenant, "correlation_id": corr_id}
```

Context is automatically initialized at request start and cleared at request end.

---

## Multi-IdP Support

A single FastAuthMCP server can trust tokens from multiple identity providers, routing validation based on the token's issuer, tool name, or a request header.

### Configuration

```yaml
auth:
  multi_idp:
    enabled: true
    providers:
      - id: corporate
        issuer: https://login.corporate.com
        client_id: fastauthmcp-corp
      - id: partner
        issuer: https://auth.partner.io
        client_id: fastauthmcp-partner
    routing:
      strategy: issuer_claim   # issuer_claim | tool_mapping | header
```

### Routing Strategies

| Strategy | How it works |
|----------|-------------|
| `issuer_claim` | Decode token, read `iss` claim, match to provider |
| `tool_mapping` | Map tool name patterns to providers (e.g., `partner_*: partner`) |
| `header` | Use a request header (`x-idp-hint`) to select provider |

---

## Graceful Degradation

When the IdP is unavailable (circuit breaker open), FastAuthMCP can optionally continue serving rather than rejecting all requests.

### Configuration

```yaml
auth:
  graceful_degradation:
    enabled: true
    allow_stale_sessions: true       # Trust existing sessions during outage
    public_tools: ["health", "status"]  # These tools never require auth
    max_stale_age: 600               # Max seconds to trust stale identity
```

### Behavior During Outage

1. Previously-authenticated sessions continue working (up to `max_stale_age`)
2. Tools marked as `public_tools` execute without authentication
3. New authentication attempts return a clear "IdP unavailable" error
4. When the circuit closes (IdP recovers), normal operation resumes automatically

---

## Schema Export

Export your server's tool definitions, authorization requirements, and rate limits as structured documentation.

### CLI

```bash
fastauthmcp schema export --format json > schema.json
fastauthmcp schema export --format markdown > API.md
```

### Programmatic

```python
from fastauthmcp.schema_export import SchemaExporter

exporter = SchemaExporter(mcp)
print(exporter.to_json())
print(exporter.to_markdown())
```

The exported schema includes tool names, descriptions, parameters, required roles/groups/scopes, and rate limit overrides.

---

## Resilience

FastAuthMCP protects all outbound IDP HTTP calls with a built-in circuit breaker and production-grade JWKS key management.

### Circuit Breaker

The circuit breaker prevents cascading failures when the identity provider is temporarily unavailable. All HTTP calls to the IDP (discovery, token requests, JWKS fetches) route through it.

**State Machine:**

```
CLOSED ──(failure_threshold reached)──→ OPEN
   ↑                                       │
   │                               (cooldown_seconds)
   │                                       ↓
   └──(probe succeeds)──── HALF_OPEN ──(probe fails)──→ OPEN
```

- **CLOSED** (normal): All requests pass through. Consecutive failures are counted.
- **OPEN** (protecting): All requests immediately rejected with `ProviderError`. Waits for cooldown.
- **HALF_OPEN** (probing): Allows a single probe request through. Success → CLOSED, failure → OPEN.

Only 5xx HTTP responses and network errors count as failures. 4xx errors (e.g., invalid token) do not trip the circuit.

**Configuration:**

```yaml
auth:
  circuit_breaker:
    failure_threshold: 5    # Open after 5 consecutive failures
    cooldown_seconds: 30    # Wait 30s before probing
```

### JWKS Key Management

Token signature verification uses a resilient JWKS manager that minimizes IDP load and handles outages gracefully:

| Feature | Behavior |
|---------|----------|
| **Request coalescing** | Concurrent verification requests share a single JWKS fetch |
| **Exponential backoff** | 1s base, 2× multiplier, 60s cap, 25% jitter, 3 max retries |
| **Stale-while-revalidate** | Cached keys served immediately; background refresh runs asynchronously |
| **Max staleness guard** | Tokens rejected if keys haven't been refreshed within `max_staleness` (default 1h) |
| **Key rotation** | Background refresh detects new keys automatically |

**Caching behavior:**

```
Cache age < jwks_cache_ttl (default 600s):  → Use cached keys immediately
Cache age < max_staleness (default 3600s):  → Use cached keys + trigger background refresh
Cache age ≥ max_staleness:                  → Reject verification (ProviderError)
No cache (first request):                   → Blocking fetch with retries
```

---

## Observability

FastAuthMCP provides full-stack observability out of the box:

- **Structured logging** — JSON or text format, with request IDs
- **Distributed tracing** — OpenTelemetry spans for every tool call
- **Metrics** — Prometheus-compatible endpoint with request counts, latencies, and error rates

### Configuration

```yaml
observability:
  enabled: true
  exporter: otlp
  otlp_endpoint: http://localhost:4317
  log_format: json
  log_level: info
  metrics_path: /metrics
  metrics_port: 9090
```

### What Gets Captured

For every tool call:

- Request ID (propagated across spans)
- Tool name, arguments (redacted if sensitive)
- User identity (email, subject)
- Latency (start to finish)
- Success/failure status
- Error details (if any)

### Prometheus Metrics

When `observability` is enabled, FastAuthMCP exposes a Prometheus metrics endpoint:

```
GET http://localhost:9090/metrics
```

Available metrics:

| Metric | Type | Description |
|--------|------|-------------|
| `fastauthmcp_tool_requests_total` | Counter | Total tool calls (labels: tool_name, status) |
| `fastauthmcp_tool_errors_total` | Counter | Failed tool calls (labels: tool_name) |
| `fastauthmcp_tool_duration_milliseconds` | Histogram | Tool call latency in ms (labels: tool_name) |

---

## Session Management

Sessions allow identity to persist across multiple tool calls without re-authenticating each time.

### Configuration

```yaml
sessions:
  enabled: true
  ttl: 3600          # 1 hour
  backend: memory
```

### How It Works

1. After successful authentication, FastAuthMCP creates a session
2. The session ID is associated with the client connection
3. Subsequent tool calls from the same connection reuse the session
4. Sessions expire after the configured TTL
5. Sessions can be explicitly invalidated via `fastauthmcp logout`

---

## Identity Context

Inside any tool function, call `identity()` to access the authenticated user's information:

```python
from fastauthmcp import identity, IdentityContext

@mcp.tool()
def my_tool() -> dict:
    user: IdentityContext = identity()
    return {
        "email": user.email,
        "subject": user.subject,
        "roles": sorted(user.roles),
        "groups": sorted(user.groups),
        "claims": dict(user.claims),
    }
```

### IdentityContext Fields

| Field | Type | Description |
|-------|------|-------------|
| `email` | `str \| None` | User's email from token claims |
| `subject` | `str \| None` | Subject identifier (sub claim) |
| `claims` | `MappingProxyType[str, Any]` | All JWT claims (read-only) |
| `roles` | `frozenset[str]` | User's roles |
| `groups` | `frozenset[str]` | User's groups |

---

## Testing

FastAuthMCP provides first-class testing support without requiring a live identity provider.

### FastAuthMCPTestClient

Bypasses OAuth flows and injects identity directly:

```python
from fastauthmcp import FastMCP, identity
from fastauthmcp.testing import FastAuthMCPTestClient

mcp = FastMCP("test-server")

@mcp.tool()
def whoami() -> str:
    user = identity()
    return f"Hello {user.email}"

async def test_identity_injected():
    client = FastAuthMCPTestClient(
        app=mcp,
        email="admin@company.com",
        subject="user-123",
        roles=["admin"],
        groups=["ops-team"],
    )
    result = await client.call_tool("whoami")
    assert result == "Hello admin@company.com"
```

### MockIdentityProvider

Generates structurally valid JWTs without network calls:

```python
from fastauthmcp.testing import MockIdentityProvider

provider = MockIdentityProvider()
token = provider.issue_token({
    "sub": "user-123",
    "email": "test@example.com",
    "roles": ["admin"],
})

# Decode without verification
header, payload = MockIdentityProvider.decode_token(token)
assert payload["email"] == "test@example.com"
```

---

## CLI Reference

The `fastauthmcp` CLI is installed automatically with the package.

| Command | Description |
|---------|-------------|
| `fastauthmcp run` | Start the server |
| `fastauthmcp login` | Run OAuth2 PKCE login flow, store tokens |
| `fastauthmcp logout` | Clear stored tokens and invalidate session |
| `fastauthmcp whoami` | Display current user's email, subject, and roles |
| `fastauthmcp doctor` | Check config validity, IDP connectivity, token freshness |
| `fastauthmcp config validate` | Validate `fastauthmcp.yaml` and report errors/warnings |

### Examples

```bash
# Start with explicit config
fastauthmcp run --config /path/to/fastauthmcp.yaml

# Start with SSE transport for remote clients
fastauthmcp run --transport sse --host 0.0.0.0 --port 9000

# Start with streamable HTTP transport
fastauthmcp run --transport streamable-http --port 8080

# Check config and IDP connectivity
fastauthmcp doctor

# Full workflow
fastauthmcp login && fastauthmcp whoami && fastauthmcp run
```

### Transport Options

| Transport | Use Case |
|-----------|----------|
| `stdio` (default) | Local CLI tools, subprocess spawning |
| `sse` | Remote clients, real-time streaming |
| `streamable-http` | HTTP-based remote access |

---

## Middleware Pipeline

### How It Works

FastAuthMCP's middleware pipeline is a chain of independent layers. Each layer can:

- **Intercept** — block the request (e.g., auth failure)
- **Enrich** — add context (e.g., request ID, identity)
- **Observe** — record telemetry without altering the request

### Built-in Middleware

| Middleware | Config Section | Responsibility |
|-----------|---------------|----------------|
| `ObservabilityMiddleware` | `observability:` | Request ID, spans, metrics, structured logs |
| `SessionMiddleware` | `sessions:` | Restore/create/invalidate sessions |
| `AuthenticationMiddleware` | `auth:` | Token validation, auto-refresh, OAuth initiation |

### Pipeline Configuration

The pipeline is assembled automatically from `fastauthmcp.yaml`. You cannot reorder built-in middleware — the execution order is fixed for security reasons:

1. Observability (always first — so every request gets a trace, even failed auth)
2. Session (restore identity from existing session if available)
3. Authentication (validate/refresh token, or initiate OAuth flow)
4. Custom plugins (your middleware, in declaration order)

---

## Custom Plugins

### Plugin Protocol

A FastAuthMCP plugin is any object with a `name` attribute and a `hooks` dictionary:

```python
class MyPlugin:
    name = "my-plugin"
    hooks = {
        "before_request": my_before_handler,
        "after_request": my_after_handler,
        "on_exception": my_error_handler,
    }
```

### Hook Signatures

```python
from fastauthmcp.middleware.pipeline import RequestContext

async def my_before_handler(ctx: RequestContext) -> None:
    """Called before the tool executes. Can modify context or raise to block."""
    print(f"Tool called: {ctx.tool_name}")

async def my_after_handler(ctx: RequestContext, result: Any) -> Any:
    """Called after the tool executes. Can modify the result."""
    return result

async def my_error_handler(ctx: RequestContext, error: Exception) -> None:
    """Called when the tool raises an exception."""
    print(f"Error in {ctx.tool_name}: {error}")
```

### Registration

**Via config:**

```yaml
plugins:
  - module: my_plugin_module
    config:
      log_level: debug
```

The module must export a `create_plugin(config: dict)` factory function.

**Programmatically:**

```python
mcp.use(my_plugin_instance)
```

---

## Deployment Patterns

FastAuthMCP supports two primary deployment modes. The key insight: **your tool code stays identical** — only the `fastauthmcp.yaml` config changes between local and cloud.

### Scenario 1: Local MCP via stdio (Claude Desktop, Cursor, VS Code)

You're a developer running an MCP server locally. Claude Desktop or Cursor spawns it as a subprocess. Your tools call downstream APIs that require user-scoped tokens.

**The problem without FastAuthMCP:** You hand-roll OAuth PKCE, build a local callback server, manage token refresh, store credentials securely, and wire the token into every HTTP call. That's days of work before you write a single tool.

**With FastAuthMCP** — run `fastauthmcp login` once, and every tool call is authenticated:

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: my-dev-app
  scopes: [openid, profile, email]
```

```python
from fastauthmcp import FastMCP, access_token
import httpx

mcp = FastMCP("my-tools", config="fastauthmcp.yaml")

@mcp.tool()
def get_orders() -> list:
    token = access_token()  # ← user-scoped, auto-refreshed
    return httpx.get(
        "https://api.internal.com/orders",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
```

```bash
fastauthmcp login     # Browser opens → token stored in macOS Keychain
fastauthmcp run       # stdio transport (default) — spawned by Claude Desktop
```

Authentication uses the interactive `authorization_code + PKCE` flow. Tokens persist across restarts and auto-refresh transparently.

### Scenario 2: Cloud MCP on Claude/Gemini (remote, headless)

Your MCP server runs in the cloud as a remote endpoint. Claude or Gemini calls it over HTTP/SSE. The platform already authenticated the user — but your downstream API needs a token scoped to *your* resource server, not the platform's.

**The problem without FastAuthMCP:** You implement RFC 8693 token exchange yourself — parse the upstream token from request headers, POST to your IDP's token endpoint with the correct grant type and parameters, handle errors, add retry logic, cache tokens, build a circuit breaker for IDP outages. Weeks of security-sensitive code.

**With FastAuthMCP** — the platform passes the user's token, FastAuthMCP exchanges it for a downstream-scoped token:

```yaml
# fastauthmcp.yaml
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: my-cloud-mcp
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: token_exchange
  upstream_token_header: x-user-token
  token_exchange_audience: https://api.internal.com
  token_exchange_scope: "read:data write:data"
  token_exchange_provider: rfc8693   # or google, entra
```

```python
from fastauthmcp import FastMCP, access_token
import httpx

mcp = FastMCP("cloud-tools", config="fastauthmcp.yaml")

@mcp.tool()
def get_orders() -> list:
    token = access_token()  # ← exchanged downstream token, user-scoped
    return httpx.get(
        "https://api.internal.com/orders",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
```

```bash
fastauthmcp run --transport sse --host 0.0.0.0 --port 9000
# or
fastauthmcp run --transport streamable-http --host 0.0.0.0 --port 8080
```

The tool code is **identical** to the local scenario. Circuit breaker, exponential backoff, JWKS validation, and token caching are all built in.

### Choosing the right grant type

| Deployment | Grant Type | User Interaction | Best For |
|---|---|---|---|
| Local stdio | `authorization_code` | Browser login once | Claude Desktop, Cursor, dev workflows |
| Cloud headless (user-scoped) | `token_exchange` | None (platform passes token) | Claude/Gemini cloud, user-scoped downstream calls |
| Cloud headless (service account) | `client_credentials` | None | Shared service identity, no per-user scoping |

### Docker

```dockerfile
FROM python:3.11-slim
WORKDIR /app
COPY . .
RUN pip install fastauthmcp
EXPOSE 9000
CMD ["fastauthmcp", "run", "--transport", "sse", "--host", "0.0.0.0", "--port", "9000"]
```

### Behind a Reverse Proxy

FastAuthMCP works behind nginx, Traefik, or any reverse proxy. Set `callback_port` to match your exposed port for OAuth flows (when using interactive mode).

---

## Migration from FastMCP

### Option 1: Import Replacement (Recommended)

```python
# Before
from fastmcp import FastMCP

# After
from fastauthmcp import FastMCP
```

Everything else stays the same. Without `fastauthmcp.yaml`, behavior is identical to vanilla FastMCP.

### Option 2: Middleware Attachment (Gradual Adoption)

Wrap an existing FastMCP instance without modifying its code:

```python
from fastmcp import FastMCP
from fastauthmcp import FastAuthMCP

# Existing app — unchanged
app = FastMCP("legacy-server")

@app.tool()
def existing_tool(x: int) -> int:
    return x * 2

# Wrap with FastAuthMCP
fastauthmcp_app = FastAuthMCP.enable_fastauthmcp(app, config="fastauthmcp.yaml")
fastauthmcp_app.run()
```

### Rollback

Remove FastAuthMCP entirely by reverting the import:

```python
from fastmcp import FastMCP  # Back to vanilla
```

Your tools, prompts, and resources are untouched. FastAuthMCP is a layer on top, not a fork.

---

## Troubleshooting

### `fastauthmcp doctor` Output

Run `fastauthmcp doctor` to check:

- ✅ Config file found and valid
- ✅ IDP issuer reachable
- ✅ OIDC discovery endpoint responsive
- ✅ Token present and not expired
- ✅ Token refresh working

### Common Issues

| Problem | Cause | Fix |
|---------|-------|-----|
| "No config found" | `fastauthmcp.yaml` not in CWD | Set `FASTAUTHMCP_CONFIG` env var or pass `--config` |
| "IDP unreachable" | Network/firewall issue | Check `issuer` URL, ensure HTTPS is accessible |
| "Token expired" | Session timeout | Run `fastauthmcp login` again |
| "Callback timeout" | Browser didn't complete OAuth | Check `callback_port` isn't blocked, increase `callback_timeout` |
| "Invalid client_id" | Wrong OAuth client configuration | Verify `client_id` in your IDP settings |

### Debug Logging

Enable debug logs for detailed middleware output:

```bash
export FASTAUTHMCP_OBSERVABILITY_LOG_LEVEL=debug
fastauthmcp run
```

Or in `fastauthmcp.yaml`:

```yaml
observability:
  log_level: debug
```

---

## Contributing

We just launched and are actively looking for contributors! Here's how you can help:

- **Try it out** — install FastAuthMCP, use it with your MCP server, and report issues
- **Add IDP examples** — tested configurations for additional identity providers
- **Improve docs** — tutorials, guides, and API documentation
- **Write middleware plugins** — rate limiting, caching, request validation
- **Report bugs** — open issues on [GitHub](https://github.com/enzomar/fastauthmcp/issues)

See [CONTRIBUTING.md](../CONTRIBUTING.md) for development setup and guidelines.

### Development Setup

```bash
git clone https://github.com/enzomar/fastauthmcp.git
cd fastauthmcp
pip install -e ".[dev]"
pytest
```

### Running the Demo

```bash
./scripts/demo.sh          # SSE transport (default)
./scripts/demo.sh stdio    # stdio transport
./scripts/demo.sh http     # streamable-http transport
```

---

## License

Apache 2.0 — see [LICENSE](../LICENSE) for details.
