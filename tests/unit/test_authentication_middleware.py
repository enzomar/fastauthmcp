"""Unit tests for AuthenticationMiddleware with mocked OAuthService and TokenStorage."""

from __future__ import annotations

import base64
import json
from datetime import datetime, timedelta, timezone
from types import MappingProxyType
from unittest.mock import AsyncMock

import pytest

from fastauthmcp.auth.claims import (
    build_identity_context,
    extract_nested_claim,
    parse_jwt_claims,
)
from fastauthmcp.auth.oauth import AuthResult, OAuthService
from fastauthmcp.config import AuthConfig
from fastauthmcp.exceptions import AuthenticationError, ProviderError
from fastauthmcp.identity import _identity_context_var
from fastauthmcp.middleware.authentication import (
    AuthenticationMiddleware,
    _derive_storage_key,
)
from fastauthmcp.middleware.pipeline import RequestContext
from fastauthmcp.models import TokenSet

# --- Helpers ---


def _make_jwt(claims: dict) -> str:
    """Create a structurally valid JWT (unsigned) with given claims."""
    header = (
        base64.urlsafe_b64encode(json.dumps({"alg": "none", "typ": "JWT"}).encode())
        .rstrip(b"=")
        .decode()
    )
    payload = base64.urlsafe_b64encode(json.dumps(claims).encode()).rstrip(b"=").decode()
    signature = ""
    return f"{header}.{payload}.{signature}"


def _make_token_set(
    *,
    expired: bool = False,
    claims: dict | None = None,
    refresh_token: str | None = "refresh-token",
) -> TokenSet:
    """Create a TokenSet with a valid or expired access token."""
    if claims is None:
        claims = {
            "sub": "user-123",
            "email": "user@example.com",
            "realm_access": {"roles": ["admin", "user"]},
            "groups": ["engineering", "ops"],
        }
    access_token = _make_jwt(claims)

    if expired:
        expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    else:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    return TokenSet(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=expires_at,
        token_type="Bearer",
    )


# --- Fixtures ---


@pytest.fixture
def auth_config():
    """Create a sample AuthConfig for testing."""
    return AuthConfig(
        provider="oidc",
        issuer="https://idp.example.com",
        client_id="test-client",
        scopes=["openid", "profile", "email"],
    )


@pytest.fixture
def mock_token_storage():
    """Create a mock TokenStorage."""
    storage = AsyncMock()
    storage.retrieve = AsyncMock(return_value=None)
    storage.store = AsyncMock()
    storage.delete = AsyncMock()
    return storage


@pytest.fixture
def mock_oauth_service():
    """Create a mock OAuthService."""
    service = AsyncMock(spec=OAuthService)
    return service


@pytest.fixture
def middleware(auth_config, mock_token_storage, mock_oauth_service):
    """Create an AuthenticationMiddleware with mocked dependencies."""
    return AuthenticationMiddleware(
        auth_config=auth_config,
        token_storage=mock_token_storage,
        oauth_service=mock_oauth_service,
    )


@pytest.fixture
def request_ctx():
    """Create a fresh RequestContext."""
    return RequestContext()


@pytest.fixture
def next_fn():
    """Create a mock next function that returns a success response."""
    mock_next = AsyncMock(return_value={"result": "success"})
    return mock_next


# --- JWT Parsing Tests ---


class TestParseJwtClaims:
    """Tests for parse_jwt_claims helper."""

    def test_parses_valid_jwt(self):
        """Should parse claims from a valid JWT."""
        claims = {"sub": "user-123", "email": "test@example.com", "iat": 1234567890}
        token = _make_jwt(claims)
        result = parse_jwt_claims(token)
        assert result["sub"] == "user-123"
        assert result["email"] == "test@example.com"

    def test_rejects_malformed_jwt(self):
        """Should raise ValueError for non-JWT strings."""
        with pytest.raises(ValueError, match="Failed to decode JWT"):
            parse_jwt_claims("not-a-jwt")

    def test_rejects_two_segment_jwt(self):
        """Should raise ValueError for JWTs with wrong number of segments."""
        with pytest.raises(ValueError, match="Failed to decode JWT"):
            parse_jwt_claims("header.payload")

    def test_handles_padding(self):
        """Should handle base64url payloads that need padding."""
        # Short payload that needs padding
        claims = {"a": "b"}
        token = _make_jwt(claims)
        result = parse_jwt_claims(token)
        assert result["a"] == "b"


