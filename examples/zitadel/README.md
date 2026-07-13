# Zitadel + Ceramic Example

A working example that demonstrates Ceramic authentication using [Zitadel](https://zitadel.com/) as the identity provider. Features a project management API with role-based access control, audit logging, and session management.

## Prerequisites

- Python 3.11+
- A Zitadel instance (cloud or self-hosted)

## Quick Start

This example ships with a ready-to-use `ceramic.yaml` pointing to the **Ceramic OSS** Zitadel Cloud instance:

```yaml
auth:
  provider: oidc
  issuer: https://ceramic-oss-agq8i8.eu1.zitadel.cloud
  client_id: "380842820363183891"
```

You can run it immediately against the hosted instance, or set up your own (see below).

```bash
# Install ceramic-fwk (from PyPI or repo root)
pip install ceramic-fwk
# Or: pip install -e ".[dev]"

# Login (opens browser for OIDC flow)
ceramic login

# Run the server
ceramic run
# Or: python server.py
```

## Zitadel Setup

### Option A: Use the provided Ceramic OSS instance

The included `ceramic.yaml` is pre-configured to use the Ceramic OSS Zitadel Cloud project. No setup needed — just run `ceramic login`.

### Option B: Zitadel Cloud (your own instance)

1. Sign up at [zitadel.cloud](https://zitadel.cloud)
2. Create a new project
3. Add an application:
   - Type: **Native** (for CLI/desktop apps)
   - Auth method: **PKCE** (no client secret needed)
   - Redirect URI: `http://localhost:9876/callback`
4. Go to **Roles** → Add roles: `viewer`, `editor`, `admin`
5. Assign roles to your user via **Authorizations**
6. Update `ceramic.yaml` with your issuer and client ID:

```yaml
auth:
  provider: oidc
  issuer: https://your-instance.zitadel.cloud
  client_id: "YOUR_CLIENT_ID"
```

### Option C: Local Zitadel with Docker

```bash
docker run -d \
  --name zitadel \
  -p 8080:8080 \
  -e ZITADEL_MASTERKEY="MasterkeyNeedsToHave32Characters" \
  -e ZITADEL_FIRSTINSTANCE_ORG_HUMAN_USERNAME="playground@ceramic.local" \
  -e ZITADEL_FIRSTINSTANCE_ORG_HUMAN_PASSWORD="Playground0." \
  ghcr.io/zitadel/zitadel:latest start-from-init \
    --masterkey "MasterkeyNeedsToHave32Characters" \
    --tlsMode disabled
```

Zitadel console available at http://localhost:8080  
Login: `playground@ceramic.local` / `Playground0.`

Then create a project and application as described in Option B, and update `ceramic.yaml`:

```yaml
auth:
  provider: oidc
  issuer: http://localhost:8080
  client_id: "YOUR_LOCAL_CLIENT_ID"
```

> **Note:** When using a local instance without TLS, Ceramic's TLS enforcer must be disabled or the issuer URL will be rejected. For development only.

### Create Roles

In your Zitadel project:

1. Go to **Roles** → Add roles: `viewer`, `editor`, `admin`
2. Assign roles to your user via **Authorizations**
3. Make sure the scope `urn:zitadel:iam:org:project:roles` is included (already set in `ceramic.yaml`) — this tells Zitadel to include role claims in the token

### M2M (Machine-to-Machine) Setup

For remote/headless server deployments where no browser is available (e.g., running as a remote MCP server over SSE or HTTP):

1. In Zitadel, create a new application with type **API** (instead of Native)
2. Set auth method to **Basic** (client_id + client_secret)
3. Copy the client secret
4. Configure `ceramic.yaml` with `grant_type: client_credentials`:

```yaml
auth:
  provider: oidc
  issuer: https://ceramic-oss-agq8i8.eu1.zitadel.cloud
  client_id: "YOUR_SERVICE_ACCOUNT_CLIENT_ID"
  client_secret: ${CERAMIC_AUTH_CLIENT_SECRET}
  grant_type: client_credentials
  scopes:
    - openid
    - "urn:zitadel:iam:org:project:roles"
```

```bash
export CERAMIC_AUTH_CLIENT_SECRET="your-client-secret"
ceramic run --transport sse --host 0.0.0.0 --port 8000
```

The server will authenticate itself with the IDP automatically — no browser interaction needed.

## Configuration

The `ceramic.yaml` in this directory is the live config file used by the server. No copy/rename step needed.

Full configuration:

```yaml
auth:
  provider: oidc
  issuer: https://ceramic-oss-agq8i8.eu1.zitadel.cloud
  client_id: "380842820363183891"
  scopes:
    - openid
    - profile
    - email
    - "urn:zitadel:iam:org:project:roles"
  callback_timeout: 120
  token_exchange_timeout: 30

authorization:
  role_claim: "urn:zitadel:iam:org:project:roles"
  group_claim: "groups"
  policies:
    - tool: "get_*"
      require_role: viewer
    - tool: "create_*"
      require_role: editor
    - tool: "update_*"
      require_role: editor
    - tool: "delete_*"
      require_role: admin
    - tool: "get_audit_log"
      require_role: admin

observability:
  enabled: true
  metrics_path: /metrics
  metrics_port: 9090
  exporter: console
  log_format: json
  log_level: info

sessions:
  enabled: true
  ttl: 3600
```

## What This Example Demonstrates

1. **OIDC Authentication** — Full OAuth2 + PKCE flow against Zitadel
2. **M2M Authentication** — Client credentials flow for headless/remote deployments
3. **Role-Based Authorization** — Tools protected by `@require_role()` decorators and YAML policies
4. **Identity Access** — Tools reading the authenticated user's identity via `ceramic.identity()`
5. **Audit Logging** — Every action is recorded with user, timestamp, and details
6. **Session Management** — Subsequent calls reuse the session without re-authentication

## Tools Available

| Tool | Required Role | Description |
|------|---------------|-------------|
| `whoami` | (any authenticated) | Show current user info |
| `get_projects` | viewer | List all projects |
| `get_project_details` | viewer | Get a specific project |
| `create_project` | editor | Create a new project |
| `update_project_status` | editor | Update project status |
| `delete_project` | admin | Delete a project |
| `get_audit_log` | admin | View the audit trail |

## Live Client (SSE)

The `live_client.py` script connects to a running Ceramic server over SSE transport, triggering the real OAuth2 flow in your browser:

```bash
# Start the server with SSE transport
ceramic run --transport sse

# In another terminal — interactive REPL
python live_client.py

# Or call a single tool directly
python live_client.py whoami
python live_client.py create_project name="New Project" description="A test project"
```

Set `CERAMIC_SERVER_URL` to override the default (`http://localhost:8000/sse`).

## Testing Without Zitadel

Use the included test file to verify authorization logic without a live IDP:

```bash
pytest test_server.py -v
```

This uses `CeramicTestClient` to inject identity and test role-based access control without any network calls.
