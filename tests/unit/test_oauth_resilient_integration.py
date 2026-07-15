"""Unit tests for OAuthService integration with ResilientHttpClient.

Verifies that when a ResilientHttpClient is provided to OAuthService,
all outbound HTTP (discover_endpoints, exchange_code, refresh_token,
client_credentials, token_exchange) routes through it instead of raw httpx.
Also verifies backward compatibility when http_client is None.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from fastauthmcp.auth.oauth import OAuthService
from fastauthmcp.config import AuthConfig
from fastauthmcp.exceptions import ProviderError
from fastauthmcp.models import OIDCEndpoints, TokenSet
from fastauthmcp.resilience import CircuitBreaker, ResilientHttpClient


# --- Fixtures ---


@pytest.fixture
def provider_config():
    return AuthConfig(
        provider="oidc",
        issuer="https://idp.example.com",
        client_id="test-client",
        client_secret="test-secret",
        scopes=["openid", "profile"],
        callback_timeout=120,
        token_exchange_timeout=30,
        token_exchange_audience="https://api.example.com",
        token_exchange_scope="downstream-scope",
    )


@pytest.fixture
def endpoints():
    return OIDCEndpoints(
        authorization_endpoint="https://idp.example.com/authorize",
        token_endpoint="https://idp.example.com/token",
        userinfo_endpoint="https://idp.example.com/userinfo",
        jwks_uri="https://idp.example.com/.well-known/jwks.json",
    )


@pytest.fixture
def token_set():
    return TokenSet(
        access_token="new-access-token",
        refresh_token="new-refresh-token",
        expires_at=datetime(2025, 1, 1, tzinfo=timezone.utc),
        token_type="Bearer",
        id_token="new-id-token",
    )


@pytest.fixture
def mock_http_client():
    """Create a ResilientHttpClient with mocked methods."""
    cb = CircuitBreaker(failure_threshold=5, cooldown_seconds=30)
    client = ResilientHttpClient(cb)
    # Mock all methods
    client.get = AsyncMock()
    client.post_form = AsyncMock()
    client.post_token = AsyncMock()
    return client


# --- discover_endpoints uses http_client.get ---


class TestDiscoverEndpointsWithHttpClient:
    @pytest.mark.asyncio
    async def test_uses_http_client_get(self, provider_config, mock_http_client):
        """When http_client is provided, discover_endpoints uses it for GET."""
        discovery_data = {
            "authorization_endpoint": "https://idp.example.com/authorize",
            "token_endpoint": "https://idp.example.com/token",
            "jwks_uri": "https://idp.example.com/.well-known/jwks.json",
            "userinfo_endpoint": "https://idp.example.com/userinfo",
        }
        mock_response = MagicMock()
        mock_response.json.return_value = discovery_data
        mock_http_client.get.return_value = mock_response

        service = OAuthService(
            provider_config=provider_config, http_client=mock_http_client
        )
        result = await service.discover_endpoints("https://idp.example.com")

        # Verify http_client.get was called with the discovery URL
        mock_http_client.get.assert_called_once_with(
            "https://idp.example.com/.well-known/openid-configuration",
            timeout=30,
            headers={"Accept": "application/json"},
        )
        assert result.token_endpoint == "https://idp.example.com/token"
        assert result.jwks_uri == "https://idp.example.com/.well-known/jwks.json"

    @pytest.mark.asyncio
    async def test_discovery_with_trailing_slash(
        self, provider_config, mock_http_client
    ):
        """Trailing slash on issuer is stripped before appending discovery path."""
        discovery_data = {
            "authorization_endpoint": "https://idp.example.com/authorize",
            "token_endpoint": "https://idp.example.com/token",
            "jwks_uri": "https://idp.example.com/.well-known/jwks.json",
        }
        mock_response = MagicMock()
        mock_response.json.return_value = discovery_data
        mock_http_client.get.return_value = mock_response

        service = OAuthService(
            provider_config=provider_config, http_client=mock_http_client
        )
        await service.discover_endpoints("https://idp.example.com/")

        mock_http_client.get.assert_called_once_with(
            "https://idp.example.com/.well-known/openid-configuration",
            timeout=30,
            headers={"Accept": "application/json"},
        )


# --- exchange_code uses http_client.post_token ---


class TestExchangeCodeWithHttpClient:
    @pytest.mark.asyncio
    async def test_uses_http_client_post_token(
        self, provider_config, mock_http_client, endpoints, token_set
    ):
        """exchange_code routes through _post_token_request → http_client.post_token."""
        mock_http_client.post_token.return_value = token_set

        service = OAuthService(
            provider_config=provider_config, http_client=mock_http_client
        )
        service._endpoints = endpoints

        result = await service.exchange_code(
            code="auth-code-123",
            verifier="test-verifier",
            redirect_uri="http://localhost:12345/callback",
        )

        assert result == token_set
        mock_http_client.post_token.assert_called_once()
        call_args = mock_http_client.post_token.call_args
        url = call_args[0][0]
        body = call_args[0][1]
        assert url == "https://idp.example.com/token"
        assert body["grant_type"] == "authorization_code"
        assert body["code"] == "auth-code-123"
        assert body["code_verifier"] == "test-verifier"
        assert body["client_id"] == "test-client"
        assert body["client_secret"] == "test-secret"

    @pytest.mark.asyncio
    async def test_exchange_code_http_error_raises_provider_error(
        self, provider_config, mock_http_client, endpoints
    ):
        """HTTPStatusError from http_client is wrapped in ProviderError."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Code expired",
        }
        mock_http_client.post_token.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=mock_resp
        )

        service = OAuthService(
            provider_config=provider_config, http_client=mock_http_client
        )
        service._endpoints = endpoints

        with pytest.raises(ProviderError, match="Code expired"):
            await service.exchange_code(
                code="bad-code",
                verifier="verifier",
                redirect_uri="http://localhost/callback",
            )


