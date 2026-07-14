"""Unit tests for the Ceramic testing utilities (CeramicTestClient and MockIdentityProvider)."""

from __future__ import annotations

import time
from types import MappingProxyType
from unittest.mock import patch

import pytest

from ceramic.identity import identity
from ceramic.testing import CeramicTestClient, MockIdentityProvider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_app():
    """Create a minimal mock CeramicFastMCP app."""
    from ceramic.middleware.pipeline import MiddlewarePipeline

    class FakeApp:
        """Minimal app-like object for testing."""

        def __init__(self):
            self._tool_functions: dict = {}
            self._pipeline = MiddlewarePipeline()

    app = FakeApp()
    return app


# ---------------------------------------------------------------------------
# CeramicTestClient Tests
# ---------------------------------------------------------------------------


class TestCeramicTestClientInit:
    """Tests for CeramicTestClient initialization."""

    def test_creates_identity_with_email(self, mock_app):
        client = CeramicTestClient(mock_app, email="user@example.com")
        assert client.identity.email == "user@example.com"

    def test_creates_identity_with_subject(self, mock_app):
        client = CeramicTestClient(mock_app, subject="sub-123")
        assert client.identity.subject == "sub-123"

    def test_creates_identity_with_claims(self, mock_app):
        client = CeramicTestClient(mock_app, claims={"custom": "value"})
        assert client.identity.claims["custom"] == "value"

    def test_creates_identity_with_roles(self, mock_app):
        client = CeramicTestClient(mock_app, roles=["admin", "editor"])
        assert client.identity.roles == frozenset(["admin", "editor"])

    def test_creates_identity_with_groups(self, mock_app):
        client = CeramicTestClient(mock_app, groups=["ops-team"])
        assert client.identity.groups == frozenset(["ops-team"])

    def test_defaults_to_none_and_empty(self, mock_app):
        client = CeramicTestClient(mock_app)
        assert client.identity.email is None
        assert client.identity.subject is None
        assert client.identity.claims == MappingProxyType({})
        assert client.identity.roles == frozenset()
        assert client.identity.groups == frozenset()

    def test_identity_is_immutable(self, mock_app):
        client = CeramicTestClient(mock_app, email="user@example.com")
        with pytest.raises(AttributeError):
            client.identity.email = "other@example.com"


class TestCeramicTestClientCallTool:
    """Tests for CeramicTestClient.call_tool()."""

    @pytest.mark.asyncio
    async def test_calls_tool_function_when_no_middleware(self, mock_app):
        """Tool function is invoked when no middleware blocks it."""

        async def my_tool(x: int = 0) -> dict:
            return {"result": x * 2}

        mock_app._tool_functions["my_tool"] = my_tool
        client = CeramicTestClient(mock_app, email="user@example.com")

        result = await client.call_tool("my_tool", x=5)
        assert result == {"result": 10}

    @pytest.mark.asyncio
    async def test_returns_tool_not_found_for_missing_tool(self, mock_app):
        """Returns error dict when tool is not registered."""
        client = CeramicTestClient(mock_app, email="user@example.com")

        result = await client.call_tool("nonexistent_tool")
        assert result["error"] == "tool_not_found"

    @pytest.mark.asyncio
    async def test_identity_context_var_is_set_during_call(self, mock_app):
        """The _identity_context_var is properly set during tool execution."""
        captured_identity = {}

        async def capture_tool() -> dict:
            ctx = identity()
            captured_identity["email"] = ctx.email
            captured_identity["roles"] = ctx.roles
            return {"captured": True}

        mock_app._tool_functions["capture_tool"] = capture_tool
        client = CeramicTestClient(mock_app, email="test@example.com", roles=["tester"])

        result = await client.call_tool("capture_tool")
        assert result == {"captured": True}
        assert captured_identity["email"] == "test@example.com"
        assert "tester" in captured_identity["roles"]

    @pytest.mark.asyncio
    async def test_identity_context_var_is_reset_after_call(self, mock_app):
        """The _identity_context_var is reset after call_tool completes."""

        async def simple_tool() -> dict:
            return {"ok": True}

        mock_app._tool_functions["simple_tool"] = simple_tool
        client = CeramicTestClient(mock_app, email="test@example.com")

        await client.call_tool("simple_tool")

        # After the call, identity() should raise RuntimeError
        with pytest.raises(RuntimeError):
            identity()


