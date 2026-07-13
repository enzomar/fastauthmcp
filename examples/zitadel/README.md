# Zitadel + Ceramic Example

A working example that demonstrates Ceramic authentication using [Zitadel](https://zitadel.com/) as the identity provider. Includes a simulated HTTP API that requires authentication to access protected endpoints.

## Prerequisites

- Python 3.11+
- A Zitadel instance (cloud or self-hosted)
- Docker (optional, for running Zitadel locally)

## Zitadel Setup

### Option A: Zitadel Cloud (easiest)

1. Sign up at [zitadel.cloud](https://zitadel.cloud)
2. Create a new project
3. Add an application:
   - Type: **Native** (for CLI/desktop apps) or **Web** (for browser-based)
   - Auth method: **PKCE** (no client secret needed)
   - Redirect URI: `http://localhost:9876/callback`
4. Note down your **Issuer URL** and **Client ID**

### Option B: Local Zitadel with Docker

```bash
# Start Zitadel locally
docker run -d \
  --name zitadel \
  -p 8080:8080 \
  -e ZITADEL_MASTERKEY="MasterkeyNeedsToHave32Characters" \
  -e ZITADEL_FIRSTINSTANCE_ORG_HUMAN_USERNAME="playground@ceramic.local" \
  -e ZITADEL_FIRSTINSTANCE_ORG_HUMAN_PASSWORD="Playground0." \
  ghcr.io/zitadel/zitadel:latest start-from-init --masterkey "MasterkeyNeedsToHave32Characters" --tlsMode disabled

# Zitadel console available at http://localhost:8080
# Login: playground@ceramic.local / Playground0.
```

Then create a project and application as described in Option A, using `http://localhost:8080` as the issuer.

### Create Roles

In your Zitadel project:
1. Go to **Roles** → Add roles: `viewer`, `editor`, `admin`
2. Assign roles to your user via **Authorizations**

## Configuration

Copy the example config and fill in your Zitadel details:

```bash
cp ceramic.yaml.example ceramic.yaml
```

Edit `ceramic.yaml`:

```yaml
auth:
  provider: oidc
  issuer: https://your-instance.zitadel.cloud  # or http://localhost:8080
  client_id: "YOUR_CLIENT_ID_HERE"
  scopes:
    - openid
    - profile
    - email
    - "urn:zitadel:iam:org:project:roles"  # Required for role claims

authorization:
  role_claim: "urn:zitadel:iam:org:project:roles"
  group_claim: "groups"
  policies:
    - tool: "get_*"
      require_role: viewer
    - tool: "create_*"
      require_role: editor
    - tool: "delete_*"
      require_role: admin

observability:
  enabled: true
  log_format: json
  log_level: info

sessions:
  ttl: 3600
```

## Running

```bash
# Install ceramic-fwk
pip install ceramic-fwk

# Or from the repo root:
pip install -e ".[dev]"

# Login first
ceramic login

# Run the example server
ceramic run
# Or: python server.py
```

## What This Example Demonstrates

1. **OIDC Authentication** — Full OAuth2 + PKCE flow against Zitadel
2. **Role-Based Authorization** — Tools protected by `@require_role()` decorators
3. **Identity Access** — Tools reading the authenticated user's identity
4. **Simulated HTTP API** — A fake "project management" API that shows realistic tool patterns
5. **Session Management** — Subsequent calls reuse the session without re-auth

## Tools Available

| Tool | Required Role | Description |
|------|---------------|-------------|
| `get_projects` | viewer | List all projects |
| `get_project_details` | viewer | Get a specific project |
| `create_project` | editor | Create a new project |
| `update_project_status` | editor | Update project status |
| `delete_project` | admin | Delete a project |
| `get_audit_log` | admin | View the audit trail |
| `whoami` | (any authenticated) | Show current user info |

## Testing Without Zitadel

Use the included test file to verify authorization logic without a live IDP:

```bash
pytest test_server.py -v
```