# --- refresh_token uses http_client.post_token ---


class TestRefreshTokenWithHttpClient:
    @pytest.mark.asyncio
    async def test_uses_http_client_post_token(
        self, provider_config, mock_http_client, endpoints, token_set
    ):
        """refresh_token routes through _post_token_request → http_client.post_token."""
        mock_http_client.post_token.return_value = token_set

        service = OAuthService(
            provider_config=provider_config, http_client=mock_http_client
        )
        service._endpoints = endpoints

        result = await service.refresh_token(refresh_token="old-refresh-token")

        assert result == token_set
        mock_http_client.post_token.assert_called_once()
        call_args = mock_http_client.post_token.call_args
        url = call_args[0][0]
        body = call_args[0][1]
        assert url == "https://idp.example.com/token"
        assert body["grant_type"] == "refresh_token"
        assert body["refresh_token"] == "old-refresh-token"
        assert body["client_id"] == "test-client"
        assert body["client_secret"] == "test-secret"


# --- client_credentials uses http_client.post_token ---


class TestClientCredentialsWithHttpClient:
    @pytest.mark.asyncio
    async def test_uses_http_client_post_token(
        self, provider_config, mock_http_client, endpoints, token_set
    ):
        """client_credentials routes through _post_token_request → http_client.post_token."""
        mock_http_client.post_token.return_value = token_set

        service = OAuthService(
            provider_config=provider_config, http_client=mock_http_client
        )
        service._endpoints = endpoints

        result = await service.client_credentials()

        assert result == token_set
        mock_http_client.post_token.assert_called_once()
        call_args = mock_http_client.post_token.call_args
        url = call_args[0][0]
        body = call_args[0][1]
        assert url == "https://idp.example.com/token"
        assert body["grant_type"] == "client_credentials"
        assert body["client_id"] == "test-client"
        assert body["client_secret"] == "test-secret"
        assert body["scope"] == "openid profile"

    @pytest.mark.asyncio
    async def test_client_credentials_discovers_endpoints_first(
        self, provider_config, mock_http_client, token_set
    ):
        """client_credentials discovers endpoints if not already cached."""
        discovery_data = {
            "authorization_endpoint": "https://idp.example.com/authorize",
            "token_endpoint": "https://idp.example.com/token",
            "jwks_uri": "https://idp.example.com/.well-known/jwks.json",
        }
        mock_response = MagicMock()
        mock_response.json.return_value = discovery_data
        mock_http_client.get.return_value = mock_response
        mock_http_client.post_token.return_value = token_set

        service = OAuthService(
            provider_config=provider_config, http_client=mock_http_client
        )

        result = await service.client_credentials()

        assert result == token_set
        # Verify discovery was performed via http_client.get
        mock_http_client.get.assert_called_once()
        # Then post_token was called
        mock_http_client.post_token.assert_called_once()


