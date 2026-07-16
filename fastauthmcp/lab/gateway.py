"""FastAuthMCP gateway wrapper for lab testing.

Creates a FastAuthMCP server instance and provides methods to
simulate tool calls with injected tokens, verifying the full
middleware pipeline.
"""

from __future__ import annotations

from typing import Any

from fastauthmcp.identity import IdentityContext
from fastauthmcp.server import FastAuthMCP
from fastauthmcp.testing import FastAuthMCPTestClient, MockIdentityProvider


class LabGateway:
    """Wraps a FastAuthMCP server for lab scenario testing.

    Provides a simplified API to:
    - Create an authenticated session with a given token
    - Call tools and verify identity propagation
    - Test access control and claim extraction
    """

    def __init__(self, server: FastAuthMCP | None = None) -> None:
        self._server = server or self._create_default_server()
        self._idp = MockIdentityProvider()

    def _create_default_server(self) -> FastAuthMCP:
        """Create a default lab server with sample tools."""
        # Minimal config — passthrough mode (no real IDP needed for lab tests)
        server = FastAuthMCP(name="lab-server")

        @server.tool()
        def whoami() -> dict:
            from fastauthmcp import identity

            ctx = identity()
            return {
                "subject": ctx.subject,
                "email": ctx.email,
                "roles": sorted(ctx.roles),
                "groups": sorted(ctx.groups),
            }

        @server.tool()
        def get_profile() -> dict:
            from fastauthmcp import identity

            ctx = identity()
            return {"user": ctx.email, "claims": dict(ctx.claims)}

        @server.tool()
        def admin_action() -> dict:
            from fastauthmcp import identity

            ctx = identity()
            if "admin" not in ctx.roles:
                return {"error": "forbidden", "message": "Admin role required"}
            return {"action": "completed", "by": ctx.email}

        return server

    async def authenticate(
        self,
        token: str,
        *,
        email: str | None = None,
        subject: str | None = None,
        roles: list[str] | None = None,
        groups: list[str] | None = None,
    ) -> "AuthenticatedSession":
        """Create an authenticated session from a token.

        Decodes the token claims and creates a test client with the identity.
        """
        _, payload = MockIdentityProvider.decode_token(token)

        return AuthenticatedSession(
            server=self._server,
            email=email or payload.get("email"),
            subject=subject or payload.get("sub"),
            roles=roles or payload.get("roles", []),
            groups=groups or payload.get("groups", []),
        )


class AuthenticatedSession:
    """An authenticated session against the lab gateway."""

    def __init__(
        self,
        server: FastAuthMCP,
        email: str | None,
        subject: str | None,
        roles: list[str] | None = None,
        groups: list[str] | None = None,
    ) -> None:
        self._client = FastAuthMCPTestClient(
            server,
            email=email,
            subject=subject,
            roles=roles,
            groups=groups,
        )

    @property
    def identity(self) -> IdentityContext:
        return self._client.identity

    async def call_tool(self, tool_name: str, **kwargs: Any) -> Any:
        return await self._client.call_tool(tool_name, **kwargs)
