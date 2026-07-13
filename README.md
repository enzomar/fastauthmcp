# Ceramic Framework

[![CI](https://github.com/vincenzo/ceramic-fwk/actions/workflows/ci.yml/badge.svg)](https://github.com/vincenzo/ceramic-fwk/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/ceramic-fwk.svg)](https://pypi.org/project/ceramic-fwk/)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

**Enterprise capabilities on top of [FastMCP](https://github.com/jlowin/fastmcp) — authentication, authorization, observability, and session management — activated by a single import change.**

---

## Why Ceramic?

FastMCP is great for building MCP servers quickly. But when you need production-grade features like OAuth2 login, role-based access control, structured logging, and session management, you'd normally wire all of that yourself.

Ceramic wraps FastMCP via composition and adds enterprise features through a middleware pipeline — configured via a single YAML file. Your existing tools, prompts, and resources work unchanged.

## Quick Start

### 1. Install

```bash
pip install ceramic-fwk
```

### 2. Replace your import

```python
# Before
from fastmcp import FastMCP

# After — that's it!
from ceramic import FastMCP
```

### 3. (Optional) Add a config file

Create `ceramic.yaml` in your project root:

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

Without a config file, Ceramic behaves identically to vanilla FastMCP.

## Features

| Feature | Description |
|---------|-------------|
| **Drop-in replacement** | Change one import, keep all your tools |
| **OAuth2/OIDC auth** | Automatic PKCE flow with token refresh |
| **Role & group authorization** | `@require_role("admin")` decorators + YAML policies |
| **Identity context** | Access user info via `ceramic.identity()` in any tool |
| **Observability** | OpenTelemetry traces + Prometheus metrics + structured JSON logs |
| **Session management** | Automatic session creation, restoration, and TTL enforcement |
| **Middleware pipeline** | Composable hooks for custom behavior |
| **CLI** | `ceramic run`, `ceramic login`, `ceramic whoami`, `ceramic doctor` |
| **Hot reload** | Update observability and authorization config without restart |
| **Testing utilities** | `CeramicTestClient` for auth flows without a live IDP |

## Usage Examples

### Authorization with decorators

```python
from ceramic import FastMCP, require_role, require_group, identity

mcp = FastMCP("my-server")

@mcp.tool()
@require_role("analyst")
def get_report(report_id: str) -> dict:
    user = identity()
    return {"report": report_id, "requested_by": user.email}

@mcp.tool()
@require_group("ops-team")
def deploy(service: str, version: str) -> str:
    return f"Deployed {service}@{version}"
```

### YAML-based authorization policies

```yaml
authorization:
  role_claim: realm_access.roles
  group_claim: groups
  policies:
    - tool: "admin_*"
      require_role: admin
    - tool: "deploy_*"
      require_group: ops-team
```

### Testing without a live IDP

```python
from ceramic.testing import CeramicTestClient

async def test_admin_tool():
    client = CeramicTestClient(
        app=mcp,
        email="admin@example.com",
        roles=["admin"],
    )
    result = await client.call_tool("get_report", report_id="q4-2024")
    CeramicTestClient.assert_authorized(result)
```

### Middleware-attachment migration

```python
from fastmcp import FastMCP
from ceramic import FastMCP as CeramicFastMCP

# Existing app stays unchanged
app = FastMCP("legacy-server")

@app.tool()
def legacy_tool(x: int) -> int:
    return x * 2

# Wrap with Ceramic features
ceramic_app = CeramicFastMCP.enable_ceramic(app, config="ceramic.yaml")
```

## Examples

| Example | Description |
|---------|-------------|
| [`examples/basic_server.py`](examples/basic_server.py) | Minimal drop-in replacement |
| [`examples/auth_server.py`](examples/auth_server.py) | Roles, groups, and identity access |
| [`examples/migration_example.py`](examples/migration_example.py) | Middleware-attachment for gradual adoption |
| [`examples/testing_example.py`](examples/testing_example.py) | Test auth flows without a live IDP |
| [`examples/zitadel/`](examples/zitadel/) | Full working example with Zitadel as IDP |

The **Zitadel example** is a complete project management API with role-based access control (viewer/editor/admin), audit logging, and tests — ready to run against a real or local Zitadel instance.

## CLI

```bash
ceramic run                  # Start server with ceramic.yaml config
ceramic login                # OAuth2 login flow
ceramic logout               # Clear stored tokens
ceramic whoami               # Show current user info
ceramic doctor               # Health check (IDP, config, tokens)
ceramic config validate      # Validate ceramic.yaml
```

## Development

### Prerequisites

- Python 3.11+
- [uv](https://docs.astral.sh/uv/) (recommended) or pip

### Setup

```bash
# Clone the repo
git clone https://github.com/vincenzo/ceramic-fwk.git
cd ceramic-fwk

# Install in development mode
pip install -e ".[dev]"

# Run tests
pytest

# Run tests with verbose output
pytest -v

# Run only property-based tests
pytest tests/properties/

# Run only unit tests
pytest tests/unit/
```

### Project structure

```
ceramic-fwk/
├── ceramic/                  # Main package
│   ├── __init__.py           # Public API (FastMCP, require_role, etc.)
│   ├── server.py             # CeramicFastMCP facade
│   ├── config.py             # Pydantic config models
│   ├── config_loader.py      # YAML loading + env overrides
│   ├── identity.py           # IdentityContext + contextvars
│   ├── authorization.py      # @require_role / @require_group
│   ├── security.py           # LogRedactor, TLSEnforcer
│   ├── exceptions.py         # Exception hierarchy
│   ├── models.py             # TokenSet, Session, etc.
│   ├── observability.py      # TelemetryService
│   ├── metrics.py            # Prometheus exporter
│   ├── sessions.py           # SessionStore
│   ├── middleware/            # Middleware pipeline + built-in middleware
│   ├── auth/                  # OAuth2/OIDC + token storage
│   ├── cli/                   # Click CLI commands
│   └── testing/               # CeramicTestClient, MockIdentityProvider
├── tests/
│   ├── properties/            # Hypothesis property-based tests
│   ├── unit/                  # Unit tests
│   └── integration/           # Integration tests
├── examples/                  # Example projects
├── docs/                      # Landing page (GitHub Pages)
├── pyproject.toml
├── ceramic.yaml.example       # Example config
└── README.md
```

## Configuration Reference

See [`ceramic.yaml.example`](ceramic.yaml.example) for a fully documented example configuration.

A JSON Schema is available at [`ceramic.schema.json`](ceramic.schema.json) for editor validation. Add this comment to the top of your `ceramic.yaml` for auto-completion in VS Code, IntelliJ, and other editors:

```yaml
# yaml-language-server: $schema=https://raw.githubusercontent.com/vincenzo/ceramic-fwk/main/ceramic.schema.json
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

## License

MIT — see [LICENSE](LICENSE) for details.
