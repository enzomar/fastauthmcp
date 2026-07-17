# FastAuthMCP Framework

<p align="center">
  <img src="docs/logo.svg" alt="FastAuthMCP logo" width="64" height="64">
</p>

[![CI](https://github.com/enzomar/fastauthmcp/actions/workflows/ci.yml/badge.svg)](https://github.com/enzomar/fastauthmcp/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/fastauthmcp.svg)](https://pypi.org/project/fastauthmcp/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: Apache 2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)

**A production-grade Python framework built on top of [FastMCP](https://github.com/jlowin/fastmcp) — adding authentication, observability, and session management with a single import change.**

---

## Quick Navigation

| Your scenario | Guide |
|---|---|
| Using **Claude Desktop** (local stdio, browser login) | [Claude Desktop guide](docs/guides/claude-desktop.md) |
| Deploying on **Google Gemini** (cloud, token exchange) | [Google Gemini guide](docs/guides/google-gemini.md) |
| Using **Cursor IDE** | [Cursor guide](docs/guides/cursor-ide.md) |
| Running a **live demo** with Zitadel | [Zitadel example](examples/zitadel/) |
| Configuring your **IdP** (Auth0, Okta, Keycloak, Entra, Zitadel) | [IdP guides](docs/guides/) |

---

## What is FastAuthMCP?

FastAuthMCP is a **production-grade Python framework built on top of [FastMCP](https://github.com/jlowin/fastmcp)** that adds enterprise features through a middleware pipeline. It wraps FastMCP via composition — your existing tools, prompts, and resources work unchanged.

> **Note:** FastAuthMCP currently supports Python only. Node.js and Go SDKs are planned for future releases.

Key design principles:
- **Zero tool changes** — change one import line, everything else stays the same
- **Configuration-driven** — all features controlled by a single `fastauthmcp.yaml` file
- **Passthrough by default** — without a config file, FastAuthMCP behaves identically to vanilla FastMCP
- **Composable middleware** — authentication, observability, and sessions are independent layers that activate based on config sections present

## See It In Action

<p align="center">
  <img src="docs/demo.gif" alt="FastAuthMCP demo: login → authenticate → tool call succeeds" width="700">
</p>

> `fastauthmcp login` → browser opens → token stored → tool call authenticated. 30 seconds, zero code changes.

## Why FastAuthMCP? (Comparison)

| | **FastAuthMCP** | **DIY Middleware** | **API Gateway (Kong, etc.)** |
|---|---|---|---|
| **Setup time** | 5 minutes | Days to weeks | Hours + infrastructure |
| **Code changes to tools** | 0 (one import change) | Extensive | 0 (external proxy) |
| **MCP-aware** | ✅ Native | ❌ Must build | ❌ Protocol-unaware |
| **OAuth2/OIDC built-in** | ✅ PKCE, client_credentials, token exchange | Must implement | ✅ Usually available |
| **Token forwarding to downstream APIs** | ✅ `access_token()` | Must build | Depends on gateway |
| **Identity inside tool functions** | ✅ `identity()` | Must propagate manually | ❌ Not possible |
| **Per-tool authorization** | ✅ Decorators + config | Must build | ❌ Route-level only |
| **Rate limiting** | 🚧 Planned | Must build | ✅ Usually available |
| **Audit logging** | 🚧 Planned | Must build | Varies |
| **Multi-IdP support** | 🚧 Planned | Must build | ❌ Single upstream |
| **Schema export** | 🚧 Planned | Must build | ✅ OpenAPI |
| **OpenTelemetry tracing** | ✅ Automatic | Must integrate | Varies |
| **Prometheus metrics** | ✅ Zero config | Must build | ✅ Usually available |
| **Session management** | ✅ Built-in | Must build | ❌ Stateless |
| **Circuit breaker / resilience** | ✅ Built-in for all IDP calls | Must build | ✅ Usually available |
| **Testing support** | ✅ `FastAuthMCPTestClient` | Must mock everything | Must mock gateway |
| **Lock-in** | None (remove import, back to FastMCP) | N/A | Vendor lock-in |
| **Infrastructure required** | None (runs in-process) | None | Separate service |
| **Language** | Python | Any | Any |
| **Cost** | Free (Apache 2.0) | Engineering time | $ to $$$$ |

> 🚧 = **Planned** — feature is on the roadmap but not yet shipped. See [CHANGELOG.md](CHANGELOG.md) for what's currently available.

### When to use what

- **Use FastAuthMCP** when you're building MCP servers with FastMCP in Python and need authentication, observability, or authorization without touching your tools.
- **Roll your own** when you have very custom requirements that don't fit a middleware pipeline, or you're not using FastMCP/Python.
- **Use an API gateway** when your MCP server is one of many services behind a shared ingress layer and you already have gateway infrastructure.

### Real-World Deployment Scenarios

Most MCP servers need to call downstream APIs (Stripe, internal services, SOAP endpoints) **on behalf of the authenticated user** — not with a shared service account. Here's how FastAuthMCP handles the two most common deployment patterns:

#### Scenario 1: Local MCP via stdio (Claude Desktop, Cursor, etc.)

You're a developer running an MCP server locally. Claude Desktop or Cursor spawns it as a subprocess. Your tools call downstream APIs that require user-scoped tokens.

**Without FastAuthMCP:** You hand-roll OAuth PKCE, build a local callback server, manage token refresh, store credentials securely, and wire the token into every HTTP call. That's days of work before you write a single tool.

**With FastAuthMCP:**

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

Run `fastauthmcp login` once → browser opens → token stored in macOS Keychain → every tool call is authenticated. 30 seconds to set up.

#### Scenario 2: Cloud MCP on Claude/Gemini (remote, headless)

Your MCP server runs in the cloud as a remote endpoint. Claude or Gemini calls it over HTTP. The platform already authenticated the user — but your downstream API needs a token scoped to *your* resource server, not the platform's.

**Without FastAuthMCP:** You implement RFC 8693 token exchange yourself — parse the upstream token from request headers, POST to your IDP's token endpoint with the correct grant type and parameters, handle errors, add retry logic, cache tokens, build a circuit breaker for IDP outages. Weeks of security-sensitive code.

**With FastAuthMCP:**

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
  token_exchange_provider: rfc8693  # or google, entra
```

```python
from fastauthmcp import FastMCP, access_token

mcp = FastMCP("cloud-tools", config="fastauthmcp.yaml")

@mcp.tool()
def get_orders() -> list:
    token = access_token()  # ← exchanged downstream token, user-scoped
    return httpx.get(
        "https://api.internal.com/orders",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
```

The platform passes the user's token → FastAuthMCP exchanges it at the IDP → your tool gets a downstream-scoped token. Circuit breaker, retry with backoff, and JWKS validation are all built in. Same tool code works in both scenarios — only the config changes.

#### Summary: One codebase, two deployment modes

| | Local (stdio) | Cloud (HTTP/SSE) |
|---|---|---|
| **Grant type** | `authorization_code` (PKCE) | `token_exchange` (RFC 8693) |
| **User interaction** | Browser login once | None (platform passes token) |
| **Token source** | IDP directly | Exchange upstream → downstream |
| **Tool code changes** | 0 | 0 |
| **Config change** | `grant_type` + exchange settings | Same |

## Installation

```bash
pip install fastauthmcp
```

Core dependencies installed automatically: FastMCP, httpx, PyJWT, Authlib, Pydantic, Click, Tenacity, and PyYAML.

Optional extras:

```bash
pip install fastauthmcp[keyring]        # Platform-native token storage (macOS Keychain, etc.)
pip install fastauthmcp[crypto]         # Encrypted file-based token storage (Linux)
pip install fastauthmcp[observability]  # OpenTelemetry tracing + Prometheus metrics
pip install fastauthmcp[soap]           # SOAP/XML downstream client (zeep)
pip install fastauthmcp[dev]            # Development dependencies (pytest, hypothesis, etc.)
```

## Quick Start

### 1. Replace your import

```python
# Before
from fastmcp import FastMCP

# After — that's it!
from fastauthmcp import FastMCP
```

Without a `fastauthmcp.yaml` config file, this behaves identically to vanilla FastMCP. No authentication, no middleware, no overhead.

### 2. Add a config file (optional)

Create `fastauthmcp.yaml` in your project root to enable features:

```yaml
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: your-app

observability:
  enabled: true
  log_format: json

sessions:
  ttl: 3600
```

Each section in `fastauthmcp.yaml` activates the corresponding middleware layer. Omit a section to disable that feature entirely.

### 3. Run

```bash
fastauthmcp run
```

Or directly in Python:

```python
from fastauthmcp import FastMCP

mcp = FastMCP("my-server", config="fastauthmcp.yaml")

@mcp.tool()
def hello(name: str) -> str:
    return f"Hello, {name}!"

if __name__ == "__main__":
    mcp.run()
```

## How Authentication Works

FastAuthMCP supports three authentication modes, selected by the `grant_type` field in `fastauthmcp.yaml`:

| Mode | `grant_type` | Best for | User interaction |
|---|---|---|---|
| Interactive | `authorization_code` (default) | Local/CLI — Claude Desktop, Cursor | Browser login once |
| Machine-to-Machine | `client_credentials` | Headless servers, service accounts | None |
| Token Exchange | `token_exchange` | Cloud — Gemini, remote MCP hosts | None (platform passes token) |

### 1. Interactive (authorization_code — default)

Uses **OAuth2 + OIDC with PKCE** for user authentication. Best for CLI and local/stdio deployments:

1. **Explicit login via CLI** — run `fastauthmcp login` before starting the server. This opens a browser, completes the OAuth flow, and stores tokens securely using the platform-native credential store.

2. **Automatic on first MCP call** — if no valid token exists when a tool call arrives, the authentication middleware automatically initiates the browser-based OAuth flow. The MCP call blocks until login completes (up to `callback_timeout` seconds), then proceeds normally.

Once authenticated, sessions persist and tokens auto-refresh transparently.

### 2. Machine-to-Machine (client_credentials)

Uses the **OAuth2 client_credentials grant** for service-to-service authentication. Best for remote/headless server deployments (SSE, HTTP) where no browser is available:

- No user interaction required — authenticates using `client_id` + `client_secret`
- Tokens are automatically acquired and refreshed when expired
- Identity is derived from the service account's JWT claims

```yaml
# fastauthmcp.yaml for M2M / remote deployment
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: my-service-account
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: client_credentials
  scopes:
    - openid
    - profile
```

This is the recommended mode when running FastAuthMCP as a remote MCP server (e.g., `fastauthmcp run --transport sse` or `--transport streamable-http`) since the server cannot open a browser for interactive login.

### 3. Token Exchange (headless/cloud with user-scoped tokens)

Uses the **OAuth 2.0 Token Exchange grant** (RFC 8693) for cloud MCP deployments where the calling platform (Claude, Gemini, etc.) passes a user token in the request. FastAuthMCP exchanges it at the IDP for a downstream-scoped token:

- No browser needed — the upstream platform already authenticated the user
- FastAuthMCP exchanges the incoming token for a token scoped to your downstream API
- Tool code calls `access_token()` to get the downstream token
- Each request is user-scoped (not a shared service account)

```yaml
# fastauthmcp.yaml for cloud/headless deployment with token exchange
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: my-mcp-server
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: token_exchange
  upstream_token_header: x-user-token        # Where to find the incoming token
  token_exchange_audience: https://api.internal.com  # Target downstream API
  token_exchange_scope: "read:data write:data"       # Scopes for downstream token
  token_exchange_provider: rfc8693           # rfc8693 (default), google, or entra
```

```python
from fastauthmcp import FastMCP, access_token

mcp = FastMCP("cloud-server", config="fastauthmcp.yaml")

@mcp.tool()
def get_orders() -> list:
    """Call downstream API with the user-scoped exchanged token."""
    token = access_token()  # ← downstream-scoped token from token exchange
    resp = httpx.get(
        "https://api.internal.com/orders",
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp.json()
```

**Built-in Token Exchange Adapters:**

| Provider | Adapter ID | Protocol |
|----------|-----------|----------|
| Standard (default) | `rfc8693` | OAuth 2.0 Token Exchange (RFC 8693) |
| Google Cloud | `google` | Google Security Token Service API |
| Microsoft Entra ID | `entra` | On-Behalf-Of (OBO) flow |

Custom adapters can be registered via the `AdapterRegistry` by implementing the `TokenExchangeAdapter` protocol.

This is the recommended mode for cloud-hosted MCP servers where you need **user-scoped** (not service-account) access to downstream APIs.

## Public API

All public symbols are accessible from the top-level `fastauthmcp` package:

```python
from fastauthmcp import (
    FastMCP,           # Drop-in replacement for fastmcp.FastMCP
    FastAuthMCP,   # Same class (FastMCP is an alias)
    identity,          # Function: get the current user's IdentityContext
    access_token,      # Function: get the raw access token for downstream API calls
    IdentityContext,   # Dataclass: email, subject, claims, roles, groups
    FastAuthMCPTestClient, # Test client for auth flows without a live IDP
    # Authorization decorators
    require_roles,     # Decorator: require any of the listed roles
    require_groups,    # Decorator: require membership in any listed group
    require_scopes,    # Decorator: require all listed scopes
    # Request context propagation
    get_context,       # Get a value from request-scoped context
    set_context,       # Set a value in request-scoped context
    request_context,   # Get the full request context dict
)
```

### `FastMCP` / `FastAuthMCP`

Drop-in replacement for `fastmcp.FastMCP`. All constructor kwargs are forwarded to the underlying FastMCP instance.

```python
mcp = FastMCP("my-server", config="fastauthmcp.yaml")

# Register tools, prompts, and resources exactly as you would with FastMCP
@mcp.tool()
def my_tool(x: int) -> int:
    return x * 2

@mcp.prompt()
def my_prompt() -> str:
    return "Hello from FastAuthMCP"

@mcp.resource("data://items")
def my_resource() -> list:
    return [1, 2, 3]

mcp.run()
```

**Constructor parameters:**
- `name` (str) — Server name (passed to FastMCP)
- `config` (str | Path | None) — Path to `fastauthmcp.yaml`. If None, uses `FASTAUTHMCP_CONFIG` env var or `./fastauthmcp.yaml`. If no config found, runs in passthrough mode.
- `**kwargs` — All additional kwargs forwarded to FastMCP

### `identity()`

Returns the current request's `IdentityContext`. Call this inside any tool function to access the authenticated user's information.

```python
@mcp.tool()
def whoami() -> dict:
    user = identity()
    return {
        "email": user.email,
        "subject": user.subject,
        "roles": sorted(user.roles),
        "groups": sorted(user.groups),
    }
```

**Raises** `RuntimeError` if called outside an active request context.

### `access_token()`

Returns the current request's raw access token for propagating to downstream APIs. The token is always valid — the middleware auto-refreshes before your tool code runs.

```python
from fastauthmcp import access_token
import httpx

@mcp.tool()
def get_orders() -> list:
    """Fetch orders from downstream API using the user's token."""
    token = access_token()
    resp = httpx.get(
        "https://api.internal.com/v1/orders",
        headers={"Authorization": f"Bearer {token}"},
    )
    return resp.json()
```

**Raises** `RuntimeError` if called outside an active request context or if no token is available.

### Per-Tool Authorization Decorators

Restrict tool access based on user roles, groups, or token scopes:

```python
from fastauthmcp import FastMCP, require_roles, require_groups, require_scopes

mcp = FastMCP("my-server", config="fastauthmcp.yaml")

@mcp.tool()
@require_roles("admin", "editor")  # User needs ANY of these roles
async def admin_tool() -> str:
    return "admin access granted"

@mcp.tool()
@require_groups("ops-team")
async def deploy() -> str:
    return "deploying..."

@mcp.tool()
@require_scopes("read:data", "write:data")  # User needs ALL listed scopes
async def manage_data() -> str:
    return "data managed"
```

- `@require_roles(...)` — OR semantics: user needs any one of the listed roles
- `@require_groups(...)` — OR semantics: user needs membership in any listed group
- `@require_scopes(...)` — AND semantics: token must contain all listed scopes
- Stack multiple decorators for AND semantics across different checks
- Unauthorized requests are rejected before the tool body executes

### Request Context Propagation

Propagate custom metadata (correlation IDs, tenant context) through the middleware pipeline into tool functions:

```python
from fastauthmcp import get_context, set_context

@mcp.tool()
async def my_tool() -> dict:
    # Access context set by middleware or plugins
    tenant = get_context("tenant_id")
    request_id = get_context("request_id")
    return {"tenant": tenant, "request_id": request_id}
```

### `IdentityContext`

Frozen (immutable) dataclass with the authenticated user's identity:

| Field | Type | Description |
|-------|------|-------------|
| `email` | `str \| None` | User's email from token claims |
| `subject` | `str \| None` | Subject identifier (sub claim) |
| `claims` | `MappingProxyType[str, Any]` | All JWT claims (read-only) |
| `roles` | `frozenset[str]` | User's roles |
| `groups` | `frozenset[str]` | User's groups |

### `FastAuthMCPTestClient`

Test client that bypasses OAuth flows and injects identity directly:

```python
from fastauthmcp.testing import FastAuthMCPTestClient

async def test_identity_available():
    client = FastAuthMCPTestClient(
        app=mcp,
        email="admin@example.com",
        subject="user-123",
        roles=["admin"],
        groups=["ops-team"],
    )
    result = await client.call_tool("whoami")
    assert result["email"] == "admin@example.com"
```

### `MockIdentityProvider`

Generates structurally valid JWTs without network calls (for testing):

```python
from fastauthmcp.testing import MockIdentityProvider

provider = MockIdentityProvider()
token = provider.issue_token({"sub": "user-123", "email": "test@example.com"})

# Decode without verification
header, payload = MockIdentityProvider.decode_token(token)
```

## Migration from FastMCP

### Option 1: Import replacement (recommended)

```python
# Change this:
from fastmcp import FastMCP

# To this:
from fastauthmcp import FastMCP
```

Everything else stays the same. Add `fastauthmcp.yaml` when you're ready to enable features.

### Option 2: Middleware-attachment (gradual adoption)

Wrap an existing FastMCP instance without changing its code:

```python
from fastmcp import FastMCP
from fastauthmcp import FastAuthMCP

# Existing app stays unchanged
app = FastMCP("legacy-server")

@app.tool()
def existing_tool(x: int) -> int:
    return x * 2

# Wrap with FastAuthMCP features
fastauthmcp_app = FastAuthMCP.enable_fastauthmcp(app, config="fastauthmcp.yaml")
fastauthmcp_app.run()
```

If the config is invalid, `enable_fastauthmcp()` raises `ConfigurationError` and leaves the original FastMCP instance completely unmodified.

## Resilience

All outbound IDP HTTP calls are protected by a built-in circuit breaker and resilient JWKS key management:

### Circuit Breaker

Prevents cascading failures when the identity provider is temporarily unavailable:

- **CLOSED → OPEN**: After `failure_threshold` (default 5) consecutive failures (5xx or network errors)
- **OPEN → HALF_OPEN**: After `cooldown_seconds` (default 30s) elapse
- **HALF_OPEN → CLOSED**: When a single probe request succeeds
- Only one probe request is allowed in HALF_OPEN state

```yaml
auth:
  # ...
  circuit_breaker:
    failure_threshold: 5
    cooldown_seconds: 30
```

### JWKS Key Management

Production-grade JWKS handling for token signature verification:

- **Request coalescing** — Concurrent requests share a single outbound fetch
- **Exponential backoff** — 1s base, 2× multiplier, 60s cap, 25% jitter, 3 retries
- **Stale-while-revalidate** — Cached keys served while background refresh runs
- **Max staleness guard** — Rejects verification after max staleness without successful refresh
- **Automatic key rotation** — Background refresh detects new keys without downtime

## Middleware Pipeline

When config sections are present, FastAuthMCP executes middleware in this fixed order:

```
Request → Observability → Session → Authentication → [Plugins] → Tool
```

After-hooks execute in reverse order. Each layer is independent:

| Layer | Activates when | What it does |
|-------|---------------|--------------|
| **Observability** | `observability:` section present | Assigns request ID, starts OTel span, records metrics, emits structured logs |
| **Session** | `sessions:` section present | Restores identity from session, creates sessions on auth, enforces TTL |
| **Authentication** | `auth:` section present | Validates token, auto-refreshes, initiates OAuth if needed |
| **Authorization** | `auth:` section present | Evaluates per-tool decorator policies and YAML-defined policies |
| **Rate Limiting** | `rate_limiting:` section present | 🚧 **Planned** — Per-tool and per-user token bucket rate limiting (module exists but not yet wired into config) |
| **Plugins** | `plugins:` section present | Custom middleware registered via `app.use()` or config |

### Custom plugins

```python
# my_plugin.py
def create_plugin(config: dict):
    """Factory function called by FastAuthMCP when loading plugins from config."""
    return MyPlugin(config)

class MyPlugin:
    name = "my-plugin"
    hooks = {
        "before_request": my_before_handler,
        "after_request": my_after_handler,
        "on_exception": my_error_handler,
    }
```

Register via config:

```yaml
plugins:
  - module: my_plugin
    config:
      key: value
```

Or programmatically:

```python
mcp.use(my_plugin_instance)
```

## Configuration Reference

All sections are optional. Omit a section to disable that feature.

```yaml
# Authentication (OAuth2/OIDC)
auth:
  provider: oidc                    # Only "oidc" supported currently
  issuer: https://idp.example.com   # OIDC issuer URL (must be HTTPS in production)
  client_id: your-client-id         # OAuth2 client ID
  client_secret: null               # Optional for authorization_code, required for client_credentials
  grant_type: authorization_code    # authorization_code | client_credentials | token_exchange
  scopes:                           # OAuth2 scopes to request
    - openid
    - profile
    - email
  callback_port: 9876               # Local port for OAuth callback server (1-65535, default: 9876)
  callback_timeout: 120             # Seconds to wait for browser callback (1-600)
  token_exchange_timeout: 30        # Seconds for token exchange HTTP call (1-120)
  # Token exchange settings (for grant_type: token_exchange)
  upstream_token_header: null       # Metadata key with the upstream user token
  token_exchange_audience: null     # Target downstream API audience
  token_exchange_scope: null        # Scopes for the downstream token
  token_exchange_provider: null     # Adapter: rfc8693 (default), google, entra
  # Resilience
  circuit_breaker:                  # Circuit breaker for all IDP HTTP calls
    failure_threshold: 5            # Consecutive failures before opening circuit (1-100)
    cooldown_seconds: 30            # Seconds before allowing a probe request (1-300)
  jwks_cache_ttl: 600              # JWKS key cache TTL in seconds (60-86400)

# Observability (traces, metrics, structured logging)
observability:
  enabled: true
  metrics_path: /metrics            # Prometheus metrics endpoint path
  metrics_port: 9090                # Metrics server port (1-65535)
  exporter: otlp                    # otlp | console | none
  otlp_endpoint: http://localhost:4317
  log_format: json                  # json | text
  log_level: info                   # debug | info | warning | error

# Session management
sessions:
  enabled: true
  ttl: 3600                         # Session TTL in seconds (60-86400)
  backend: memory                   # Only "memory" supported currently

# Plugins (third-party middleware)
plugins:
  - module: my_plugin_module
    config:
      custom_key: custom_value

# Hot reload (live config updates without restart)
hot_reload:
  enabled: true
  watch_interval: 5                 # Seconds between file checks (1-60)
  reloadable_sections:              # Only these sections can be hot-reloaded
    - observability
```

### Environment variable overrides

Any scalar config value can be overridden via environment variables prefixed with `FASTAUTHMCP_`:

```bash
export FASTAUTHMCP_AUTH_CLIENT_SECRET="my-secret"
export FASTAUTHMCP_OBSERVABILITY_LOG_LEVEL="debug"
```

The config file path itself can be set via:

```bash
export FASTAUTHMCP_CONFIG="/path/to/fastauthmcp.yaml"
```

## CLI Commands

The `fastauthmcp` CLI is installed automatically with the package.

| Command | Description |
|---------|-------------|
| `fastauthmcp run` | Start the server (loads `fastauthmcp.yaml` from CWD or `FASTAUTHMCP_CONFIG`). Options: `--transport` (stdio\|sse\|http\|streamable-http, default: stdio), `--host`, `--port` |
| `fastauthmcp login` | Run OAuth2 PKCE login flow, store tokens |
| `fastauthmcp logout` | Clear stored tokens and invalidate session |
| `fastauthmcp whoami` | Display current user's email, subject, and roles |
| `fastauthmcp doctor` | Diagnostics: check config validity, IDP connectivity, token freshness |
| `fastauthmcp config validate` | Validate `fastauthmcp.yaml` and report errors/warnings |

All commands exit 0 on success, non-zero with stderr message on failure.

```bash
# Start with explicit config path
fastauthmcp run --config /path/to/fastauthmcp.yaml

# Start with a specific transport (default: stdio)
fastauthmcp run --transport sse --host 0.0.0.0 --port 9000

# Available transports: stdio, sse, http, streamable-http
fastauthmcp run --transport streamable-http

# Check everything is configured correctly
fastauthmcp doctor

# Full login → verify → run workflow
fastauthmcp login && fastauthmcp whoami && fastauthmcp run
```

## Exception Hierarchy

All FastAuthMCP exceptions inherit from `FastAuthMCPError`:

| Exception | When raised |
|-----------|-------------|
| `ConfigurationError` | Invalid YAML, unknown keys, missing required fields, invalid config path |
| `AuthenticationError` | OAuth flow failure, token exchange error, expired refresh token |
| `ProviderError` | IDP unreachable, discovery endpoint failure, HTTP errors, circuit breaker open |
| `SessionError` | Session creation/restoration failure |
| `PluginError` | Plugin doesn't conform to protocol, invalid hook names |

## Testing

FastAuthMCP provides first-class testing support without requiring a live identity provider:

```python
from fastauthmcp import FastMCP, identity
from fastauthmcp.testing import FastAuthMCPTestClient

# Your server
mcp = FastMCP("test-server")

@mcp.tool()
def whoami() -> str:
    user = identity()
    return f"Hello {user.email}"

# Test
async def test_identity_injected():
    client = FastAuthMCPTestClient(app=mcp, email="admin@co.com", roles=["admin"])
    result = await client.call_tool("whoami")
    assert result == "Hello admin@co.com"
```

## Examples

| Example | Description |
|---------|-------------|
| [`examples/basic_server.py`](examples/basic_server.py) | Minimal drop-in replacement |
| [`examples/auth_server.py`](examples/auth_server.py) | Identity access in tools |
| [`examples/headless_server.py`](examples/headless_server.py) | Token propagation to downstream APIs |
| [`examples/migration_example.py`](examples/migration_example.py) | Middleware-attachment for gradual adoption |
| [`examples/testing_example.py`](examples/testing_example.py) | Test auth flows without a live IDP |
| [`examples/zitadel/`](examples/zitadel/) | Full working example with Zitadel as IDP |
| [`examples/zitadel/petstore_server.py`](examples/zitadel/petstore_server.py) | Pet Store MCP server with authentication |
| [`examples/zitadel/mcp_client.py`](examples/zitadel/mcp_client.py) | E2E demo — emulates LLM tool calls through FastAuthMCP |

The **Zitadel example** includes a Pet Store MCP server with real OAuth2 login, session reuse, and identity propagation — narrated step by step.

## Development

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Setup

```bash
git clone https://github.com/enzomar/fastauthmcp.git
cd fastauthmcp

# Install in development mode
pip install -e ".[dev]"

# Run all tests
pytest

# Run only unit tests
pytest tests/unit/

# Run only property-based tests
pytest tests/properties/
```

### Demo

Run the E2E demo with a real OAuth2 flow:

```bash
# SSE transport (default) — starts Pet Store server + client
./scripts/demo.sh

# stdio transport — client spawns server as subprocess
./scripts/demo.sh stdio

# streamable-http transport
./scripts/demo.sh http
```

Utility commands:

```bash
./scripts/demo.sh login        # Run OAuth2 login flow
./scripts/demo.sh whoami       # Show authenticated identity
./scripts/demo.sh run          # Start Pet Store server (SSE)
./scripts/demo.sh test         # Run example tests
./scripts/demo.sh clean        # Remove sandbox venv
```

### Headless / Token Propagation Demo

Demonstrates `access_token()` and token exchange for downstream API calls:

```bash
# Explain the architecture (token exchange flow diagram)
./scripts/demo-headless.sh explain

# Start the headless MCP server (SSE, token exchange mode)
./scripts/demo-headless.sh server

# Simulate a platform call with a user token
./scripts/demo-headless.sh client
```

### Project structure

```
fastauthmcp/
├── fastauthmcp/                  # Main package
│   ├── __init__.py           # Public API (FastMCP, identity, decorators, etc.)
│   ├── server.py             # FastAuthMCP facade (composition over FastMCP)
│   ├── config.py             # Pydantic config models
│   ├── config_loader.py      # YAML loading + env overrides + hot reload
│   ├── identity.py           # IdentityContext + contextvars propagation
│   ├── authorization.py      # Per-tool authorization decorators (@require_roles, etc.)
│   ├── context.py            # Request-scoped context propagation (get_context/set_context)
│   ├── audit.py              # 🚧 Planned: Structured audit logging for security events
│   ├── credential_mapping.py # 🚧 Planned: Downstream credential mapping + scope-aware token cache
│   ├── rate_limiting.py      # 🚧 Planned: Token bucket rate limiter (per-tool, per-user)
│   ├── secrets.py            # 🚧 Planned: Secret management integration (env, AWS, Vault)
│   ├── multi_idp.py          # 🚧 Planned: Multi-IdP routing (issuer claim, tool mapping, header)
│   ├── graceful_degradation.py # 🚧 Planned: Continue serving during IdP outages
│   ├── schema_export.py      # 🚧 Planned: Export server schema as JSON/Markdown
│   ├── security.py           # LogRedactor, TLSEnforcer
│   ├── exceptions.py         # Exception hierarchy
│   ├── models.py             # TokenSet, Session, OIDCEndpoints, LogEntry
│   ├── observability.py      # TelemetryService (OpenTelemetry)
│   ├── metrics.py            # Prometheus MetricsExporter
│   ├── resilience.py         # CircuitBreaker + ResilientHttpClient
│   ├── sessions.py           # SessionStore protocol + InMemorySessionStore
│   ├── downstream.py         # Authenticated HTTP/SOAP clients for downstream APIs
│   ├── middleware/            # Middleware pipeline + built-in middleware
│   │   ├── pipeline.py       # RequestContext, MiddlewarePipeline, protocols
│   │   ├── authentication.py # OAuth token validation + auto-refresh + JWKS verification
│   │   ├── authorization.py  # Per-tool policy evaluation middleware
│   │   ├── observability.py  # Span creation, metrics recording, structured logs
│   │   ├── session.py        # Session restore/create/invalidate
│   │   └── builtin.py        # Re-exports all built-in middleware
│   ├── auth/                  # OAuth2/OIDC implementation
│   │   ├── oauth.py          # OAuthService (PKCE, discovery, token exchange)
│   │   ├── adapters/         # Token exchange adapters (RFC8693, Google STS, Entra OBO)
│   │   ├── jwks_manager.py   # Resilient JWKS key management (coalescing, stale-while-revalidate)
│   │   └── token_storage.py  # Platform-native secure token storage
│   ├── lab/                   # Security & Interoperability Lab
│   │   ├── providers/        # IDP abstractions (Mock, Zitadel, Keycloak, Auth0, Azure, Okta)
│   │   ├── scenarios/        # Test scenarios (matrix of providers × flows × checks)
│   │   ├── runner/           # Engine, discovery, reporting
│   │   └── docker-compose.yml # Keycloak for integration tests
│   ├── cli/                   # Click CLI commands
│   └── testing/               # FastAuthMCPTestClient, MockIdentityProvider
├── tests/
│   ├── unit/                  # Unit tests
│   ├── properties/            # Hypothesis property-based tests
│   └── integration/           # Integration tests
├── examples/                  # Example projects
│   └── zitadel/               # Full Zitadel IDP example (ready to run)
├── docs/
│   ├── GUIDE.md               # Full integration & development guide
│   └── guides/                # Per-platform and per-IDP integration guides
│       ├── claude-desktop.md  # Claude Desktop + each IDP
│       ├── google-gemini.md   # Gemini + token exchange + Workload Identity
│       ├── cursor-ide.md      # Cursor + SSE + social login
│       ├── custom-agent.md    # Build your own MCP client with auth
│       ├── idp-zitadel.md    # Zitadel setup guide
│       ├── idp-keycloak.md   # Keycloak setup guide
│       ├── idp-auth0.md      # Auth0 setup guide
│       ├── idp-azure.md      # Azure Entra ID setup guide
│       ├── idp-google.md     # Google Cloud IAM setup guide
│       ├── idp-okta.md       # Okta setup guide
│       ├── scenario-local.md # Local development deployment
│       ├── scenario-cloud.md # Cloud/K8s deployment
│       └── scenario-enterprise.md # Enterprise multi-IDP + RBAC
├── scripts/
│   ├── demo.sh                # E2E demo + utility commands
│   └── demo-headless.sh       # Token exchange demo
├── lab.sh                     # Run the compatibility lab
├── Makefile                   # Build, test, release, lab helpers
├── pyproject.toml             # Package metadata + dependencies
└── README.md
```

## Security & Interoperability Lab

FastAuthMCP includes a built-in compatibility lab that validates the framework against every supported provider and flow combination.

```bash
./lab.sh          # Run all 34 scenarios (no Docker needed)
./lab.sh --docker # Include Keycloak integration tests
./lab.sh list     # Show the compatibility matrix
```

```
  ╔══════════════════════════════════════════════════════════════╗
  ║      FastAuthMCP Security & Interoperability Lab            ║
  ╚══════════════════════════════════════════════════════════════╝

  OIDC Providers ───────────────
    ✓ Generic OIDC (Mock)
    ✓ ZITADEL
    ✓ Keycloak
    ✓ Auth0
    ✓ Azure Entra ID
    ✓ Okta

  Authentication ──────────────
    ✓ Auth Code + PKCE → identity propagation (per provider)
    ✓ Client Credentials → service identity (per provider)
    ✓ Token Exchange (RFC 8693) → structural validation

  Authorization ─────────────
    ✓ Admin role → tool allowed
    ✓ Viewer role → tool rejected

  Security ────────────────
    ✓ Expired token → rejected
    ✓ Invalid JWT format → rejected
    ✓ Wrong issuer → rejected
    ✓ Wrong audience → rejected
    ✓ Missing claims → handled

  Result: 34 passed, 0 failed
  Report: reports/index.html
```

Adding a new provider or scenario is just a Python class — no DSL, no YAML test definitions.

### Interactive Lab UI

Chat with an LLM through FastAuthMCP-protected tools in a terminal UI:

```bash
make lab-ui
```

Select a scenario (Zitadel, Keycloak, Auth0, Azure, Okta), configure your LLM (OpenAI, OpenRouter, GitHub Models, Anthropic, Ollama), and watch auth + authorization + identity propagation happen live as tools are called.

## Integration Guides

Step-by-step guides for specific platforms and identity providers:

| Guide | Description |
|-------|-------------|
| **[Claude Desktop](docs/guides/claude-desktop.md)** | Local MCP server with browser login (stdio) |
| **[Google Gemini](docs/guides/google-gemini.md)** | Cloud MCP with token exchange + Workload Identity |
| **[Cursor IDE](docs/guides/cursor-ide.md)** | Development server with SSE transport |
| **[Custom Agent](docs/guides/custom-agent.md)** | Build your own MCP client with auth |
| **[Zitadel](docs/guides/idp-zitadel.md)** | PKCE, Client Credentials, Token Exchange |
| **[Keycloak](docs/guides/idp-keycloak.md)** | PKCE, Client Credentials, RBAC with realm roles |
| **[Auth0](docs/guides/idp-auth0.md)** | PKCE, M2M, custom claims via Actions |
| **[Azure Entra ID](docs/guides/idp-azure.md)** | PKCE, Client Credentials, On-Behalf-Of |
| **[Google Cloud](docs/guides/idp-google.md)** | OAuth2, Service Account, Workload Identity STS |
| **[Okta](docs/guides/idp-okta.md)** | PKCE, Client Credentials, Authorization Servers |
| **[Local Dev](docs/guides/scenario-local.md)** | Developer laptop deployment pattern |
| **[Cloud Deploy](docs/guides/scenario-cloud.md)** | Docker/K8s/Cloud Run headless pattern |
| **[Enterprise](docs/guides/scenario-enterprise.md)** | Multi-IDP, RBAC, SOAP, audit, rate limiting |

Each guide includes complete `fastauthmcp.yaml` configs and platform-specific client configurations.

## Supported Identity Providers

FastAuthMCP works with any standard OIDC-compliant provider:

- **Zitadel** (tested, see `examples/zitadel/`) — native RFC 8693 token exchange
- **Google** (OAuth2 + OIDC) — built-in Google STS adapter for token exchange
- **Microsoft Entra ID** (formerly Azure AD) — built-in On-Behalf-Of adapter
- **Okta**
- **Auth0**
- **Keycloak**
- **Any OIDC-compliant provider** with a `.well-known/openid-configuration` endpoint

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## Support the Project

If FastAuthMCP is useful to you, consider supporting its development:

[![PayPal](https://img.shields.io/badge/Support-PayPal-blue.svg?logo=paypal)](https://www.paypal.com/ncp/payment/DA8FJHJT5GSZY)

## Changelog

See [CHANGELOG.md](CHANGELOG.md) for release history.

## License

Apache 2.0 — see [LICENSE](LICENSE) for details.