# --- Nested Claim Extraction Tests ---


class TestExtractNestedClaim:
    """Tests for extract_nested_claim helper."""

    def test_extracts_simple_list(self):
        """Should extract a list from a top-level key."""
        claims = {"groups": ["eng", "ops"]}
        result = extract_nested_claim(claims, "groups")
        assert result == ["eng", "ops"]

    def test_extracts_nested_list(self):
        """Should extract a list from a nested path."""
        claims = {"realm_access": {"roles": ["admin", "user"]}}
        result = extract_nested_claim(claims, "realm_access.roles")
        assert result == ["admin", "user"]

    def test_returns_empty_on_missing_key(self):
        """Should return empty list when path doesn't exist."""
        claims = {"other": "value"}
        result = extract_nested_claim(claims, "realm_access.roles")
        assert result == []

    def test_returns_empty_on_none_intermediate(self):
        """Should return empty list when intermediate value is None."""
        claims = {"realm_access": None}
        result = extract_nested_claim(claims, "realm_access.roles")
        assert result == []

    def test_handles_string_value(self):
        """Should wrap a single string value in a list."""
        claims = {"role": "admin"}
        result = extract_nested_claim(claims, "role")
        assert result == ["admin"]


# --- Build Identity Context Tests ---


class TestBuildIdentityContext:
    """Tests for build_identity_context helper."""

    def test_builds_complete_identity(self):
        """Should create IdentityContext with all fields populated."""
        claims = {
            "sub": "user-123",
            "email": "user@example.com",
            "realm_access": {"roles": ["admin"]},
            "groups": ["engineering"],
        }
        identity = build_identity_context(claims)
        assert identity.email == "user@example.com"
        assert identity.subject == "user-123"
        assert identity.roles == frozenset(["admin"])
        assert identity.groups == frozenset(["engineering"])
        assert isinstance(identity.claims, MappingProxyType)
        assert identity.claims["sub"] == "user-123"

    def test_handles_missing_email(self):
        """Should set email to None when claim is absent."""
        claims = {"sub": "user-123"}
        identity = build_identity_context(claims)
        assert identity.email is None

    def test_handles_missing_subject(self):
        """Should set subject to None when claim is absent."""
        claims = {"email": "user@example.com"}
        identity = build_identity_context(claims)
        assert identity.subject is None

    def test_custom_claim_paths(self):
        """Should support custom role and group claim paths."""
        claims = {
            "custom": {"user_roles": ["viewer"]},
            "org": {"teams": ["platform"]},
        }
        identity = build_identity_context(
            claims,
            role_claim_path="custom.user_roles",
            group_claim_path="org.teams",
        )
        assert identity.roles == frozenset(["viewer"])
        assert identity.groups == frozenset(["platform"])

    def test_claims_immutable(self):
        """Claims should be wrapped in MappingProxyType (immutable)."""
        claims = {"sub": "user-123"}
        identity = build_identity_context(claims)
        with pytest.raises(TypeError):
            identity.claims["new_key"] = "value"  # type: ignore[index]


# --- Storage Key Derivation Tests ---


class TestDeriveStorageKey:
    """Tests for _derive_storage_key helper."""

    def test_derives_from_issuer_hostname(self, auth_config):
        """Should derive storage key from the issuer's hostname."""
        key = _derive_storage_key(auth_config)
        assert key == "idp.example.com"


# --- Middleware: Valid Token Tests ---


