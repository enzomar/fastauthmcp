"""Unit tests for OAuthService with mocked httpx."""

from __future__ import annotations

import base64
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from fastauthmcp.auth.callback_server import CallbackServer
from fastauthmcp.auth.oauth import (
    OAuthService,
    _generate_code_challenge,
    _generate_code_verifier,
    _parse_token_response,
)
from fastauthmcp.config import AuthConfig
from fastauthmcp.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ProviderError,
)
from fastauthmcp.models import OIDCEndpoints, TokenSet


# --- Fixtures ---


@pytest.fixture
def provider_config():
    return AuthConfig(
        provider="oidc",
        issuer="https://idp.example.com",
        client_id="test-client",
        client_secret=None,
        scopes=["openid", "profile", "email"],
        callback_timeout=120,
        token_exchange_timeout=30,
    )


@pytest.fixture
def oauth_service(provider_config):
    return OAuthService(provider_config=provider_config)


@pytest.fixture
def discovery_response():
    return {
        "issuer": "https://idp.example.com",
        "authorization_endpoint": "https://idp.example.com/authorize",
        "token_endpoint": "https://idp.example.com/token",
        "userinfo_endpoint": "https://idp.example.com/userinfo",
        "jwks_uri": "https://idp.example.com/.well-known/jwks.json",
    }


@pytest.fixture
def token_response():
    return {
        "access_token": "eyJhbGciOiJSUzI1NiJ9.test-access",
        "refresh_token": "test-refresh-token",
        "expires_in": 3600,
        "token_type": "Bearer",
        "id_token": "test-id-token",
    }


def _mock_httpx_response(json_data: dict, status_code: int = 200) -> MagicMock:
    """Create a mock httpx.Response."""
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


def _mock_async_client(response: MagicMock) -> AsyncMock:
    """Create a mock httpx.AsyncClient context manager."""
    client = AsyncMock()
    client.get = AsyncMock(return_value=response)
    client.post = AsyncMock(return_value=response)
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=None)
    return client


# --- PKCE Tests ---


class TestPKCE:
    def test_code_verifier_length(self):
        verifier = _generate_code_verifier()
        assert 43 <= len(verifier) <= 128

    def test_code_verifier_is_url_safe(self):
        verifier = _generate_code_verifier()
        allowed = set(
            "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
        )
        assert all(c in allowed for c in verifier)

    def test_code_verifier_uniqueness(self):
        verifiers = {_generate_code_verifier() for _ in range(100)}
        assert len(verifiers) == 100

    def test_code_challenge_is_s256(self):
        verifier = "test-verifier-value-for-challenge"
        challenge = _generate_code_challenge(verifier)
        digest = hashlib.sha256(verifier.encode("ascii")).digest()
        expected = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
        assert challenge == expected

    def test_code_challenge_no_padding(self):
        verifier = _generate_code_verifier()
        challenge = _generate_code_challenge(verifier)
        assert "=" not in challenge


# --- OIDC Discovery Tests ---


