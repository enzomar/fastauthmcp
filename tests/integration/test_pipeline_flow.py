"""Integration tests: full pipeline flow with mocked IDP.

These tests verify the end-to-end middleware pipeline behavior without
making real network calls.
"""

from __future__ import annotations

import pytest

from ceramic import FastMCP, identity
from ceramic.testing import CeramicTestClient


# --- Test server ---

mcp = FastMCP("integration-test-server")


@mcp.tool()
def get_profile() -> dict:
    """Return the authenticated user's profile."""
    user = identity()
    return {
        "email": user.email,
        "subject": user.subject,
        "roles": sorted(user.roles),
        "groups": sorted(user.groups),
    }


@mcp.tool()
def greet(name: str) -> str:
    """Greet someone (uses identity for audit)."""
    user = identity()
    return f"Hello {name}, from {user.email}"


# --- Integration tests ---


@pytest.mark.asyncio
async def test_full_tool_call_with_identity():
    """A tool call receives the full identity context through the pipeline."""
    client = CeramicTestClient(
        app=mcp,
        email="engineer@company.com",
        subject="user-42",
        roles=["engineer", "viewer"],
        groups=["platform-team"],
    )
    result = await client.call_tool("get_profile")

    assert result["email"] == "engineer@company.com"
    assert result["subject"] == "user-42"
    assert result["roles"] == ["engineer", "viewer"]
    assert result["groups"] == ["platform-team"]


@pytest.mark.asyncio
async def test_tool_with_arguments_and_identity():
    """Tool arguments are passed correctly alongside identity."""
    client = CeramicTestClient(
        app=mcp,
        email="admin@company.com",
        subject="admin-1",
    )
    result = await client.call_tool("greet", name="World")
    assert result == "Hello World, from admin@company.com"


@pytest.mark.asyncio
async def test_tool_not_found():
    """Calling a non-existent tool returns an error dict."""
    client = CeramicTestClient(
        app=mcp,
        email="test@example.com",
    )
    result = await client.call_tool("nonexistent_tool")
    assert isinstance(result, dict)
    assert result["error"] == "tool_not_found"


@pytest.mark.asyncio
async def test_multiple_calls_isolated():
    """Each call has its own identity (no leakage between calls)."""
    client_a = CeramicTestClient(app=mcp, email="alice@co.com", subject="a-1")
    client_b = CeramicTestClient(app=mcp, email="bob@co.com", subject="b-2")

    result_a = await client_a.call_tool("get_profile")
    result_b = await client_b.call_tool("get_profile")

    assert result_a["email"] == "alice@co.com"
    assert result_b["email"] == "bob@co.com"
    assert result_a["subject"] == "a-1"
    assert result_b["subject"] == "b-2"
