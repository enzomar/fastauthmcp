"""Example: Testing authenticated tools without a live IDP.

Run with:
    pytest examples/testing_example.py
"""

import pytest

from ceramic import FastMCP, identity
from ceramic.testing import CeramicTestClient

# --- App setup ---

mcp = FastMCP("test-app")


@mcp.tool()
def get_dashboard() -> dict:
    user = identity()
    return {"dashboard": "main", "user": user.email}


@mcp.tool()
def delete_user(user_id: str) -> str:
    return f"Deleted {user_id}"


# --- Tests ---


@pytest.mark.asyncio
async def test_authenticated_access():
    """An authenticated user can access the dashboard."""
    client = CeramicTestClient(
        app=mcp,
        email="viewer@example.com",
        subject="user-123",
        roles=["viewer"],
    )
    result = await client.call_tool("get_dashboard")
    assert result["user"] == "viewer@example.com"


@pytest.mark.asyncio
async def test_identity_propagation():
    """Identity context is available in tool functions."""
    client = CeramicTestClient(
        app=mcp,
        email="admin@example.com",
        roles=["admin"],
    )
    result = await client.call_tool("delete_user", user_id="u-456")
    assert result == "Deleted u-456"
