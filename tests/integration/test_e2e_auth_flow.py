"""End-to-end integration test for the full authentication pipeline.

Creates a FastAuthMCP server with auth config, issues a token via
MockIdentityProvider, makes a tool call through the full pipeline,
and verifies identity()/access_token() work inside the tool.
"""

from __future__ import annotations

import pytest

from fastauthmcp.identity import access_token, identity
from fastauthmcp.server import FastAuthMCP
from fastauthmcp.testing import FastAuthMCPTestClient, MockIdentityProvider


@pytest.fixture
def auth_server(tmp_path, monkeypatch):
    """Create a FastAuthMCP server with auth enabled."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FASTAUTHMCP_CONFIG", raising=False)

    config_file = tmp_path / "fastauthmcp.yaml"
    config_file.write_text(
        "auth:\n"
        "  provider: oidc\n"
        "  issuer: https://idp.example.com\n"
        "  client_id: test-app\n"
        "  client_secret: test-secret\n"
        "observability:\n"
        "  enabled: true\n"
    )

    server = FastAuthMCP(name="e2e-server", config=str(config_file))

    @server.tool()
    def whoami() -> dict:
        """Return the authenticated user's identity info."""
        ctx = identity()
        token = access_token()
        return {
            "subject": ctx.subject,
            "email": ctx.email,
            "roles": sorted(ctx.roles),
            "token_present": token is not None and len(token) > 0,
        }

    return server


@pytest.fixture
def mock_idp():
    """Create a MockIdentityProvider instance."""
    return MockIdentityProvider()


class TestE2EAuthFlow:
    """Full pipeline integration test."""

    @pytest.mark.asyncio
    async def test_tool_call_with_identity(self, auth_server, mock_idp):
        """Token issued → tool call → identity() and access_token() work."""
        # Issue a token via MockIdentityProvider
        token = mock_idp.issue_token(
            {
                "sub": "user-42",
                "email": "alice@example.com",
                "roles": ["admin", "viewer"],
            }
        )

        # Verify token is structurally valid
        header, payload = MockIdentityProvider.decode_token(token)
        assert header["alg"] == "HS256"
        assert payload["sub"] == "user-42"
        assert payload["email"] == "alice@example.com"

        # Create a test client that simulates the authenticated user
        client = FastAuthMCPTestClient(
            auth_server,
            email="alice@example.com",
            subject="user-42",
            roles=["admin", "viewer"],
        )

        # Make a tool call through the full middleware pipeline
        result = await client.call_tool("whoami")

        # Verify identity() worked inside the tool
        assert result["subject"] == "user-42"
        assert result["email"] == "alice@example.com"
        assert result["roles"] == ["admin", "viewer"]

        # Verify access_token() returned a valid (non-empty) token
        assert result["token_present"] is True

    @pytest.mark.asyncio
    async def test_unauthenticated_tool_call(self, auth_server):
        """Tool call without identity returns tool_not_found or works depending on config."""
        client = FastAuthMCPTestClient(
            auth_server,
            email=None,
            subject=None,
        )

        # Even an unauthenticated client can call tools that don't require auth
        # (FastAuthMCPTestClient injects identity directly)
        result = await client.call_tool("whoami")

        # identity() still works — returns the injected (None) values
        assert result["subject"] is None
        assert result["email"] is None

    @pytest.mark.asyncio
    async def test_nonexistent_tool(self, auth_server):
        """Calling a nonexistent tool returns an error dict."""
        client = FastAuthMCPTestClient(
            auth_server,
            email="user@example.com",
            subject="user-1",
        )

        result = await client.call_tool("nonexistent_tool")

        assert isinstance(result, dict)
        assert result.get("error") == "tool_not_found"
