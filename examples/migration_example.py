"""Middleware-attachment migration style.

Shows how to add FastAuthMCP to an existing FastMCP app without changing the import.
Useful for gradual adoption.

Run with:
    python examples/migration_example.py
"""

from fastmcp import FastMCP

# --- Existing code (unchanged) ---

app = FastMCP("legacy-server")


@app.tool()
def legacy_tool(x: int) -> int:
    """An existing tool that doesn't need modification."""
    return x * 2


@app.tool()
def another_tool(msg: str) -> str:
    """Another pre-existing tool."""
    return msg.upper()


# --- Add FastAuthMCP enterprise features ---

from fastauthmcp import FastMCP as FastAuthMCP  # noqa: E402

fastauthmcp_app = FastAuthMCP.enable_fastauthmcp(app, config="fastauthmcp.yaml")

if __name__ == "__main__":
    fastauthmcp_app.run()
