"""Unit tests for the Ceramic testing utilities (CeramicTestClient and MockIdentityProvider)."""

from __future__ import annotations

import json
import time
from types import MappingProxyType
from unittest.mock import patch

import pytest

from ceramic.authorization import require_group, require_role
from ceramic.config import AuthorizationConfig, AuthorizationPolicy
from ceramic.identity import IdentityContext, _identity_context_var, identity
from ceramic.testing import CeramicTestClient, MockIdentityProvider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_app():
    """Create a minimal mock CeramicFastMCP app with authorization pipeline."""
    from ceramic.middleware.authorization import AuthorizationMiddleware
    from ceramic.middleware.pipeline import MiddlewarePipeline

    class FakeApp:
        """Minimal app-like object for testing."""

        def __init__(self):
            self._tool_functions: dict = {}
            self._pipeline = MiddlewarePipeline()

    app = FakeApp()
    return app


@pytest.fixture
def mock_app_with_authz():
    """Create a mock app with authorization middleware configured."""
    from ceramic.middleware.authorization import AuthorizationMiddleware
    from ceramic.middleware.pipeline import MiddlewarePipeline

    class FakeApp:
        def __init__(self):
            self._tool_functions: dict = {}
            self._pipeline = MiddlewarePipeline()
            self._authz_config = AuthorizationConfig(policies=[])
            self._authz_mw = AuthorizationMiddleware(
                authz_config=self._authz_config,
                tool_functions=self._tool_functions,
            )
            self._pipeline.add_before(self._authz_mw)

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
        """Tool function is invoked when no authorization middleware blocks it."""

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
    async def test_authorization_granted_with_correct_role(self, mock_app_with_authz):
        """User with required role is authorized."""

        @require_role("admin")
        async def admin_tool() -> dict:
            return {"status": "ok"}

        mock_app_with_authz._tool_functions["admin_tool"] = admin_tool
        mock_app_with_authz._authz_mw._tool_functions = mock_app_with_authz._tool_functions

        client = CeramicTestClient(
            mock_app_with_authz, email="admin@example.com", roles=["admin"]
        )

        result = await client.call_tool("admin_tool")
        assert result == {"status": "ok"}

    @pytest.mark.asyncio
    async def test_authorization_denied_without_role(self, mock_app_with_authz):
        """User without required role is denied."""

        @require_role("admin")
        async def admin_tool() -> dict:
            return {"status": "ok"}

        mock_app_with_authz._tool_functions["admin_tool"] = admin_tool
        mock_app_with_authz._authz_mw._tool_functions = mock_app_with_authz._tool_functions

        client = CeramicTestClient(
            mock_app_with_authz, email="user@example.com", roles=["viewer"]
        )

        result = await client.call_tool("admin_tool")
        assert result["error"] == "authorization_denied"

    @pytest.mark.asyncio
    async def test_authorization_granted_with_correct_group(self, mock_app_with_authz):
        """User in required group is authorized."""

        @require_group("ops-team")
        async def deploy_tool() -> dict:
            return {"deployed": True}

        mock_app_with_authz._tool_functions["deploy_tool"] = deploy_tool
        mock_app_with_authz._authz_mw._tool_functions = mock_app_with_authz._tool_functions

        client = CeramicTestClient(
            mock_app_with_authz, email="dev@example.com", groups=["ops-team"]
        )

        result = await client.call_tool("deploy_tool")
        assert result == {"deployed": True}

    @pytest.mark.asyncio
    async def test_authorization_denied_without_group(self, mock_app_with_authz):
        """User not in required group is denied."""

        @require_group("ops-team")
        async def deploy_tool() -> dict:
            return {"deployed": True}

        mock_app_with_authz._tool_functions["deploy_tool"] = deploy_tool
        mock_app_with_authz._authz_mw._tool_functions = mock_app_with_authz._tool_functions

        client = CeramicTestClient(
            mock_app_with_authz, email="dev@example.com", groups=["dev-team"]
        )

        result = await client.call_tool("deploy_tool")
        assert result["error"] == "authorization_denied"

    @pytest.mark.asyncio
    async def test_multiple_policies_and_semantics(self, mock_app_with_authz):
        """All policies must pass (AND semantics)."""

        @require_role("admin")
        @require_group("ops-team")
        async def critical_tool() -> dict:
            return {"critical": True}

        mock_app_with_authz._tool_functions["critical_tool"] = critical_tool
        mock_app_with_authz._authz_mw._tool_functions = mock_app_with_authz._tool_functions

        # Has role but not group
        client = CeramicTestClient(
            mock_app_with_authz, roles=["admin"], groups=["dev-team"]
        )
        result = await client.call_tool("critical_tool")
        assert result["error"] == "authorization_denied"

        # Has both
        client_ok = CeramicTestClient(
            mock_app_with_authz, roles=["admin"], groups=["ops-team"]
        )
        result_ok = await client_ok.call_tool("critical_tool")
        assert result_ok == {"critical": True}

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
        client = CeramicTestClient(
            mock_app, email="test@example.com", roles=["tester"]
        )

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

    def test_assert_authorized_passes_for_normal_response(self):
        """assert_authorized passes for a non-error response."""
        CeramicTestClient.assert_authorized({"result": "success"})

    def test_assert_authorized_passes_for_non_dict(self):
        """assert_authorized passes for non-dict responses."""
        CeramicTestClient.assert_authorized("hello")
        CeramicTestClient.assert_authorized(42)
        CeramicTestClient.assert_authorized(None)

    def test_assert_authorized_fails_for_authorization_denied(self):
        """assert_authorized raises AssertionError for authorization_denied."""
        with pytest.raises(AssertionError, match="authorization_denied"):
            CeramicTestClient.assert_authorized(
                {"error": "authorization_denied", "message": "Insufficient permissions"}
            )

    def test_assert_authorized_passes_for_other_errors(self):
        """assert_authorized passes for non-authorization errors."""
        CeramicTestClient.assert_authorized({"error": "internal_error"})

    def test_assert_unauthorized_passes_for_authorization_denied(self):
        """assert_unauthorized passes for authorization_denied."""
        CeramicTestClient.assert_unauthorized(
            {"error": "authorization_denied", "message": "Insufficient permissions"}
        )

    def test_assert_unauthorized_fails_for_normal_response(self):
        """assert_unauthorized raises AssertionError for normal responses."""
        with pytest.raises(AssertionError, match="Expected authorization_denied"):
            CeramicTestClient.assert_unauthorized({"result": "success"})

    def test_assert_unauthorized_fails_for_non_dict(self):
        """assert_unauthorized raises AssertionError for non-dict responses."""
        with pytest.raises(AssertionError):
            CeramicTestClient.assert_unauthorized("hello")

    def test_assert_unauthorized_fails_for_other_errors(self):
        """assert_unauthorized raises AssertionError for non-authorization errors."""
        with pytest.raises(AssertionError):
            CeramicTestClient.assert_unauthorized({"error": "internal_error"})


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
        now = int(time.time())
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
