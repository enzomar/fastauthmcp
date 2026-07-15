# Zitadel + FastAuthMCP Example

A working example that demonstrates FastAuthMCP authentication using [Zitadel](https://zitadel.com/) as the identity provider. Includes two MCP servers (Project API and Pet Store) with identity-aware tools, plus an MCP client that emulates LLM tool-calling through the full FastAuthMCP pipeline.

## What's in this directory

| File | Description |
|------|-------------|
| `server.py` | **Project API** — MCP server with project management tools |
| `petstore_server.py` | **Pet Store** — MCP server with CRUD pet operations |
| `mcp_client.py` | **MCP Client** — Textual TUI emulating LLM tool calls through FastAuthMCP |
| `test_server.py` | Unit tests using `FastAuthMCPTestClient` (no live IDP needed) |
| `fastauthmcp.yaml` | FastAuthMCP config pointing to the FastAuthMCP OSS Zitadel instance |

## Quick Start — E2E Demo

The fastest way to see FastAuthMCP in action:

```bash
# From the repo root
./scripts/demo.sh
```

This launches a **Textual TUI** with three panels:

```
┌─────────────────────────┬─────────────────────────┐
│     📖 NARRATOR         │    💬 USER ↔ AI         │
│                         │                         │
│  Step-by-step           │  Simulated LLM          │
│  explanation of         │  conversation with      │
│  what FastAuthMCP is        │  tool calls & results   │
│  doing under the hood   │                         │
├─────────────────────────┴─────────────────────────┤
│              ⚡ MIDDLEWARE PIPELINE                │
│                                                   │
│  Live observability: see each request flow        │
│  through Auth → Session → Tool                    │
└───────────────────────────────────────────────────┘
```

Press **N** to advance through each step. The demo runs simulated "LLM prompts":
1. `whoami` → triggers browser-based OAuth2 login (first call)
2. `list_pets` → session reused, no re-auth
3. `add_pet` → write operation with identity tracking

### Transport options

```bash
./scripts/demo.sh sse          # SSE (default) — starts server + client
./scripts/demo.sh stdio        # stdio — client spawns server as subprocess
./scripts/demo.sh http         # streamable-http — starts server + client
```

### What you'll see

The TUI clearly separates three concerns:
- **Narrator** (left) — explains the "why" of each step in plain language
- **User ↔ AI** (right) — shows the simulated conversation and tool results
- **Pipeline** (bottom) — live trace of each middleware layer firing

This makes it immediately clear that authentication and observability happen transparently — the server code is just a YAML file and `identity()` calls.

## Running the servers manually

```bash
# Pet Store (recommended for the E2E demo)
cd examples/zitadel
python petstore_server.py                                        # stdio
FASTAUTHMCP_TRANSPORT=sse python petstore_server.py                  # SSE on :8000
FASTAUTHMCP_TRANSPORT=streamable-http python petstore_server.py      # HTTP on :8000

# Project API (the original example)
python server.py
FASTAUTHMCP_TRANSPORT=sse python server.py
```

## Running the MCP client manually

```bash
# Against a running SSE server
python mcp_client.py --transport sse

# Against a running streamable-http server
python mcp_client.py --transport streamable-http --url http://localhost:8000/mcp

# Via stdio (spawns server as subprocess, no separate server needed)
python mcp_client.py --transport stdio
```

## Zitadel Setup

### Option A: Use the provided FastAuthMCP OSS instance

The included `fastauthmcp.yaml` is pre-configured to use the FastAuthMCP OSS Zitadel Cloud project. No setup needed — just run the demo.

### Option B: Your own Zitadel instance

1. Sign up at [zitadel.cloud](https://zitadel.cloud) or run Zitadel locally
2. Create a project → add a **Native** application (PKCE, no client secret)
3. Set redirect URI: `http://localhost:9876/callback`
4. Update `fastauthmcp.yaml`:

```yaml
auth:
  provider: oidc
  issuer: https://your-instance.zitadel.cloud
  client_id: "YOUR_CLIENT_ID"
```

### M2M (Machine-to-Machine) — for remote/headless deployments

```yaml
auth:
  provider: oidc
  issuer: https://your-instance.zitadel.cloud
  client_id: "YOUR_SERVICE_ACCOUNT_CLIENT_ID"
  client_secret: ${FASTAUTHMCP_AUTH_CLIENT_SECRET}
  grant_type: client_credentials
  scopes:
    - openid
    - "urn:zitadel:iam:org:project:roles"
```

## Testing without a live IDP

```bash
pytest test_server.py -v
```

Uses `FastAuthMCPTestClient` to inject identity and verify tool behavior without any network calls or browser interaction.

## Pet Store tools

| Tool | Description |
|------|-------------|
| `whoami` | Show current user info |
| `list_pets` | List all pets (optional status filter) |
| `get_pet` | Get full details of a pet |
| `add_pet` | Add a new pet to the store |
| `update_pet_status` | Change pet status (available/adopted) |
| `delete_pet` | Remove a pet permanently |

## Project API tools

| Tool | Description |
|------|-------------|
| `whoami` | Show current user info |
| `get_projects` | List all projects |
| `get_project_details` | Get a specific project |
| `create_project` | Create a new project |
| `update_project_status` | Update project status |
| `delete_project` | Delete a project |
| `get_audit_log` | View the audit trail |
