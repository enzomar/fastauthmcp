"""Live MCP client that connects to a running Ceramic server over SSE.

This client connects to the server via HTTP/SSE transport, triggering the
real OAuth2 authentication flow (browser opens for login). Use this to
demonstrate the full end-to-end Ceramic experience.

Prerequisites:
    - Server must be running: ./scripts/dev-demo.sh run
    - Or: ceramic run --transport sse

Usage:
    python live_client.py                          # Interactive REPL
    python live_client.py whoami                   # Single tool call
    python live_client.py get_projects             # Call a specific tool
    python live_client.py create_project name="New Project" description="Test"

Environment:
    CERAMIC_SERVER_URL  — Server URL (default: http://localhost:8000/sse)
"""

from __future__ import annotations

import asyncio
import os
import sys

from fastmcp import Client


DEFAULT_SERVER_URL = "http://localhost:8000/sse"


async def call_tool(client: Client, tool_name: str, args: dict | None = None) -> None:
    """Call a tool on the remote server and print the result."""
    try:
        result = await client.call_tool(tool_name, **(args or {}))
        print(f"\n✓ {tool_name}:")
        if isinstance(result, list):
            for item in result:
                if hasattr(item, "text"):
                    print(f"  {item.text}")
                else:
                    print(f"  {item}")
        elif isinstance(result, dict):
            for k, v in result.items():
                print(f"  {k}: {v}")
        else:
            print(f"  {result}")
    except Exception as exc:
        print(f"\n✗ {tool_name}: {exc}")


async def list_tools(client: Client) -> list[str]:
    """Fetch and display available tools from the server."""
    tools = await client.list_tools()
    print("\nAvailable tools:")
    for tool in tools:
        desc = tool.description or ""
        # Truncate long descriptions
        if len(desc) > 60:
            desc = desc[:57] + "..."
        print(f"  • {tool.name:<28} {desc}")
    print()
    return [t.name for t in tools]


async def interactive(client: Client) -> None:
    """Run an interactive REPL against the live server."""
    print("Ceramic Live Client — connected via SSE")
    print("=" * 45)
    print(f"Server: {os.environ.get('CERAMIC_SERVER_URL', DEFAULT_SERVER_URL)}")
    print()

    tool_names = await list_tools(client)

    print("Syntax: tool_name key=value key=value ...")
    print("Commands: quit | help | tools\n")

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
        if line in ("help", "tools"):
            await list_tools(client)
            continue

        # Parse: tool_name key=value key=value
        parts = line.split()
        tool_name = parts[0]

        if tool_name not in tool_names:
            # Try it anyway — the server might have it
            pass

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


async def main() -> None:
    """Entry point."""
    server_url = os.environ.get("CERAMIC_SERVER_URL", DEFAULT_SERVER_URL)

    # Parse remaining CLI args (tool_name key=value ...)
    remaining = sys.argv[1:]

    print(f"Connecting to {server_url}...")
    print("(If this is your first call, a browser window will open for authentication)\n")

    async with Client(server_url) as client:
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
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
