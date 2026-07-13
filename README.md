# Ceramic Framework

[![CI](https://github.com/vincenzo/ceramic-fwk/actions/workflows/ci.yml/badge.svg)](https://github.com/vincenzo/ceramic-fwk/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ceramic-fwk.svg)](https://pypi.org/project/ceramic-fwk/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Enterprise capabilities on top of [FastMCP](https://github.com/jlowin/fastmcp) — authentication, authorization, observability, and session management — activated by a single import change.**

---

## What is Ceramic?

Ceramic is a **drop-in replacement** for FastMCP that adds production-grade enterprise features through a middleware pipeline. It wraps FastMCP via composition — your existing tools, prompts, and resources work unchanged.

Key design principles:
- **Zero tool changes** — change one import line, everything else stays the same
- **Configuration-driven** — all features controlled by a single `ceramic.yaml` file
- **Passthrough by default** — without a config file, Ceramic behaves identically to vanilla FastMCP
- **Composable middleware** — authentication, authorization, observability, and sessions are independent layers that activate based on config sections present

## Installation

```bash
pip install ceramic-fwk
```

Optional extras:

```bash
pip install ceramic-fwk[keyring]   # Platform-native token storage (macOS Keychain, etc.)
pip install ceramic-fwk[crypto]    # Encrypted file-based token storage (Linux)
pip install ceramic-fwk[dev]       # Development dependencies (pytest, hypothesis, etc.)
```

## Quick Start

### 1. Replace your import

```python
# Before
from fastmcp import FastMCP

# After — that's it!
from ceramic import FastMCP
```

Without a `ceramic.yaml` config file, this behaves identically to vanilla FastMCP. No authentication, no middleware, no overhead.

### 2. Add a config file (optional)

Create `ceramic.yaml` in your project root to enable features:

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

Each section in `ceramic.yaml` activates the corresponding middleware layer. Omit a section to disable that feature entirely.

### 3. Run

```bash
ceramic run
```

Or directly in Python:

```python
from ceramic import FastMCP

mcp = FastMCP("my-server", config="ceramic.yaml")

@mcp.tool()
def hello(name: str) -> str:
    return f"Hello, {name}!"

if __name__ == "__main__":
    mcp.run()
```

## How Authentication Works

Ceramic supports two authentication modes depending on your deployment:

### Interactive (authorization_code — default)

Uses **OAuth2 + OIDC with PKCE** for user authentication. Best for CLI and local/stdio deployments:

1. **Explicit login via CLI** — run `ceramic login` before starting the server. This opens a browser, completes the OAuth flow, and stores tokens securely using the platform-native credential store.

2. **Automatic on first MCP call** — if no valid token exists when a tool call arrives, the authentication middleware automatically initiates the browser-based OAuth flow. The MCP call blocks until login completes (up to `callback_timeout` seconds), then proceeds normally.

Once authenticated, sessions persist and tokens auto-refresh transparently.

### Machine-to-Machine (client_credentials)

Uses the **OAuth2 client_credentials grant** for service-to-service authentication. Best for remote/headless server deployments (SSE, HTTP) where no browser is available:

- No user interaction required — authenticates using `client_id` + `client_secret`
- Tokens are automatically acquired and refreshed when expired
- Identity is derived from the service account's JWT claims

```yaml
# ceramic.yaml for M2M / remote deployment
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: my-service-account
  client_secret: ${CERAMIC_AUTH_CLIENT_SECRET}
  grant_type: client_credentials
  scopes:
    - openid
    - profile
```

This is the recommended mode when running Ceramic as a remote MCP server (e.g., `ceramic run --transport sse` or `--transport streamable-http`) since the server cannot open a browser for interactive login.

## Public API

All public symbols are accessible from the top-level `ceramic` package:

```python
from ceramic import (
    FastMCP,           # Drop-in replacement for fastmcp.FastMCP
    CeramicFastMCP,   # Same class (FastMCP is an alias)
    require_role,      # Decorator: restrict tool to users with a specific role
    require_group,     # Decorator: restrict tool to users in a specific group
    identity,          # Function: get the current user's IdentityContext
    IdentityContext,   # Dataclass: email, subject, claims, roles, groups
    CeramicTestClient, # Test client for auth flows without a live IDP
)
```

### `FastMCP` / `CeramicFastMCP`

Drop-in replacement for `fastmcp.FastMCP`. All constructor kwargs are forwarded to the underlying FastMCP instance.

```python
mcp = FastMCP("my-server", config="ceramic.yaml")

# Register tools, prompts, and resources exactly as you would with FastMCP
@mcp.tool()
def my_tool(x: int) -> int:
    return x * 2

@mcp.prompt()
def my_prompt() -> str:
    return "Hello from Ceramic"

@mcp.resource("data://items")
def my_resource() -> list:
    return [1, 2, 3]

mcp.run()
```

**Constructor parameters:**
- `name` (str) — Server name (passed to FastMCP)
- `config` (str | Path | None) — Path to `ceramic.yaml`. If None, uses `CERAMIC_CONFIG` env var or `./ceramic.yaml`. If no config found, runs in passthrough mode.
- `**kwargs` — All additional kwargs forwarded to FastMCP

### `require_role(role_name)`

Decorator that restricts tool access to users with the specified role. Multiple decorators stack with AND semantics (all roles required).

```python
@mcp.tool()
@require_role("admin")
def admin_only_tool() -> str:
    return "secret"

@mcp.tool()
@require_role("editor")
@require_role("reviewer")
def needs_both_roles() -> str:
    return "approved"
```

### `require_group(group_name)`

Same as `require_role` but checks group membership instead.

```python
@mcp.tool()
@require_group("ops-team")
def deploy(service: str) -> str:
    return f"Deployed {service}"
```

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

### `IdentityContext`

Frozen (immutable) dataclass with the authenticated user's identity:

| Field | Type | Description |
|-------|------|-------------|
| `email` | `str \| None` | User's email from token claims |
| `subject` | `str \| None` | Subject identifier (sub claim) |
| `claims` | `MappingProxyType[str, Any]` | All JWT claims (read-only) |
| `roles` | `frozenset[str]` | User's roles |
| `groups` | `frozenset[str]` | User's groups |

### `CeramicTestClient`

Test client that bypasses OAuth flows and injects identity directly. Triggers all authorization middleware as if a real request.

```python
from ceramic.testing import CeramicTestClient

async def test_admin_access():
    client = CeramicTestClient(
        app=mcp,
        email="admin@example.com",
        subject="user-123",
        roles=["admin"],
        groups=["ops-team"],
    )
    result = await client.call_tool("admin_only_tool")
    CeramicTestClient.assert_authorized(result)

async def test_unauthorized():
    client = CeramicTestClient(
        app=mcp,
        email="reader@example.com",
        roles=["viewer"],
    )
    result = await client.call_tool("admin_only_tool")
    CeramicTestClient.assert_unauthorized(result)
```

### `MockIdentityProvider`

Generates structurally valid JWTs without network calls (for testing):

```python
from ceramic.testing import MockIdentityProvider

provider = MockIdentityProvider()
token = provider.issue_token({"sub": "user-123", "email": "test@example.com", "roles": ["admin"]})

# Decode without verification
header, payload = MockIdentityProvider.decode_token(token)
```

## Migration from FastMCP

### Option 1: Import replacement (recommended)

```python
# Change this:
from fastmcp import FastMCP

# To this:
from ceramic import FastMCP
```

Everything else stays the same. Add `ceramic.yaml` when you're ready to enable features.

### Option 2: Middleware-attachment (gradual adoption)

Wrap an existing FastMCP instance without changing its code:

```python
from fastmcp import FastMCP
from ceramic import CeramicFastMCP

# Existing app stays unchanged
app = FastMCP("legacy-server")

@app.tool()
def existing_tool(x: int) -> int:
    return x * 2

# Wrap with Ceramic features
ceramic_app = CeramicFastMCP.enable_ceramic(app, config="ceramic.yaml")
ceramic_app.run()
```

If the config is invalid, `enable_ceramic()` raises `ConfigurationError` and leaves the original FastMCP instance completely unmodified.

## Middleware Pipeline

When config sections are present, Ceramic executes middleware in this fixed order:

```
Request → Observability → Session → Authentication → Authorization → [Plugins] → Tool
```

After-hooks execute in reverse order. Each layer is independent:

| Layer | Activates when | What it does |
|-------|---------------|--------------|
| **Observability** | `observability:` section present | Assigns request ID, starts OTel span, records metrics, emits structured logs |
| **Session** | `sessions:` section present | Restores identity from session, creates sessions on auth, enforces TTL |
| **Authentication** | `auth:` section present | Validates token, auto-refreshes, initiates OAuth if needed |
| **Authorization** | `authorization:` section present | Evaluates `@require_role`/`@require_group` decorators + YAML policies |
| **Plugins** | `plugins:` section present | Custom middleware registered via `app.use()` or config |

### Custom plugins

```python
# my_plugin.py
def create_plugin(config: dict):
    """Factory function called by Ceramic when loading plugins from config."""
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
  grant_type: authorization_code    # authorization_code (interactive) or client_credentials (M2M)
  scopes:                           # OAuth2 scopes to request
    - openid
    - profile
    - email
  callback_port: 9876               # Local port for OAuth callback server (1-65535, authorization_code only)
  callback_timeout: 120             # Seconds to wait for browser callback (1-600, authorization_code only)
  callback_port: 9876               # Local port for OAuth callback server (1-65535, default: 9876)
  token_exchange_timeout: 30        # Seconds for token exchange HTTP call (1-120)

# Authorization (role/group-based access control)
authorization:
  role_claim: realm_access.roles    # JSONPath to roles in the JWT
  group_claim: groups               # JSONPath to groups in the JWT
  policies:                         # YAML-based policies (glob patterns supported)
    - tool: "admin_*"
      require_role: admin
    - tool: "deploy_*"
      require_group: ops-team

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
    - authorization
```

### Environment variable overrides

Any scalar config value can be overridden via environment variables prefixed with `CERAMIC_`:

```bash
export CERAMIC_AUTH_CLIENT_SECRET="my-secret"
export CERAMIC_OBSERVABILITY_LOG_LEVEL="debug"
```

The config file path itself can be set via:

```bash
export CERAMIC_CONFIG="/path/to/ceramic.yaml"
```

## CLI Commands

The `ceramic` CLI is installed automatically with the package.

| Command | Description |
|---------|-------------|
| `ceramic run` | Start the server (loads `ceramic.yaml` from CWD or `CERAMIC_CONFIG`). Options: `--transport` (stdio\|sse\|http\|streamable-http, default: stdio), `--host`, `--port` |
| `ceramic login` | Run OAuth2 PKCE login flow, store tokens |
| `ceramic logout` | Clear stored tokens and invalidate session |
| `ceramic whoami` | Display current user's email, subject, and roles |
| `ceramic doctor` | Diagnostics: check config validity, IDP connectivity, token freshness |
| `ceramic config validate` | Validate `ceramic.yaml` and report errors/warnings |

All commands exit 0 on success, non-zero with stderr message on failure.

```bash
# Start with explicit config path
ceramic run --config /path/to/ceramic.yaml

# Start with a specific transport (default: stdio)
ceramic run --transport sse --host 0.0.0.0 --port 9000

# Available transports: stdio, sse, http, streamable-http
ceramic run --transport streamable-http

# Check everything is configured correctly
ceramic doctor

# Full login → verify → run workflow
ceramic login && ceramic whoami && ceramic run
```

## Exception Hierarchy

All Ceramic exceptions inherit from `CeramicError`:

| Exception | When raised |
|-----------|-------------|
| `ConfigurationError` | Invalid YAML, unknown keys, missing required fields, invalid config path |
| `AuthenticationError` | OAuth flow failure, token exchange error, expired refresh token |
| `AuthorizationError` | User lacks required role or group |
| `ProviderError` | IDP unreachable, discovery endpoint failure, HTTP errors |
| `SessionError` | Session creation/restoration failure |
| `PluginError` | Plugin doesn't conform to protocol, invalid hook names |

## Testing

Ceramic provides first-class testing support without requiring a live identity provider:

```python
from ceramic import FastMCP, require_role, identity
from ceramic.testing import CeramicTestClient

# Your server
mcp = FastMCP("test-server")

@mcp.tool()
@require_role("admin")
def protected_tool() -> str:
    user = identity()
    return f"Hello {user.email}"

# Test
async def test_authorized_user():
    client = CeramicTestClient(app=mcp, email="admin@co.com", roles=["admin"])
    result = await client.call_tool("protected_tool")
    CeramicTestClient.assert_authorized(result)
    assert result == "Hello admin@co.com"

async def test_unauthorized_user():
    client = CeramicTestClient(app=mcp, email="viewer@co.com", roles=["viewer"])
    result = await client.call_tool("protected_tool")
    CeramicTestClient.assert_unauthorized(result)
```

## Examples

| Example | Description |
|---------|-------------|
| [`examples/basic_server.py`](examples/basic_server.py) | Minimal drop-in replacement |
| [`examples/auth_server.py`](examples/auth_server.py) | Roles, groups, and identity access |
| [`examples/migration_example.py`](examples/migration_example.py) | Middleware-attachment for gradual adoption |
| [`examples/testing_example.py`](examples/testing_example.py) | Test auth flows without a live IDP |
| [`examples/zitadel/`](examples/zitadel/) | Full working example with Zitadel as IDP |
| [`examples/zitadel/demo.py`](examples/zitadel/demo.py) | Chat UI demo with AI tool calling through the full Ceramic pipeline |
| [`examples/zitadel/live_client.py`](examples/zitadel/live_client.py) | Interactive MCP client over SSE (real OAuth2 flow) |

The **Zitadel example** is a complete project management API with role-based access control (viewer/editor/admin), audit logging, and tests — ready to run against the Ceramic OSS Zitadel instance or your own.

## Development

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Setup

```bash
git clone https://github.com/vincenzo/ceramic-fwk.git
cd ceramic-fwk

# Install in development mode
pip install -e ".[dev]"

# Run all tests
pytest

# Run only unit tests
pytest tests/unit/

# Run only property-based tests
pytest tests/properties/
```

### Dev demo (sandbox install + Zitadel example)

Two standalone scripts — no arguments needed:

```bash
# Web UI demo: starts server + chat interface, opens browser automatically
./scripts/demo-web.sh

# Terminal demo: starts server in background, drops into interactive REPL
# First tool call opens browser for real OAuth2 login
./scripts/demo-terminal.sh
```

The original multi-action script is still available for individual commands:

```bash
./scripts/dev-demo.sh login        # Run OAuth2 login flow
./scripts/dev-demo.sh whoami       # Show authenticated identity
./scripts/dev-demo.sh client       # In-process REPL with simulated identity (no server needed)
./scripts/dev-demo.sh clean        # Remove sandbox venv
```

### Project structure

```
ceramic-fwk/
├── ceramic/                  # Main package
│   ├── __init__.py           # Public API (FastMCP, require_role, identity, etc.)
│   ├── server.py             # CeramicFastMCP facade (composition over FastMCP)
│   ├── config.py             # Pydantic config models
│   ├── config_loader.py      # YAML loading + env overrides + hot reload
│   ├── identity.py           # IdentityContext + contextvars propagation
│   ├── authorization.py      # @require_role / @require_group decorators
│   ├── security.py           # LogRedactor, TLSEnforcer
│   ├── exceptions.py         # Exception hierarchy
│   ├── models.py             # TokenSet, Session, OIDCEndpoints, LogEntry
│   ├── observability.py      # TelemetryService (OpenTelemetry)
│   ├── metrics.py            # Prometheus MetricsExporter
│   ├── sessions.py           # SessionStore protocol + InMemorySessionStore
│   ├── middleware/            # Middleware pipeline + built-in middleware
│   │   ├── pipeline.py       # RequestContext, MiddlewarePipeline, protocols
│   │   ├── authentication.py # OAuth token validation + auto-refresh
│   │   ├── authorization.py  # Policy evaluation (decorators + YAML)
│   │   ├── observability.py  # Span creation, metrics recording, structured logs
│   │   ├── session.py        # Session restore/create/invalidate
│   │   └── builtin.py        # Re-exports all built-in middleware
│   ├── auth/                  # OAuth2/OIDC implementation
│   │   ├── oauth.py          # OAuthService (PKCE, discovery, token exchange)
│   │   └── token_storage.py  # Platform-native secure token storage
│   ├── cli/                   # Click CLI commands
│   └── testing/               # CeramicTestClient, MockIdentityProvider
├── tests/
│   ├── unit/                  # Unit tests
│   ├── properties/            # Hypothesis property-based tests
│   └── integration/           # Integration tests
├── examples/                  # Example projects
│   └── zitadel/               # Full Zitadel IDP example (ready to run)
├── scripts/
│   ├── dev-demo.sh            # Sandbox install + run Zitadel example
│   └── release.sh             # Version bump + tag + push
├── docs/                      # Landing page (GitHub Pages)
├── pyproject.toml             # Package metadata + dependencies
├── ceramic.yaml.example       # Annotated example config
└── README.md
```

## Supported Identity Providers

Ceramic works with any standard OIDC-compliant provider:

- **Zitadel** (tested, see `examples/zitadel/`)
- **Google** (OAuth2 + OIDC)
- **Microsoft Entra ID** (formerly Azure AD)
- **Okta**
- **Auth0**
- **Keycloak**
- **Any OIDC-compliant provider** with a `.well-known/openid-configuration` endpoint

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT — see [LICENSE](LICENSE) for details.
