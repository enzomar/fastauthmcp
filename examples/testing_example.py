"""Example: Testing authenticated tools without a live IDP.

Run with:
    pytest examples/testing_example.py
"""

import pytest

from ceramic import FastMCP, require_role, identity
from ceramic.testing import CeramicTestClient

# --- App setup ---

mcp = FastMCP("test-app")


@mcp.tool()
@require_role("viewer")
def get_dashboard() -> dict:
    user = identity()
    return {"dashboard": "main", "user": user.email}


@mcp.tool()
@require_role("admin")
def delete_user(user_id: str) -> str:
    return f"Deleted {user_id}"


# --- Tests ---


@pytest.mark.asyncio
async def test_authorized_access():
    """A user with the 'viewer' role can access the dashboard."""
    client = CeramicTestClient(
        app=mcp,
        email="viewer@example.com",
        subject="user-123",
        roles=["viewer"],
    )
    result = await client.call_tool("get_dashboard")
    CeramicTestClient.assert_authorized(result)


@pytest.mark.asyncio
async def test_unauthorized_access():
    """A user without the 'admin' role is rejected from delete_user."""
    client = CeramicTestClient(
        app=mcp,
        email="viewer@example.com",
        roles=["viewer"],  # Missing 'admin'
    )
    result = await client.call_tool("delete_user", user_id="u-456")
    CeramicTestClient.assert_unauthorized(result)
