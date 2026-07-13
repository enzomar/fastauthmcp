"""Interactive MCP client for the Zitadel example.

Connects to the project-api server using CeramicTestClient (simulated identity)
or the raw FastMCP Client (for tools without auth requirements).

Usage:
    python client.py                                    # Interactive REPL (demo identity)
    python client.py whoami                             # Single tool call
    python client.py get_projects                       # List projects
    python client.py create_project name="New" description="Test"

    # Custom identity
    python client.py --email admin@co.com --roles admin,editor whoami

Environment:
    DEMO_EMAIL    — Email for simulated identity (default: demo@ceramic.dev)
    DEMO_ROLES    — Comma-separated roles (default: viewer,editor,admin)
    DEMO_GROUPS   — Comma-separated groups (default: ops-team)
"""

from __future__ import annotations

import asyncio
import os
import sys

from server import mcp

# Use CeramicTestClient which goes through the middleware pipeline
from ceramic.testing import CeramicTestClient


def get_test_client(
    email: str | None = None,
    roles: list[str] | None = None,
    groups: list[str] | None = None,
) -> CeramicTestClient:
    """Build a CeramicTestClient with the given or default identity."""
    return CeramicTestClient(
        app=mcp,
        email=email or os.environ.get("DEMO_EMAIL", "demo@ceramic.dev"),
        subject="demo-user-001",
        roles=roles or os.environ.get("DEMO_ROLES", "viewer,editor,admin").split(","),
        groups=groups or os.environ.get("DEMO_GROUPS", "ops-team").split(","),
    )


async def call_tool(
    client: CeramicTestClient, tool_name: str, args: dict | None = None
) -> None:
    """Call a tool and print the result."""
    try:
        result = await client.call_tool(tool_name, **(args or {}))

        # Check for authorization denial
        if isinstance(result, dict) and result.get("error") == "authorization_denied":
            print(
                f"\n✗ {tool_name}: Access denied — {result.get('message', 'insufficient permissions')}"
            )
            return

        print(f"\n✓ {tool_name}:")
        if isinstance(result, list):
            for item in result:
                print(f"  {item}")
        elif isinstance(result, dict):
            for k, v in result.items():
                print(f"  {k}: {v}")
        else:
            print(f"  {result}")
    except Exception as exc:
        print(f"\n✗ {tool_name}: {exc}")


async def interactive(client: CeramicTestClient) -> None:
    """Run an interactive REPL for calling tools."""
    print("Ceramic MCP Client — Zitadel Example")
    print("=" * 40)
    print(f"Identity: {client.identity.email}")
    print(f"Roles:    {', '.join(sorted(client.identity.roles))}")
    print(f"Groups:   {', '.join(sorted(client.identity.groups))}")
    print()

    # List available tools
    tools = [
        ("whoami", "(any auth)", "Show current user info"),
        ("get_projects", "viewer", "List all projects"),
        ("get_project_details", "viewer", "Get project (needs project_id=)"),
        ("create_project", "editor", "Create project (needs name=, description=)"),
        (
            "update_project_status",
            "editor",
            "Update status (needs project_id=, status=)",
        ),
        ("delete_project", "admin", "Delete project (needs project_id=)"),
        ("get_audit_log", "admin", "View audit trail (optional limit=)"),
    ]

    print("Available tools:")
    for name, role, desc in tools:
        print(f"  • {name:<25} [{role:<10}] {desc}")

    print("\nSyntax: tool_name key=value key=value ...")
    print("Commands: quit | help | identity\n")

    while True:
        try:
            line = input("ceramic> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not line:
            continue
        if line in ("quit", "exit", "q"):
            print("Bye!")
            break
        if line == "help":
            for name, role, desc in tools:
                print(f"  {name:<25} [{role:<10}] {desc}")
            print()
            continue
        if line == "identity":
            print(f"  Email:   {client.identity.email}")
            print(f"  Subject: {client.identity.subject}")
            print(f"  Roles:   {', '.join(sorted(client.identity.roles))}")
            print(f"  Groups:  {', '.join(sorted(client.identity.groups))}")
            print()
            continue

        # Parse: tool_name key=value key=value
        parts = line.split()
        tool_name = parts[0]
        args: dict = {}
        for part in parts[1:]:
            if "=" in part:
                k, v = part.split("=", 1)
                try:
                    args[k] = int(v)
                except ValueError:
                    args[k] = v

        await call_tool(client, tool_name, args if args else None)
        print()


def parse_cli_args() -> tuple[
    str | None, list[str] | None, list[str] | None, list[str]
]:
    """Parse --email, --roles, --groups flags from sys.argv. Return remaining args."""
    email = None
    roles = None
    groups = None
    remaining = []
    skip_next = False

    for i, arg in enumerate(sys.argv[1:], 1):
        if skip_next:
            skip_next = False
            continue
        if arg == "--email" and i < len(sys.argv) - 1:
            email = sys.argv[i + 1]
            skip_next = True
        elif arg == "--roles" and i < len(sys.argv) - 1:
            roles = sys.argv[i + 1].split(",")
            skip_next = True
        elif arg == "--groups" and i < len(sys.argv) - 1:
            groups = sys.argv[i + 1].split(",")
            skip_next = True
        else:
            remaining.append(arg)

    return email, roles, groups, remaining


async def main() -> None:
    """Entry point."""
    email, roles, groups, remaining = parse_cli_args()
    client = get_test_client(email=email, roles=roles, groups=groups)

    if remaining:
        # Single tool call mode
        tool_name = remaining[0]
        args: dict = {}
        for arg in remaining[1:]:
            if "=" in arg:
                k, v = arg.split("=", 1)
                try:
                    args[k] = int(v)
                except ValueError:
                    args[k] = v
        await call_tool(client, tool_name, args if args else None)
    else:
        # Interactive mode
        await interactive(client)


if __name__ == "__main__":
    asyncio.run(main())