class TestDiscoverEndpoints:
    @pytest.mark.asyncio
    async def test_successful_discovery(self, oauth_service, discovery_response):
        mock_resp = _mock_httpx_response(discovery_response)
        mock_client = _mock_async_client(mock_resp)

        with patch(
            "fastauthmcp.auth.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            endpoints = await oauth_service.discover_endpoints(
                "https://idp.example.com"
            )

        assert endpoints.authorization_endpoint == "https://idp.example.com/authorize"
        assert endpoints.token_endpoint == "https://idp.example.com/token"
        assert endpoints.userinfo_endpoint == "https://idp.example.com/userinfo"
        assert endpoints.jwks_uri == "https://idp.example.com/.well-known/jwks.json"

    @pytest.mark.asyncio
    async def test_discovery_caches_endpoints(self, oauth_service, discovery_response):
        mock_resp = _mock_httpx_response(discovery_response)
        mock_client = _mock_async_client(mock_resp)

        with patch(
            "fastauthmcp.auth.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            await oauth_service.discover_endpoints("https://idp.example.com")

        assert oauth_service._endpoints is not None
        assert (
            oauth_service._endpoints.token_endpoint == "https://idp.example.com/token"
        )

    @pytest.mark.asyncio
    async def test_discovery_rejects_http_issuer(self, oauth_service):
        with pytest.raises(ConfigurationError, match="Non-TLS endpoint"):
            await oauth_service.discover_endpoints("http://insecure.example.com")

    @pytest.mark.asyncio
    async def test_discovery_rejects_http_endpoints(self, oauth_service):
        insecure_response = {
            "authorization_endpoint": "http://idp.example.com/authorize",
            "token_endpoint": "https://idp.example.com/token",
            "jwks_uri": "https://idp.example.com/.well-known/jwks.json",
        }
        mock_resp = _mock_httpx_response(insecure_response)
        mock_client = _mock_async_client(mock_resp)

        with patch(
            "fastauthmcp.auth.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            with pytest.raises(ConfigurationError, match="Non-TLS endpoint"):
                await oauth_service.discover_endpoints("https://idp.example.com")

    @pytest.mark.asyncio
    async def test_discovery_provider_unreachable(self, oauth_service):
        mock_client = AsyncMock()
        mock_client.get = AsyncMock(
            side_effect=httpx.ConnectError("Connection refused")
        )
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "fastauthmcp.auth.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            with pytest.raises(ProviderError, match="Failed to fetch OIDC discovery"):
                await oauth_service.discover_endpoints("https://idp.example.com")

    @pytest.mark.asyncio
    async def test_discovery_missing_required_fields(self, oauth_service):
        incomplete = {"authorization_endpoint": "https://idp.example.com/authorize"}
        mock_resp = _mock_httpx_response(incomplete)
        mock_client = _mock_async_client(mock_resp)

        with patch(
            "fastauthmcp.auth.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            with pytest.raises(ProviderError, match="missing required fields"):
                await oauth_service.discover_endpoints("https://idp.example.com")


# --- Token Exchange Tests ---


class TestExchangeCode:
    @pytest.mark.asyncio
    async def test_successful_exchange(self, oauth_service, token_response):
        oauth_service._endpoints = OIDCEndpoints(
            authorization_endpoint="https://idp.example.com/authorize",
            token_endpoint="https://idp.example.com/token",
            userinfo_endpoint=None,
            jwks_uri="https://idp.example.com/.well-known/jwks.json",
        )

        mock_resp = _mock_httpx_response(token_response)
        mock_client = _mock_async_client(mock_resp)

        with patch(
            "fastauthmcp.auth.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            token_set = await oauth_service.exchange_code(
                code="auth-code-123",
                verifier="test-verifier",
                redirect_uri="http://localhost:12345/callback",
            )

        assert isinstance(token_set, TokenSet)
        assert token_set.access_token == "eyJhbGciOiJSUzI1NiJ9.test-access"
        assert token_set.refresh_token == "test-refresh-token"
        assert token_set.token_type == "Bearer"
        assert token_set.id_token == "test-id-token"

        # Verify the POST body contained PKCE verifier
        call_kwargs = mock_client.post.call_args
        body = call_kwargs.kwargs.get("data", {})
        assert body["code_verifier"] == "test-verifier"
        assert body["grant_type"] == "authorization_code"

    @pytest.mark.asyncio
    async def test_exchange_includes_client_secret(
        self, provider_config, token_response
    ):
        config_with_secret = provider_config.model_copy(
            update={"client_secret": "my-secret"}
        )
        service = OAuthService(provider_config=config_with_secret)
        service._endpoints = OIDCEndpoints(
            authorization_endpoint="https://idp.example.com/authorize",
            token_endpoint="https://idp.example.com/token",
            userinfo_endpoint=None,
            jwks_uri="https://idp.example.com/.well-known/jwks.json",
        )

        mock_resp = _mock_httpx_response(token_response)
        mock_client = _mock_async_client(mock_resp)

        with patch(
            "fastauthmcp.auth.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            await service.exchange_code(
                code="auth-code",
                verifier="verifier",
                redirect_uri="http://localhost:1234/callback",
            )

        body = mock_client.post.call_args.kwargs.get("data", {})
        assert body["client_secret"] == "my-secret"

    @pytest.mark.asyncio
    async def test_exchange_without_endpoints_raises(self, oauth_service):
        with pytest.raises(AuthenticationError, match="not discovered"):
            await oauth_service.exchange_code(code="code", verifier="verifier")

    @pytest.mark.asyncio
    async def test_exchange_provider_error(self, oauth_service):
        oauth_service._endpoints = OIDCEndpoints(
            authorization_endpoint="https://idp.example.com/authorize",
            token_endpoint="https://idp.example.com/token",
            userinfo_endpoint=None,
            jwks_uri="https://idp.example.com/.well-known/jwks.json",
        )

        error_resp = _mock_httpx_response(
            {"error": "invalid_grant", "error_description": "Code expired"},
            status_code=400,
        )
        mock_client = _mock_async_client(error_resp)

        with patch(
            "fastauthmcp.auth.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            with pytest.raises(ProviderError, match="Code expired"):
                await oauth_service.exchange_code(
                    code="bad-code",
                    verifier="verifier",
                    redirect_uri="http://localhost/callback",
                )


# --- Token Refresh Tests ---


class TestRefreshToken:
    @pytest.mark.asyncio
    async def test_successful_refresh(self, oauth_service, token_response):
        oauth_service._endpoints = OIDCEndpoints(
            authorization_endpoint="https://idp.example.com/authorize",
            token_endpoint="https://idp.example.com/token",
            userinfo_endpoint=None,
            jwks_uri="https://idp.example.com/.well-known/jwks.json",
        )

        mock_resp = _mock_httpx_response(token_response)
        mock_client = _mock_async_client(mock_resp)

        with patch(
            "fastauthmcp.auth.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            token_set = await oauth_service.refresh_token(
                refresh_token="old-refresh-token"
            )

        assert isinstance(token_set, TokenSet)
        assert token_set.access_token == "eyJhbGciOiJSUzI1NiJ9.test-access"

        body = mock_client.post.call_args.kwargs.get("data", {})
        assert body["grant_type"] == "refresh_token"
        assert body["refresh_token"] == "old-refresh-token"

    @pytest.mark.asyncio
    async def test_refresh_without_endpoints_raises(self, oauth_service):
        with pytest.raises(AuthenticationError, match="not discovered"):
            await oauth_service.refresh_token(refresh_token="some-token")


# --- Token Response Parsing ---


class TestParseTokenResponse:
    def test_valid_response(self, token_response):
        token_set = _parse_token_response(token_response)
        assert token_set.access_token == "eyJhbGciOiJSUzI1NiJ9.test-access"
        assert token_set.refresh_token == "test-refresh-token"
        assert token_set.token_type == "Bearer"

    def test_missing_access_token(self):
        with pytest.raises(ProviderError, match="missing 'access_token'"):
            _parse_token_response({"token_type": "Bearer"})

    def test_defaults(self):
        token_set = _parse_token_response({"access_token": "tok"})
        assert token_set.token_type == "Bearer"
        assert token_set.refresh_token is None


# --- Callback Server ---


class TestCallbackServer:
    def test_starts_on_random_port(self):
        server = CallbackServer()
        port = server.start(0)
        assert port > 0
        server.shutdown()

    def test_starts_on_specific_port(self):
        server = CallbackServer()
        port = server.start(19876)
        assert port == 19876
        server.shutdown()

    def test_timeout_raises(self):
        server = CallbackServer()
        server.start(0)
        with pytest.raises(TimeoutError):
            server.wait_for_callback(timeout=0.2)
        server.shutdown()
