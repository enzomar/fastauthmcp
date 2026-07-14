# Ceramic Framework — Integration & Development Guide

<p align="center">
  <img src="logo.svg" alt="Ceramic logo" width="64" height="64">
</p>

> **Ceramic** is a production-grade Python framework built on top of [FastMCP](https://github.com/jlowin/fastmcp).
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

Ceramic wraps [FastMCP](https://github.com/jlowin/fastmcp) via composition — your existing tools, prompts, and resources work unchanged. The key idea is:

- **Change one import** (`from ceramic import FastMCP` instead of `from fastmcp import FastMCP`)
- **Add a `ceramic.yaml` config** to activate enterprise features
- **Zero changes to your tools** — Ceramic intercepts at the transport layer

Without a config file, Ceramic behaves identically to vanilla FastMCP. There is no overhead, no middleware, and no side effects.

### Why Ceramic?

MCP servers often start as local prototypes. When it's time to deploy them for a team or organization, you need:

- **Authentication** — who is calling this tool?
- **Observability** — what happened, how long did it take, did it fail?
- **Sessions** — can identity persist across tool calls?

Ceramic adds all of these as independent, configuration-driven middleware layers. Disable any feature by simply omitting its section from `ceramic.yaml`.

### Language Support

Ceramic currently supports **Python 3.11+** only. Node.js and Go SDKs are planned for future releases.

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
│          Ceramic Framework              │
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

Ceramic sits between the transport layer and FastMCP. It intercepts every request, runs it through the configured middleware pipeline, and forwards it to FastMCP. After the tool executes, after-hooks run in reverse order.

### Middleware Execution Order

```
Request → Observability → Session → Authentication → [Plugins] → Tool
                                                                   │
Tool Result ← Observability ← Session ← Authentication ← [Plugins] ←─┘
```

Each layer is independent and activates only when its corresponding section is present in `ceramic.yaml`.

---

## Getting Started

### Prerequisites

- Python 3.11 or later
- pip or [uv](https://docs.astral.sh/uv/)

### Installation

```bash
pip install ceramic-fwk
```

Core dependencies installed automatically: FastMCP, httpx, PyJWT, OpenTelemetry, Prometheus client, zeep (SOAP support), and more.

Optional extras:

```bash
pip install ceramic-fwk[keyring]   # Platform-native token storage (macOS Keychain, Windows Credential Manager)
pip install ceramic-fwk[crypto]    # Encrypted file-based token storage (Linux)
pip install ceramic-fwk[dev]       # Development dependencies (pytest, hypothesis, etc.)
```

### Minimal Example

```python
from ceramic import FastMCP

mcp = FastMCP("my-server")

@mcp.tool()
def hello(name: str) -> str:
    return f"Hello, {name}!"

if __name__ == "__main__":
    mcp.run()
```

This is identical to a vanilla FastMCP server. No config means no middleware — Ceramic is invisible.

### Adding Authentication

Create `ceramic.yaml` in your project root:

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
from ceramic import FastMCP, identity

mcp = FastMCP("my-server", config="ceramic.yaml")

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

All configuration lives in a single `ceramic.yaml` file. Every section is optional — omit a section to disable that feature entirely.

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

Any scalar config value can be overridden via environment variables prefixed with `CERAMIC_`:

```bash
export CERAMIC_AUTH_CLIENT_SECRET="my-secret"
export CERAMIC_OBSERVABILITY_LOG_LEVEL="debug"
export CERAMIC_CONFIG="/path/to/ceramic.yaml"
```

---

## Authentication

Ceramic supports two OAuth2/OIDC grant types:

### Interactive Mode (authorization_code + PKCE)

Best for CLI/local deployments where a browser is available.

**Flow:**

1. User runs `ceramic login` (or authentication triggers automatically on first tool call)
2. Browser opens to the identity provider's login page
3. After successful login, the IDP redirects to `http://localhost:{callback_port}/callback`
4. Ceramic exchanges the authorization code for tokens
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

1. Ceramic authenticates using `client_id` + `client_secret` directly with the token endpoint
2. No user interaction required
3. Tokens auto-refresh when expired
4. Identity is derived from the service account's JWT claims

**Configuration:**

```yaml
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: my-service-account
  client_secret: ${CERAMIC_AUTH_CLIENT_SECRET}
  grant_type: client_credentials
  scopes: [openid, profile]
```

### Supported Identity Providers

Ceramic works with any standard OIDC-compliant provider:

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
| macOS | Keychain | `ceramic-fwk[keyring]` |
| Windows | Credential Manager | `ceramic-fwk[keyring]` |
| Linux (keyring) | Secret Service (GNOME) | `ceramic-fwk[keyring]` |
| Linux (no keyring) | Encrypted file | `ceramic-fwk[crypto]` |
| Fallback | Plaintext file | Built-in (with warning) |

---

## Token Propagation to Downstream APIs

A key use case for authenticated MCP servers: your tool needs to call a downstream API (Stripe, GitHub, your internal service) **on behalf of the authenticated user**.

### `access_token()` — Get the raw token

Inside any tool function, call `access_token()` to get the current valid access token:

```python
from ceramic import access_token
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

Many enterprise integrations still use SOAP/XML APIs. Ceramic provides a pre-configured SOAP client that injects the user's token automatically:

```python
from ceramic import authenticated_soap_client

@mcp.tool()
def get_invoice(invoice_id: str) -> dict:
    soap = authenticated_soap_client("https://legacy.internal.com/InvoiceService?wsdl")
    result = soap.service.GetInvoice(invoice_id)
    return {"invoice_id": result.Id, "amount": result.Amount, "status": result.Status}
```

The token is injected as an HTTP `Authorization` header on the transport layer. For services that expect the token inside the SOAP envelope (WS-Security), use the WS-Security variant:

```python
from ceramic.downstream import authenticated_soap_client_wsse

@mcp.tool()
def get_claim(claim_id: str) -> dict:
    soap = authenticated_soap_client_wsse(
        "https://claims.internal.com/ClaimService?wsdl",
        token_type="http://docs.oasis-open.org/wss/oasis-wss-saml-token-profile-1.1#SAMLV2.0",
    )
    result = soap.service.GetClaim(claim_id)
    return {"claim_id": result.Id, "claimant": result.Claimant, "amount": result.Amount}
```

Both clients use `zeep` under the hood (installed automatically with Ceramic). You can also specify `service_name` and `port_name` when the WSDL defines multiple services or ports.

### Token Exchange (RFC 8693) — Headless/Cloud Deployments

When your MCP server runs in the cloud (not locally), the calling platform (Claude, Gemini, etc.) may pass a user token in the request. Ceramic can exchange this upstream token for a downstream-scoped token at the IDP:

```yaml
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: my-mcp-server
  client_secret: ${CERAMIC_AUTH_CLIENT_SECRET}
  grant_type: token_exchange
  upstream_token_header: x-user-token
  token_exchange_audience: https://api.internal.com
  token_exchange_scope: "read:data write:data"
```

**Flow:**

1. Calling platform sends MCP request with user token in metadata
2. Ceramic extracts the upstream token from the configured header/key
3. Ceramic POSTs to the IDP token endpoint with `grant_type=urn:ietf:params:oauth:grant-type:token-exchange`
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

When using `grant_type: token_exchange`, Ceramic supports multiple IDP-specific wire formats via the adapter system. Configure the adapter with `token_exchange_provider`:

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
  client_secret: ${CERAMIC_AUTH_CLIENT_SECRET}
  token_exchange_scope: "https://graph.microsoft.com/.default"
```

### Custom Adapters

Register custom adapters by implementing the `TokenExchangeAdapter` protocol:

```python
from ceramic.auth.adapters import TokenExchangeAdapter, AdapterRegistry

class MyCustomAdapter:
    @property
    def provider_id(self) -> str:
        return "my-provider"

    async def exchange(self, subject_token, config, endpoints, *, audience=None, scope=None):
        # Your custom exchange logic
        ...
```

---

## Resilience

Ceramic protects all outbound IDP HTTP calls with a built-in circuit breaker and production-grade JWKS key management.

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

Ceramic provides full-stack observability out of the box:

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

When `observability` is enabled, Ceramic exposes a Prometheus metrics endpoint:

```
GET http://localhost:9090/metrics
```

Available metrics:

| Metric | Type | Description |
|--------|------|-------------|
| `ceramic_tool_requests_total` | Counter | Total tool calls (labels: tool_name, status) |
| `ceramic_tool_errors_total` | Counter | Failed tool calls (labels: tool_name) |
| `ceramic_tool_duration_milliseconds` | Histogram | Tool call latency in ms (labels: tool_name) |

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

1. After successful authentication, Ceramic creates a session
2. The session ID is associated with the client connection
3. Subsequent tool calls from the same connection reuse the session
4. Sessions expire after the configured TTL
5. Sessions can be explicitly invalidated via `ceramic logout`

---

## Identity Context

Inside any tool function, call `identity()` to access the authenticated user's information:

```python
from ceramic import identity, IdentityContext

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

Ceramic provides first-class testing support without requiring a live identity provider.

### CeramicTestClient

Bypasses OAuth flows and injects identity directly:

```python
from ceramic import FastMCP, identity
from ceramic.testing import CeramicTestClient

mcp = FastMCP("test-server")

@mcp.tool()
def whoami() -> str:
    user = identity()
    return f"Hello {user.email}"

async def test_identity_injected():
    client = CeramicTestClient(
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
from ceramic.testing import MockIdentityProvider

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

The `ceramic` CLI is installed automatically with the package.

| Command | Description |
|---------|-------------|
| `ceramic run` | Start the server |
| `ceramic login` | Run OAuth2 PKCE login flow, store tokens |
| `ceramic logout` | Clear stored tokens and invalidate session |
| `ceramic whoami` | Display current user's email, subject, and roles |
| `ceramic doctor` | Check config validity, IDP connectivity, token freshness |
| `ceramic config validate` | Validate `ceramic.yaml` and report errors/warnings |

### Examples

```bash
# Start with explicit config
ceramic run --config /path/to/ceramic.yaml

# Start with SSE transport for remote clients
ceramic run --transport sse --host 0.0.0.0 --port 9000

# Start with streamable HTTP transport
ceramic run --transport streamable-http --port 8080

# Check config and IDP connectivity
ceramic doctor

# Full workflow
ceramic login && ceramic whoami && ceramic run
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

Ceramic's middleware pipeline is a chain of independent layers. Each layer can:

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

The pipeline is assembled automatically from `ceramic.yaml`. You cannot reorder built-in middleware — the execution order is fixed for security reasons:

1. Observability (always first — so every request gets a trace, even failed auth)
2. Session (restore identity from existing session if available)
3. Authentication (validate/refresh token, or initiate OAuth flow)
4. Custom plugins (your middleware, in declaration order)

---

## Custom Plugins

### Plugin Protocol

A Ceramic plugin is any object with a `name` attribute and a `hooks` dictionary:

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
from ceramic.middleware.pipeline import RequestContext

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

Ceramic supports two primary deployment modes. The key insight: **your tool code stays identical** — only the `ceramic.yaml` config changes between local and cloud.

### Scenario 1: Local MCP via stdio (Claude Desktop, Cursor, VS Code)

You're a developer running an MCP server locally. Claude Desktop or Cursor spawns it as a subprocess. Your tools call downstream APIs that require user-scoped tokens.

**The problem without Ceramic:** You hand-roll OAuth PKCE, build a local callback server, manage token refresh, store credentials securely, and wire the token into every HTTP call. That's days of work before you write a single tool.

**With Ceramic** — run `ceramic login` once, and every tool call is authenticated:

```yaml
# ceramic.yaml
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: my-dev-app
  scopes: [openid, profile, email]
```

```python
from ceramic import FastMCP, access_token
import httpx

mcp = FastMCP("my-tools", config="ceramic.yaml")

@mcp.tool()
def get_orders() -> list:
    token = access_token()  # ← user-scoped, auto-refreshed
    return httpx.get(
        "https://api.internal.com/orders",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
```

```bash
ceramic login     # Browser opens → token stored in macOS Keychain
ceramic run       # stdio transport (default) — spawned by Claude Desktop
```

Authentication uses the interactive `authorization_code + PKCE` flow. Tokens persist across restarts and auto-refresh transparently.

### Scenario 2: Cloud MCP on Claude/Gemini (remote, headless)

Your MCP server runs in the cloud as a remote endpoint. Claude or Gemini calls it over HTTP/SSE. The platform already authenticated the user — but your downstream API needs a token scoped to *your* resource server, not the platform's.

**The problem without Ceramic:** You implement RFC 8693 token exchange yourself — parse the upstream token from request headers, POST to your IDP's token endpoint with the correct grant type and parameters, handle errors, add retry logic, cache tokens, build a circuit breaker for IDP outages. Weeks of security-sensitive code.

**With Ceramic** — the platform passes the user's token, Ceramic exchanges it for a downstream-scoped token:

```yaml
# ceramic.yaml
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: my-cloud-mcp
  client_secret: ${CERAMIC_AUTH_CLIENT_SECRET}
  grant_type: token_exchange
  upstream_token_header: x-user-token
  token_exchange_audience: https://api.internal.com
  token_exchange_scope: "read:data write:data"
  token_exchange_provider: rfc8693   # or google, entra
```

```python
from ceramic import FastMCP, access_token
import httpx

mcp = FastMCP("cloud-tools", config="ceramic.yaml")

@mcp.tool()
def get_orders() -> list:
    token = access_token()  # ← exchanged downstream token, user-scoped
    return httpx.get(
        "https://api.internal.com/orders",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
```

```bash
ceramic run --transport sse --host 0.0.0.0 --port 9000
# or
ceramic run --transport streamable-http --host 0.0.0.0 --port 8080
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
RUN pip install ceramic-fwk
EXPOSE 9000
CMD ["ceramic", "run", "--transport", "sse", "--host", "0.0.0.0", "--port", "9000"]
```

### Behind a Reverse Proxy

Ceramic works behind nginx, Traefik, or any reverse proxy. Set `callback_port` to match your exposed port for OAuth flows (when using interactive mode).

---

## Migration from FastMCP

### Option 1: Import Replacement (Recommended)

```python
# Before
from fastmcp import FastMCP

# After
from ceramic import FastMCP
```

Everything else stays the same. Without `ceramic.yaml`, behavior is identical to vanilla FastMCP.

### Option 2: Middleware Attachment (Gradual Adoption)

Wrap an existing FastMCP instance without modifying its code:

```python
from fastmcp import FastMCP
from ceramic import CeramicFastMCP

# Existing app — unchanged
app = FastMCP("legacy-server")

@app.tool()
def existing_tool(x: int) -> int:
    return x * 2

# Wrap with Ceramic
ceramic_app = CeramicFastMCP.enable_ceramic(app, config="ceramic.yaml")
ceramic_app.run()
```

### Rollback

Remove Ceramic entirely by reverting the import:

```python
from fastmcp import FastMCP  # Back to vanilla
```

Your tools, prompts, and resources are untouched. Ceramic is a layer on top, not a fork.

---

## Troubleshooting

### `ceramic doctor` Output

Run `ceramic doctor` to check:

- ✅ Config file found and valid
- ✅ IDP issuer reachable
- ✅ OIDC discovery endpoint responsive
- ✅ Token present and not expired
- ✅ Token refresh working

### Common Issues

| Problem | Cause | Fix |
|---------|-------|-----|
| "No config found" | `ceramic.yaml` not in CWD | Set `CERAMIC_CONFIG` env var or pass `--config` |
| "IDP unreachable" | Network/firewall issue | Check `issuer` URL, ensure HTTPS is accessible |
| "Token expired" | Session timeout | Run `ceramic login` again |
| "Callback timeout" | Browser didn't complete OAuth | Check `callback_port` isn't blocked, increase `callback_timeout` |
| "Invalid client_id" | Wrong OAuth client configuration | Verify `client_id` in your IDP settings |

### Debug Logging

Enable debug logs for detailed middleware output:

```bash
export CERAMIC_OBSERVABILITY_LOG_LEVEL=debug
ceramic run
```

Or in `ceramic.yaml`:

```yaml
observability:
  log_level: debug
```

---

## Contributing

We just launched and are actively looking for contributors! Here's how you can help:

- **Try it out** — install Ceramic, use it with your MCP server, and report issues
- **Add IDP examples** — tested configurations for additional identity providers
- **Improve docs** — tutorials, guides, and API documentation
- **Write middleware plugins** — rate limiting, caching, request validation
- **Report bugs** — open issues on [GitHub](https://github.com/enzomar/ceramic-fwk/issues)

See [CONTRIBUTING.md](../CONTRIBUTING.md) for development setup and guidelines.

### Development Setup

```bash
git clone https://github.com/enzomar/ceramic-fwk.git
cd ceramic-fwk
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
