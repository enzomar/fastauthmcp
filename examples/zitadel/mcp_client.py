"""FastAuthMCP E2E Demo — simple terminal client that emulates LLM tool calls.

Shows what happens when an LLM calls MCP tools through a FastAuthMCP-protected
server: authentication, session reuse, and identity propagation.

Usage:
    # Via stdio (default — spawns server as subprocess, most reliable)
    python mcp_client.py

    # Against a running SSE server
    python mcp_client.py --transport sse --url http://localhost:8000/sse

Environment:
    FASTAUTHMCP_SERVER_URL — Server URL for SSE/HTTP (default: http://localhost:8000/sse)

Requirements:
    pip install fastmcp
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import time
from pathlib import Path

# ---------------------------------------------------------------------------
# ANSI colors
# ---------------------------------------------------------------------------

BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
CYAN = "\033[36m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RED = "\033[31m"
MAGENTA = "\033[35m"
BLUE = "\033[34m"


def header(text: str) -> None:
    print(f"\n{BOLD}{'─' * 60}{RESET}")
    print(f"{BOLD}{text}{RESET}")
    print(f"{BOLD}{'─' * 60}{RESET}")


def narrator(lines: list[str]) -> None:
    for line in lines:
        print(f"  {line}")
    print()


def pipeline(stage: str, detail: str) -> None:
    print(f"  {DIM}{time.strftime('%H:%M:%S')}{RESET}  {stage}  {detail}")


# ---------------------------------------------------------------------------
# Demo steps
# ---------------------------------------------------------------------------

DEMO_STEPS = [
    {
        "prompt": "Who am I?",
        "narrator": [
            f"{BOLD}{CYAN}STEP 1: First Tool Call{RESET}",
            "",
            "The LLM calls the 'whoami' tool on the MCP server.",
            f"Since this is the {BOLD}{YELLOW}first request{RESET}, there is no session.",
            "FastAuthMCP's middleware will:",
            "",
            "  1. Observability → assign request ID, start span",
            "  2. Session → no session found",
            f"  3. {BOLD}{YELLOW}Authentication → no token!{RESET}",
            "     → open browser for OAuth2 login",
            "     → wait for you to sign in",
            "     → exchange code for tokens",
            "  4. Tool → execute whoami()",
            "",
            f"{YELLOW}Your browser will open for login.{RESET}",
            "",
            f"{BOLD}{YELLOW}━━━ Zitadel Demo Credentials ━━━{RESET}",
            f"  Username: {BOLD}playground@ceramic.local{RESET}",
            f"  Password: {BOLD}Playground0.{RESET}",
        ],
        "tool": "whoami",
        "args": {},
    },
    {
        "prompt": "Show me the available pets",
        "narrator": [
            f"{BOLD}{CYAN}STEP 2: Session Reuse{RESET}",
            "",
            "The LLM calls 'list_pets'. This time, the session exists.",
            "",
            "  1. Observability → assign request ID",
            f"  2. {BOLD}{GREEN}Session → FOUND ✓{RESET} (restore identity)",
            f"  3. Authentication → {GREEN}SKIPPED{RESET} (session valid)",
            "  4. Tool → execute list_pets()",
            "",
            f"{GREEN}No browser popup. No re-auth. Instant.{RESET}",
        ],
        "tool": "list_pets",
        "args": {"status": "available"},
    },
    {
        "prompt": "Tell me about pet-001",
        "narrator": [
            f"{BOLD}{CYAN}STEP 3: Identity Inside Tools{RESET}",
            "",
            "The LLM calls 'get_pet'. Session is reused again.",
            "The identity is available inside the tool via fastauthmcp.identity().",
        ],
        "tool": "get_pet",
        "args": {"pet_id": "pet-001"},
    },
    {
        "prompt": "Add a new pet: Buddy the Golden Retriever, age 2",
        "narrator": [
            f"{BOLD}{CYAN}STEP 4: Write Operation{RESET}",
            "",
            "The LLM calls 'add_pet' — a write operation.",
            "The identity records who added the pet.",
        ],
        "tool": "add_pet",
        "args": {
            "name": "Buddy",
            "species": "dog",
            "breed": "Golden Retriever",
            "age": 2,
        },
    },
]


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def run_demo(transport: str, url: str | None) -> None:
    from fastmcp import Client

    target = _get_target(transport, url)

    print(f"\n{BOLD}FastAuthMCP E2E Demo{RESET}")
    print(f"  Transport: {transport}")
    print(f"  Server:    {_display_target(transport, url)}")
    print()
    print(f"{DIM}Connecting to MCP server...{RESET}")

    async with Client(target, timeout=300) as client:
        tools = await client.list_tools()
        tool_names = ", ".join(t.name for t in tools)
        print(f"{GREEN}✓ Connected{RESET} — {len(tools)} tools: {tool_names}")

        for i, step in enumerate(DEMO_STEPS):
            # Wait for user to press Enter
            print()
            input(f"{DIM}Press Enter for step {i + 1}...{RESET}")

            header(f'PROMPT: "{step["prompt"]}"')
            narrator(step["narrator"])

            # Show the tool call
            args_str = ", ".join(f"{k}={v!r}" for k, v in step["args"].items())
            print(f"  {BLUE}→ calling{RESET} {BOLD}{step['tool']}{RESET}({args_str})")
            print()

            # Pipeline animation
            pipeline(f"{CYAN}▶ Observability{RESET}", "request_id assigned")
            pipeline(f"{YELLOW}▶ Session{RESET}", "checking...")
            pipeline(f"{GREEN}▶ Authentication{RESET}", "validating token...")

            # Execute (with retry — first call may fail if OAuth flow caused a reconnect)
            result = None
            for attempt in range(3):
                start = time.perf_counter()
                try:
                    result = await client.call_tool(step["tool"], step["args"])
                    elapsed = (time.perf_counter() - start) * 1000
                    pipeline(f"{GREEN}✓ Complete{RESET}", f"{elapsed:.0f}ms")
                    break
                except Exception as exc:
                    elapsed = (time.perf_counter() - start) * 1000
                    if attempt < 2:
                        print(f"  {DIM}(connection recovered, retrying...){RESET}")
                        await asyncio.sleep(1)
                    else:
                        pipeline(f"{RED}✗ Failed{RESET}", f"{elapsed:.0f}ms")
                        print(f"  {RED}Error:{RESET} {exc}")

            if result is not None:
                print()
                # Display result
                if isinstance(result, list) and result:
                    for item in result:
                        text = item.text if hasattr(item, "text") else str(item)
                        try:
                            parsed = json.loads(text)
                            formatted = json.dumps(parsed, indent=2)
                            print(f"  {GREEN}✓ Result:{RESET}")
                            for line in formatted.split("\n"):
                                print(f"    {DIM}{line}{RESET}")
                        except (json.JSONDecodeError, TypeError):
                            print(f"  {GREEN}✓{RESET} {text}")
                else:
                    print(f"  {GREEN}✓{RESET} {result}")

    # Summary
    header("DEMO COMPLETE")
    print(f"""
  What you just saw:

  1. First tool call triggered OAuth2 login in the browser
  2. Token stored securely — session established
  3. All subsequent calls reused the session (instant, no re-auth)
  4. Identity available inside every tool via fastauthmcp.identity()

  {DIM}All of this happened transparently.
  The server code has zero auth logic — just a YAML file.{RESET}
""")


def _get_target(transport: str, url: str | None):
    if transport == "stdio":
        from fastmcp.client.transports import PythonStdioTransport

        server_path = str(Path(__file__).parent / "petstore_server.py")
        return PythonStdioTransport(script_path=server_path)
    elif transport == "streamable-http":
        return url or os.environ.get("FASTAUTHMCP_SERVER_URL", "http://localhost:8000/mcp")
    else:
        return url or os.environ.get("FASTAUTHMCP_SERVER_URL", "http://localhost:8000/sse")


def _display_target(transport: str, url: str | None) -> str:
    if transport == "stdio":
        return "petstore_server.py (subprocess)"
    return url or os.environ.get("FASTAUTHMCP_SERVER_URL", "http://localhost:8000/sse")


def main():
    parser = argparse.ArgumentParser(description="FastAuthMCP E2E Demo")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport (default: stdio)",
    )
    parser.add_argument("--url", default=None, help="Server URL for SSE/HTTP")
    args = parser.parse_args()

    try:
        asyncio.run(run_demo(args.transport, args.url))
    except KeyboardInterrupt:
        print(f"\n{DIM}Interrupted.{RESET}")


if __name__ == "__main__":
    main()