# --- token_exchange uses http_client.post_token via _post_token_request ---


class TestTokenExchangeWithHttpClient:
    @pytest.mark.asyncio
    async def test_uses_http_client_post_token(
        self, provider_config, mock_http_client, endpoints, token_set
    ):
        """token_exchange builds RFC 8693 body and posts through http_client."""
        mock_http_client.post_token.return_value = token_set

        service = OAuthService(
            provider_config=provider_config, http_client=mock_http_client
        )
        service._endpoints = endpoints

        result = await service.token_exchange(subject_token="upstream-user-token")

        assert result == token_set
        mock_http_client.post_token.assert_called_once()
        call_args = mock_http_client.post_token.call_args
        url = call_args[0][0]
        body = call_args[0][1]
        assert url == "https://idp.example.com/token"
        assert body["grant_type"] == "urn:ietf:params:oauth:grant-type:token-exchange"
        assert body["subject_token"] == "upstream-user-token"
        assert (
            body["subject_token_type"]
            == "urn:ietf:params:oauth:token-type:access_token"
        )
        assert (
            body["requested_token_type"]
            == "urn:ietf:params:oauth:token-type:access_token"
        )
        assert body["client_id"] == "test-client"
        assert body["client_secret"] == "test-secret"
        assert body["audience"] == "https://api.example.com"
        assert body["scope"] == "downstream-scope"

    @pytest.mark.asyncio
    async def test_token_exchange_connection_error_raises_provider_error(
        self, provider_config, mock_http_client, endpoints
    ):
        """RequestError from http_client is wrapped in ProviderError."""
        mock_http_client.post_token.side_effect = httpx.ConnectError(
            "Connection refused"
        )

        service = OAuthService(
            provider_config=provider_config, http_client=mock_http_client
        )
        service._endpoints = endpoints

        with pytest.raises(ProviderError, match="Failed to reach token endpoint"):
            await service.token_exchange(subject_token="user-token")


# --- Backward compatibility: None http_client falls back to raw httpx ---


class TestBackwardCompatibility:
    @pytest.mark.asyncio
    async def test_none_http_client_uses_raw_httpx(self, provider_config):
        """When http_client is None, OAuthService uses raw httpx.AsyncClient."""
        service = OAuthService(provider_config=provider_config, http_client=None)
        service._endpoints = OIDCEndpoints(
            authorization_endpoint="https://idp.example.com/authorize",
            token_endpoint="https://idp.example.com/token",
            userinfo_endpoint=None,
            jwks_uri="https://idp.example.com/.well-known/jwks.json",
        )

        token_data = {
            "access_token": "raw-httpx-token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = token_data
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.post = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "fastauthmcp.auth.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            result = await service.refresh_token(refresh_token="old-token")

        assert result.access_token == "raw-httpx-token"
        # Verify raw httpx was used
        mock_client.post.assert_called_once()

    @pytest.mark.asyncio
    async def test_none_http_client_discovery_uses_raw_httpx(self, provider_config):
        """When http_client is None, discover_endpoints uses raw httpx.AsyncClient."""
        service = OAuthService(provider_config=provider_config, http_client=None)

        discovery_data = {
            "authorization_endpoint": "https://idp.example.com/authorize",
            "token_endpoint": "https://idp.example.com/token",
            "jwks_uri": "https://idp.example.com/.well-known/jwks.json",
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = discovery_data
        mock_resp.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.get = AsyncMock(return_value=mock_resp)
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=None)

        with patch(
            "fastauthmcp.auth.oauth.httpx.AsyncClient", return_value=mock_client
        ):
            result = await service.discover_endpoints("https://idp.example.com")

        assert result.token_endpoint == "https://idp.example.com/token"
        mock_client.get.assert_called_once()