class TestMiddlewareValidToken:
    """Tests for when a valid (non-expired) token is in storage."""

    @pytest.mark.asyncio
    async def test_valid_token_populates_identity(
        self, middleware, mock_token_storage, request_ctx, next_fn
    ):
        """Should populate ctx.identity and call next when token is valid."""
        token_set = _make_token_set()
        mock_token_storage.retrieve.return_value = token_set

        result = await middleware(request_ctx, next_fn)

        assert result == {"result": "success"}
        next_fn.assert_awaited_once()
        assert request_ctx.identity is not None
        assert request_ctx.identity.email == "user@example.com"
        assert request_ctx.identity.subject == "user-123"

    @pytest.mark.asyncio
    async def test_valid_token_sets_contextvar(
        self, middleware, mock_token_storage, request_ctx, next_fn
    ):
        """Should set the _identity_context_var contextvar."""
        token_set = _make_token_set()
        mock_token_storage.retrieve.return_value = token_set

        await middleware(request_ctx, next_fn)

        # The contextvar should be set
        identity = _identity_context_var.get()
        assert identity.email == "user@example.com"

    @pytest.mark.asyncio
    async def test_valid_token_extracts_roles_and_groups(
        self, middleware, mock_token_storage, request_ctx, next_fn
    ):
        """Should extract roles and groups from JWT claims."""
        token_set = _make_token_set()
        mock_token_storage.retrieve.return_value = token_set

        await middleware(request_ctx, next_fn)

        assert request_ctx.identity.roles == frozenset(["admin", "user"])
        assert request_ctx.identity.groups == frozenset(["engineering", "ops"])


# --- Middleware: Expired Token with Refresh ---


class TestMiddlewareTokenRefresh:
    """Tests for when stored token is expired and refresh is attempted."""

    @pytest.mark.asyncio
    async def test_refresh_success_updates_storage(
        self, middleware, mock_token_storage, mock_oauth_service, request_ctx, next_fn
    ):
        """Should refresh token, update storage, and proceed."""
        expired_token = _make_token_set(expired=True)
        new_token = _make_token_set(expired=False)
        mock_token_storage.retrieve.return_value = expired_token
        mock_oauth_service.refresh_token.return_value = new_token

        result = await middleware(request_ctx, next_fn)

        assert result == {"result": "success"}
        mock_oauth_service.refresh_token.assert_awaited_once_with(refresh_token="refresh-token")
        mock_token_storage.store.assert_awaited_once()
        next_fn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_refresh_preserves_old_refresh_token_if_not_rotated(
        self, middleware, mock_token_storage, mock_oauth_service, request_ctx, next_fn
    ):
        """Should keep old refresh_token when provider doesn't rotate."""
        expired_token = _make_token_set(expired=True, refresh_token="old-refresh")
        # New token without refresh_token (provider didn't rotate)
        new_token = _make_token_set(expired=False, refresh_token=None)
        mock_token_storage.retrieve.return_value = expired_token
        mock_oauth_service.refresh_token.return_value = new_token

        await middleware(request_ctx, next_fn)

        # The stored token should have the old refresh token preserved
        stored_call = mock_token_storage.store.call_args
        stored_token_set = stored_call[0][1]
        assert stored_token_set.refresh_token == "old-refresh"

    @pytest.mark.asyncio
    async def test_refresh_failure_auth_error_invalidates(
        self, middleware, mock_token_storage, mock_oauth_service, request_ctx, next_fn
    ):
        """Should invalidate session and discard tokens on auth failure."""
        expired_token = _make_token_set(expired=True)
        mock_token_storage.retrieve.return_value = expired_token
        mock_oauth_service.refresh_token.side_effect = AuthenticationError("Token revoked")

        result = await middleware(request_ctx, next_fn)

        assert result["error"] == "authentication_failed"
        mock_token_storage.delete.assert_awaited_once()
        next_fn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_refresh_provider_error_preserves_tokens(
        self, middleware, mock_token_storage, mock_oauth_service, request_ctx, next_fn
    ):
        """Should preserve stored tokens on transient provider failures."""
        expired_token = _make_token_set(expired=True)
        mock_token_storage.retrieve.return_value = expired_token
        mock_oauth_service.refresh_token.side_effect = ProviderError("Connection refused")

        result = await middleware(request_ctx, next_fn)

        assert result["error"] == "provider_error"
        # Tokens should NOT be deleted on transient failures
        mock_token_storage.delete.assert_not_awaited()
        mock_token_storage.store.assert_not_awaited()
        next_fn.assert_not_awaited()


# --- Middleware: No Token — OAuth Flow ---