class TestCeramicTestClientAssertions:
    """Tests for CeramicTestClient static assertion helpers."""

    def test_assert_success_passes_for_normal_response(self):
        """assert_success passes for a non-error response."""
        CeramicTestClient.assert_success({"result": "success"})

    def test_assert_success_passes_for_non_dict(self):
        """assert_success passes for non-dict responses."""
        CeramicTestClient.assert_success("hello")
        CeramicTestClient.assert_success(42)
        CeramicTestClient.assert_success(None)

    def test_assert_success_fails_for_error_response(self):
        """assert_success raises AssertionError for error responses."""
        with pytest.raises(AssertionError):
            CeramicTestClient.assert_success(
                {"error": "internal_error", "message": "Something went wrong"}
            )

    def test_assert_success_passes_for_empty_dict(self):
        """assert_success passes for a dict without 'error' key."""
        CeramicTestClient.assert_success({"data": "value"})


# ---------------------------------------------------------------------------
# MockIdentityProvider Tests
# ---------------------------------------------------------------------------


class TestMockIdentityProvider:
    """Tests for MockIdentityProvider."""

    def test_issue_token_returns_three_part_jwt(self):
        """Issued token has three base64url-encoded parts separated by dots."""
        provider = MockIdentityProvider()
        token = provider.issue_token({"sub": "user-123"})

        parts = token.split(".")
        assert len(parts) == 3

    def test_issue_token_header_has_alg_and_typ(self):
        """JWT header contains alg=HS256 and typ=JWT."""
        provider = MockIdentityProvider()
        token = provider.issue_token({"sub": "user-123"})

        header, _ = MockIdentityProvider.decode_token(token)
        assert header["alg"] == "HS256"
        assert header["typ"] == "JWT"

    def test_issue_token_payload_contains_claims(self):
        """JWT payload contains all provided claims."""
        provider = MockIdentityProvider()
        claims = {"sub": "user-123", "email": "user@example.com", "roles": ["admin"]}
        token = provider.issue_token(claims)

        _, payload = MockIdentityProvider.decode_token(token)
        assert payload["sub"] == "user-123"
        assert payload["email"] == "user@example.com"
        assert payload["roles"] == ["admin"]

    def test_issue_token_payload_has_iat(self):
        """JWT payload contains iat (issued at) timestamp."""
        provider = MockIdentityProvider()
        before = int(time.time())
        token = provider.issue_token({"sub": "user-123"})
        after = int(time.time())

        _, payload = MockIdentityProvider.decode_token(token)
        assert "iat" in payload
        assert before <= payload["iat"] <= after

    def test_issue_token_payload_has_exp(self):
        """JWT payload contains exp (expiration) timestamp 1h from now."""
        provider = MockIdentityProvider()
        token = provider.issue_token({"sub": "user-123"})

        _, payload = MockIdentityProvider.decode_token(token)
        assert "exp" in payload
        # exp should be approximately 1h (3600s) after iat
        assert payload["exp"] - payload["iat"] == 3600

    def test_issue_token_with_custom_secret(self):
        """Provider can use a custom secret key."""
        provider = MockIdentityProvider(secret="my-custom-secret")
        token = provider.issue_token({"sub": "user-123"})

        # Token is still decodable
        header, payload = MockIdentityProvider.decode_token(token)
        assert payload["sub"] == "user-123"

    def test_issue_token_signature_is_deterministic(self):
        """Same claims and time produce the same signature with the same secret."""
        provider = MockIdentityProvider(secret="fixed-secret")

        with patch("ceramic.testing.time.time", return_value=1700000000.0):
            token1 = provider.issue_token({"sub": "user-123"})
            token2 = provider.issue_token({"sub": "user-123"})

        assert token1 == token2

    def test_issue_token_different_claims_different_token(self):
        """Different claims produce different tokens."""
        provider = MockIdentityProvider()

        with patch("ceramic.testing.time.time", return_value=1700000000.0):
            token1 = provider.issue_token({"sub": "user-1"})
            token2 = provider.issue_token({"sub": "user-2"})

        assert token1 != token2

    def test_decode_token_invalid_format_raises(self):
        """decode_token raises ValueError for invalid JWT format."""
        with pytest.raises(ValueError, match="Invalid JWT format"):
            MockIdentityProvider.decode_token("not.a.valid.jwt.with.extra.parts")

        with pytest.raises(ValueError, match="Invalid JWT format"):
            MockIdentityProvider.decode_token("only-one-part")

    def test_issue_token_preserves_existing_iat_exp(self):
        """Provided iat/exp in claims are overridden by the provider."""
        provider = MockIdentityProvider()
        token = provider.issue_token({"sub": "user-123", "iat": 0, "exp": 0})

        _, payload = MockIdentityProvider.decode_token(token)
        # iat and exp should be current time, not 0
        assert payload["iat"] > 0
        assert payload["exp"] > 0

    def test_default_secret(self):
        """Default secret is 'ceramic-test-secret'."""
        provider = MockIdentityProvider()
        assert provider._secret == "ceramic-test-secret"
