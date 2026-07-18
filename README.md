# FastAuthMCP

<p align="center">
  <img src="docs/logo.svg" alt="FastAuthMCP logo" width="64" height="64">
</p>

<p align="center">
  <strong>Identity infrastructure for AI agents.</strong>
</p>

<p align="center">
  <a href="https://github.com/enzomar/fastauthmcp/actions/workflows/ci.yml"><img src="https://github.com/enzomar/fastauthmcp/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <a href="https://pypi.org/project/fastauthmcp/"><img src="https://img.shields.io/pypi/v/fastauthmcp.svg" alt="PyPI"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.11+-blue.svg" alt="Python 3.11+"></a>
  <a href="LICENSE"><img src="https://img.shields.io/badge/License-Apache_2.0-blue.svg" alt="License"></a>
</p>

---

When an AI agent calls your MCP tools — who is the human behind the request? What are they allowed to do? How do you forward their credentials to downstream APIs?

FastAuthMCP answers these questions. It's an identity runtime that authenticates humans, propagates their identity into tool functions, and forwards user-scoped tokens to enterprise APIs. One config file. Zero changes to your tools.

---

## The Problem

The [Model Context Protocol](https://modelcontextprotocol.io/) defines how AI agents interact with tools. It says nothing about identity.

Every team building production MCP servers re-invents authentication, authorization, and token propagation from scratch. There is no standard. No shared infrastructure. No reference implementation.

Your MCP server works on your laptop. Then your security team asks:

- *Who is calling these tools?*
- *What are they allowed to do?*
- *Where's the audit trail?*
- *How do downstream APIs get a user-scoped token?*

You start building OAuth. Then token refresh. Then per-user propagation. Then authorization. Weeks pass.

## The Solution

FastAuthMCP sits between MCP clients and your tools:

```
┌─────────────────────────────────────────────┐
│  MCP Client (Claude, Gemini, Cursor, etc.)  │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│              FastAuthMCP                    │
│                                             │
│  Authenticate → Authorize → Propagate      │
│                                             │
│  identity()       @require_roles("admin")   │
│  access_token()   sessions, observability   │
└──────────────────────┬──────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────┐
│  Your Tools → Downstream APIs (Stripe,      │
│  GitHub, SAP, internal services...)         │
└─────────────────────────────────────────────┘
```

- **Authenticates the human** — OAuth2, PKCE, or token exchange
- **Propagates identity** — `identity()` returns who is calling, in every tool
- **Forwards user-scoped tokens** — `access_token()` for downstream API calls
- **Enforces authorization** — `@require_roles("admin")` per tool
- **Works identically** — local (stdio + browser) and cloud (HTTP + token exchange)

## Quick Start

### 1. Install

```bash
pip install fastauthmcp
```

### 2. Change one import

```python
# Before
from fastmcp import FastMCP

# After
from fastauthmcp import FastMCP
```

Without a config file, this behaves identically to vanilla FastMCP. No overhead.

### 3. Add identity

Create `fastauthmcp.yaml`:

```yaml
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: your-app
  scopes: [openid, profile, email]
```

Use identity in your tools:

```python
from fastauthmcp import FastMCP, identity, access_token

mcp = FastMCP("my-server", config="fastauthmcp.yaml")

@mcp.tool()
def whoami() -> dict:
    user = identity()
    return {"email": user.email, "roles": sorted(user.roles)}

@mcp.tool()
def get_orders() -> list:
    token = access_token()  # User-scoped, auto-refreshed
    return httpx.get(
        "https://api.internal.com/orders",
        headers={"Authorization": f"Bearer {token}"},
    ).json()
```

That's it. Every tool call is now authenticated. The token is always valid — auto-refreshed by the middleware before your code runs.

## How It Works

### Local: Browser login (Claude Desktop, Cursor)

```yaml
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: my-app
  grant_type: authorization_code  # default
```

First tool call → browser opens → user logs in → token stored in Keychain → all subsequent calls authenticated. No user interaction after the first login.

### Cloud: Token exchange (Gemini, remote agents)

```yaml
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: cloud-mcp-server
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: token_exchange
  upstream_token_header: x-user-token
  token_exchange_audience: https://api.internal.com
```

The calling platform passes a user token → FastAuthMCP exchanges it at the IDP → your tool gets a downstream-scoped token via `access_token()`. No browser. Per-user scoping.

### Machine-to-Machine (headless services)

```yaml
auth:
  provider: oidc
  issuer: https://your-idp.example.com
  client_id: my-service
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: client_credentials
```

## Identity Primitives

```python
from fastauthmcp import identity, access_token, require_roles

@mcp.tool()
def whoami() -> dict:
    user = identity()          # Who is calling this tool?
    return {"email": user.email, "subject": user.subject}

@mcp.tool()
def call_api() -> dict:
    token = access_token()     # Forward to downstream APIs
    return httpx.get(url, headers={"Authorization": f"Bearer {token}"}).json()

@mcp.tool()
@require_roles("admin")        # Per-tool authorization
def admin_action() -> str:
    return "access granted"
```

## Supported Platforms

### MCP Clients

| Platform | Transport | Guide |
|----------|-----------|-------|
| Claude Desktop | stdio | [Guide](docs/guides/claude-desktop.md) |
| Google Gemini | SSE/HTTP | [Guide](docs/guides/google-gemini.md) |
| Cursor IDE | SSE | [Guide](docs/guides/cursor-ide.md) |
| Custom agents | Any | [Guide](docs/guides/custom-agent.md) |

### Identity Providers

| Provider | Auth Code | Client Credentials | Token Exchange | Guide |
|----------|:---------:|:------------------:|:--------------:|-------|
| Zitadel | ✓ | ✓ | ✓ (RFC 8693) | [Guide](docs/guides/idp-zitadel.md) |
| Keycloak | ✓ | ✓ | ✓ | [Guide](docs/guides/idp-keycloak.md) |
| Auth0 | ✓ | ✓ | via Actions | [Guide](docs/guides/idp-auth0.md) |
| Azure Entra ID | ✓ | ✓ | ✓ (OBO) | [Guide](docs/guides/idp-azure.md) |
| Okta | ✓ | ✓ | ✓ | [Guide](docs/guides/idp-okta.md) |
| Google Cloud | ✓ | ✓ | ✓ (STS) | [Guide](docs/guides/idp-google.md) |
| Any OIDC provider | ✓ | ✓ | ✓ | — |

## Compatibility Lab

FastAuthMCP includes an automated interoperability suite — 34 scenarios validating every provider × flow × security check:

```
  Authentication ──────────────
  ✓ ZITADEL Auth Code + PKCE → identity propagation
  ✓ Keycloak Client Credentials → service identity
  ✓ Auth0, Azure, Okta — same

  Authorization ─────────────
  ✓ Admin role → tool allowed
  ✓ Viewer role → tool rejected

  Security ────────────────
  ✓ Expired token → rejected
  ✓ Wrong issuer → rejected
  ✓ Wrong audience → rejected

  Result: 34 passed, 0 failed (300ms)
```

```bash
./lab.sh          # Run all scenarios
make lab-ui       # Interactive TUI with LLM + MCP tools
```

## Why FastAuthMCP?

| | FastAuthMCP | DIY | API Gateway |
|---|---|---|---|
| **Setup** | 5 minutes | Weeks | Hours + infra |
| **MCP-aware** | ✓ | ✗ | ✗ |
| **Identity in tools** | `identity()` | Manual | Not possible |
| **Token forwarding** | `access_token()` | Build it | Depends |
| **Per-tool auth** | Decorators | Build it | Route-level |
| **Lock-in** | None (remove import) | — | Vendor |
| **Infrastructure** | None (in-process) | None | Separate service |

## Architecture

FastAuthMCP wraps [FastMCP](https://github.com/jlowin/fastmcp) via composition. Your tools, prompts, and resources stay unchanged. Remove FastAuthMCP and your app still works.

```
Request → Observability → Session → Authentication → Authorization → Your Tool
```

Each layer activates only when its section is present in `fastauthmcp.yaml`. Omit a section to disable it entirely.

## Configuration

All configuration lives in `fastauthmcp.yaml`. Every section is optional.

```yaml
auth:
  provider: oidc
  issuer: https://idp.example.com
  client_id: your-client-id
  grant_type: authorization_code
  scopes: [openid, profile, email]
  callback_port: 9876

observability:
  enabled: true
  exporter: otlp
  log_format: json

sessions:
  ttl: 3600
```

Full reference: [docs/GUIDE.md](docs/GUIDE.md)

## CLI

```bash
fastauthmcp login     # Browser login, store token
fastauthmcp whoami    # Show current identity
fastauthmcp doctor    # Check config + IDP connectivity
fastauthmcp run       # Start the server
```

## Testing

Test without a live IDP:

```python
from fastauthmcp.testing import FastAuthMCPTestClient

client = FastAuthMCPTestClient(app=mcp, email="admin@co.com", roles=["admin"])
result = await client.call_tool("whoami")
assert result["email"] == "admin@co.com"
```

## Documentation

| Resource | Description |
|----------|-------------|
| [Full Guide](docs/GUIDE.md) | Complete integration & development reference |
| [Integration Guides](docs/guides/) | Per-platform and per-IDP setup |
| [Examples](examples/) | Working code samples |
| [Compatibility Lab](fastauthmcp/lab/) | Automated interoperability suite |

## Installation Extras

```bash
pip install fastauthmcp                # Core (auth, identity, CLI)
pip install fastauthmcp[observability]  # + OpenTelemetry + Prometheus
pip install fastauthmcp[soap]           # + SOAP/XML downstream support
pip install fastauthmcp[keyring]        # + Platform-native token storage
pip install fastauthmcp[dev]            # + Testing tools
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

```bash
git clone https://github.com/enzomar/fastauthmcp.git
cd fastauthmcp
pip install -e ".[dev]"
pytest                        # 359 tests
python -m fastauthmcp.lab run # 34 compatibility scenarios
make lab-ui                   # Interactive TUI
```

## Support

If FastAuthMCP is useful to you:

[![PayPal](https://img.shields.io/badge/Support-PayPal-blue.svg?logo=paypal)](https://www.paypal.com/ncp/payment/DA8FJHJT5GSZY)

## License

Apache 2.0 — see [LICENSE](LICENSE).