class TestMiddlewareOAuthFlow:
    """Tests for when no token is in storage and OAuth flow is initiated."""

    @pytest.mark.asyncio
    async def test_oauth_flow_success(
        self, middleware, mock_token_storage, mock_oauth_service, request_ctx, next_fn
    ):
        """Should initiate OAuth flow, store tokens, and proceed."""
        mock_token_storage.retrieve.return_value = None
        new_token = _make_token_set()
        mock_oauth_service.initiate_flow.return_value = AuthResult(
            code="auth-code",
            verifier="verifier-123",
            redirect_uri="http://localhost:1234/callback",
        )
        mock_oauth_service.exchange_code.return_value = new_token

        result = await middleware(request_ctx, next_fn)

        assert result == {"result": "success"}
        mock_oauth_service.initiate_flow.assert_awaited_once()
        mock_oauth_service.exchange_code.assert_awaited_once_with(
            code="auth-code",
            verifier="verifier-123",
            redirect_uri="http://localhost:1234/callback",
        )
        mock_token_storage.store.assert_awaited_once()
        next_fn.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_oauth_flow_populates_identity(
        self, middleware, mock_token_storage, mock_oauth_service, request_ctx, next_fn
    ):
        """Should populate identity after successful OAuth flow."""
        mock_token_storage.retrieve.return_value = None
        new_token = _make_token_set()
        mock_oauth_service.initiate_flow.return_value = AuthResult(
            code="auth-code",
            verifier="verifier",
            redirect_uri="http://localhost:1234/callback",
        )
        mock_oauth_service.exchange_code.return_value = new_token

        await middleware(request_ctx, next_fn)

        assert request_ctx.identity is not None
        assert request_ctx.identity.email == "user@example.com"

    @pytest.mark.asyncio
    async def test_oauth_flow_auth_error(
        self, middleware, mock_token_storage, mock_oauth_service, request_ctx, next_fn
    ):
        """Should return auth error when OAuth flow fails."""
        mock_token_storage.retrieve.return_value = None
        mock_oauth_service.initiate_flow.side_effect = AuthenticationError("Callback timed out")

        result = await middleware(request_ctx, next_fn)

        assert result["error"] == "authentication_required"
        assert "Callback timed out" in result["message"]
        next_fn.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_oauth_flow_provider_error_preserves_tokens(
        self, middleware, mock_token_storage, mock_oauth_service, request_ctx, next_fn
    ):
        """Should preserve stored tokens on provider error during OAuth flow."""
        mock_token_storage.retrieve.return_value = None
        mock_oauth_service.initiate_flow.side_effect = ProviderError("Provider unreachable")

        result = await middleware(request_ctx, next_fn)

        assert result["error"] == "provider_error"
        # Should not delete any tokens
        mock_token_storage.delete.assert_not_awaited()
        next_fn.assert_not_awaited()


# --- Middleware: Expired Token, No Refresh Token ---


class TestMiddlewareExpiredNoRefresh:
    """Tests for when token is expired but no refresh token is available."""

    @pytest.mark.asyncio
    async def test_expired_no_refresh_initiates_flow(
        self, middleware, mock_token_storage, mock_oauth_service, request_ctx, next_fn
    ):
        """Should delete old token and initiate OAuth flow when no refresh token."""
        expired_token = _make_token_set(expired=True, refresh_token=None)
        new_token = _make_token_set()
        mock_token_storage.retrieve.return_value = expired_token
        mock_oauth_service.initiate_flow.return_value = AuthResult(
            code="code",
            verifier="verifier",
            redirect_uri="http://localhost:1234/callback",
        )
        mock_oauth_service.exchange_code.return_value = new_token

        result = await middleware(request_ctx, next_fn)

        assert result == {"result": "success"}
        mock_token_storage.delete.assert_awaited_once()
        mock_oauth_service.initiate_flow.assert_awaited_once()


# --- Middleware: Builtin Wrapper ---


class TestBuiltinWrapper:
    """Tests that the builtin.py wrapper delegates correctly."""

    @pytest.mark.asyncio
    async def test_builtin_wrapper_delegates(self, auth_config):
        """The wrapper in builtin.py should delegate to the real implementation."""
        from fastauthmcp.middleware.builtin import (
            AuthenticationMiddleware as BuiltinAuth,
        )

        mw = BuiltinAuth(config=auth_config)
        assert mw._impl is not None
        assert isinstance(mw._impl, AuthenticationMiddleware)
