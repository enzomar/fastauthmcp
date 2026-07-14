"""Ceramic testing utilities for simulating authenticated requests.

Provides CeramicTestClient for bypassing OAuth flows and injecting identity
directly into the middleware pipeline, and MockIdentityProvider for generating
structurally valid JWTs without network calls.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from types import MappingProxyType
from typing import Any

from ceramic.identity import IdentityContext, _identity_context_var, _access_token_var
from ceramic.middleware.pipeline import (
    MiddlewarePipeline as MiddlewarePipeline,
    RequestContext,
)
from ceramic.server import CeramicFastMCP


class CeramicTestClient:
    """Test client that simulates authenticated requests.

    Bypasses OAuth flows and injects identity directly into the middleware
    pipeline.

    Example::

        client = CeramicTestClient(
            app,
            email="user@example.com",
            roles=["admin"],
        )
        result = await client.call_tool("admin_dashboard", query="status")
        CeramicTestClient.assert_authorized(result)
    """

    def __init__(
        self,
        app: CeramicFastMCP,
        email: str | None = None,
        subject: str | None = None,
        claims: dict | None = None,
        roles: list[str] | None = None,
        groups: list[str] | None = None,
    ) -> None:
        """Initialize the test client.

        Args:
            app: The CeramicFastMCP application instance to test against.
            email: Email address for the simulated identity.
            subject: Subject identifier for the simulated identity.
            claims: Additional JWT claims for the simulated identity.
            roles: List of roles assigned to the simulated identity.
            groups: List of groups assigned to the simulated identity.
        """
        self._app = app
        self._identity = IdentityContext(
            email=email,
            subject=subject,
            claims=MappingProxyType(claims or {}),
            roles=frozenset(roles or []),
            groups=frozenset(groups or []),
        )

    @property
    def identity(self) -> IdentityContext:
        """The configured identity context for this test client."""
        return self._identity

    async def call_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """Simulate a tool invocation with the configured identity.

        Creates a RequestContext, injects the identity, and runs through
        the middleware pipeline (skipping authentication and session
        middleware since identity is already provided).

        Args:
            tool_name: The name of the tool to invoke.
            **kwargs: Arguments to pass to the tool function.

        Returns:
            The tool result.
        """
        # Create the request context
        ctx = RequestContext(tool_name=tool_name)

        # Inject the configured identity into the context
        ctx.identity = self._identity

        # Set the identity context var so ceramic.identity() works
        token = _identity_context_var.set(self._identity)
        # Set a test access token so ceramic.access_token() works
        access_tok = _access_token_var.set("ceramic-test-token")

        try:
            # Build a test-only pipeline that skips auth/session middleware
            # but preserves observability behavior.
            from ceramic.middleware.builtin import (
                AuthenticationMiddleware as BuiltinAuthMW,
                SessionMiddleware as BuiltinSessionMW,
            )
            from ceramic.middleware.authentication import (
                AuthenticationMiddleware as RealAuthMW,
            )
            from ceramic.middleware.session import (
                SessionMiddleware as RealSessionMW,
            )
            from ceramic.middleware.pipeline import MiddlewarePipeline

            _skip_types = (BuiltinAuthMW, BuiltinSessionMW, RealAuthMW, RealSessionMW)

            test_pipeline = MiddlewarePipeline()
            for mw in self._app._pipeline._before:
                # Skip authentication and session middleware — identity is injected
                if isinstance(mw, _skip_types):
                    continue
                test_pipeline.add_before(mw)

            for mw in self._app._pipeline._after:
                test_pipeline.add_after(mw)

            for mw in self._app._pipeline._on_exception:
                test_pipeline.add_exception_handler(mw)

            # Look up the tool function from the app registry
            tool_func = self._app._tool_functions.get(tool_name)

            async def handler() -> Any:
                if tool_func is None:
                    return {
                        "error": "tool_not_found",
                        "message": f"Tool '{tool_name}' not found",
                    }
                import inspect

                result = tool_func(**kwargs)
                if inspect.isawaitable(result):
                    return await result
                return result

            # Execute through the filtered pipeline
            result = await test_pipeline.execute(ctx, handler)
            return result
        finally:
            # Reset the context vars
            _identity_context_var.reset(token)
            _access_token_var.reset(access_tok)

    @staticmethod
    def assert_success(response: Any) -> None:
        """Assert that the response does NOT indicate an error.

        Args:
            response: The response from call_tool().

        Raises:
            AssertionError: If the response contains an error field.
        """
        if isinstance(response, dict) and response.get("error"):
            raise AssertionError(
                f"Expected successful response but got error: "
                f"{response.get('message', response.get('error', ''))}"
            )


class MockIdentityProvider:
    """Generates structurally valid JWTs without network calls.

    Uses HMAC-SHA256 (HS256) with a test secret key to produce decodable
    JWT tokens suitable for testing scenarios.

    Example::

        provider = MockIdentityProvider()
        token = provider.issue_token({
            "sub": "user-123",
            "email": "user@example.com",
            "roles": ["admin"],
        })
    """

    DEFAULT_SECRET = "ceramic-test-secret"

    def __init__(self, secret: str | None = None) -> None:
        """Initialize the mock identity provider.

        Args:
            secret: The HMAC secret key for signing JWTs.
                Defaults to "ceramic-test-secret".
        """
        self._secret = secret or self.DEFAULT_SECRET

    def issue_token(self, claims: dict) -> str:
        """Create a structurally valid JWT with the provided claims.

        The token includes:
        - Header: {"alg": "HS256", "typ": "JWT"}
        - Payload: provided claims + iat (issued at) + exp (1h from now)
        - Signature: HMAC-SHA256 with the configured secret key

        Args:
            claims: The claims to include in the JWT payload.

        Returns:
            A complete, decodable JWT string (header.payload.signature).
        """
        # Header
        header = {"alg": "HS256", "typ": "JWT"}

        # Payload: merge provided claims with iat and exp
        now = int(time.time())
        payload = {**claims, "iat": now, "exp": now + 3600}

        # Encode header and payload
        header_b64 = self._base64url_encode(json.dumps(header, separators=(",", ":")))
        payload_b64 = self._base64url_encode(json.dumps(payload, separators=(",", ":")))

        # Create signature
        signing_input = f"{header_b64}.{payload_b64}"
        signature = hmac.HMAC(
            self._secret.encode("utf-8"),
            signing_input.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        signature_b64 = self._base64url_encode_bytes(signature)

        return f"{header_b64}.{payload_b64}.{signature_b64}"

    @staticmethod
    def _base64url_encode(data: str) -> str:
        """Base64url-encode a string (no padding)."""
        return (
            base64.urlsafe_b64encode(data.encode("utf-8")).rstrip(b"=").decode("ascii")
        )

    @staticmethod
    def _base64url_encode_bytes(data: bytes) -> str:
        """Base64url-encode raw bytes (no padding)."""
        return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")

    @staticmethod
    def decode_token(token: str) -> tuple[dict, dict]:
        """Decode a JWT token without verification (for testing).

        Args:
            token: The JWT string to decode.

        Returns:
            A tuple of (header, payload) dicts.
        """
        parts = token.split(".")
        if len(parts) != 3:
            raise ValueError(f"Invalid JWT format: expected 3 parts, got {len(parts)}")

        header = json.loads(MockIdentityProvider._base64url_decode(parts[0]))
        payload = json.loads(MockIdentityProvider._base64url_decode(parts[1]))
        return header, payload

    @staticmethod
    def _base64url_decode(data: str) -> bytes:
        """Base64url-decode a string (handles missing padding)."""
        # Add padding if necessary
        padding = 4 - len(data) % 4
        if padding != 4:
            data += "=" * padding
        return base64.urlsafe_b64decode(data)
