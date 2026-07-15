"""Basic FastAuthMCP server — drop-in replacement for FastMCP.

Run with:
    fastauthmcp run
    # or
    python examples/basic_server.py
"""

from fastauthmcp import FastMCP

mcp = FastMCP("basic-server")


@mcp.tool()
def greet(name: str) -> str:
    """Greet someone by name."""
    return f"Hello, {name}!"


@mcp.tool()
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


if __name__ == "__main__":
    mcp.run()
