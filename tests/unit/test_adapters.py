"""Consolidated adapter tests (~15 tests).

Covers: AdapterRegistry, RFC8693Adapter, GoogleSTSAdapter, EntraOBOAdapter.
"""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from fastauthmcp.auth.adapters import (
    AdapterRegistry,
    EntraOBOAdapter,
    GoogleSTSAdapter,
    RFC8693Adapter,
)
from fastauthmcp.config import AuthConfig
from fastauthmcp.exceptions import (
    AuthenticationError,
    ConfigurationError,
    ProviderError,
)
from fastauthmcp.models import OIDCEndpoints, TokenSet
from fastauthmcp.resilience import CircuitBreaker, ResilientHttpClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def http_client():
    cb = CircuitBreaker(failure_threshold=5, cooldown_seconds=30)
    return ResilientHttpClient(cb)


@pytest.fixture
def auth_config():
    return AuthConfig(
        issuer="https://idp.example.com",
        client_id="test-client",
        client_secret="test-secret",
        token_exchange_audience="https://api.example.com",
        token_exchange_scope="read write",
    )


@pytest.fixture
def auth_config_no_secret():
    return AuthConfig(issuer="https://idp.example.com", client_id="test-client")


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
        access_token="exchanged-access-token",
        refresh_token=None,
        expires_at=datetime(2025, 1, 1, 12, 0, 0, tzinfo=timezone.utc),
        token_type="Bearer",
        id_token=None,
    )


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------


class TestAdapterRegistry:
    def test_returns_rfc8693_for_none(self, http_client):
        """None provider_id returns the default RFC8693 adapter."""
        registry = AdapterRegistry(http_client)
        adapter = registry.get_adapter(None)
        assert adapter.provider_id == "rfc8693"

    def test_raises_configuration_error_for_unknown(self, http_client):
        """Unknown provider_id raises ConfigurationError listing available."""
        registry = AdapterRegistry(http_client)
        with pytest.raises(ConfigurationError) as exc_info:
            registry.get_adapter("unknown-provider")
        assert "unknown-provider" in str(exc_info.value)
        assert "rfc8693" in str(exc_info.value)


# ---------------------------------------------------------------------------
# RFC8693 body keys/values
# ---------------------------------------------------------------------------


class TestRFC8693Adapter:
    async def test_body_keys(self, http_client, auth_config, endpoints, token_set):
        """RFC8693 adapter builds the standard token-exchange body."""
        http_client.post_token = AsyncMock(return_value=token_set)

        adapter = RFC8693Adapter(http_client)
        await adapter.exchange("user-token", auth_config, endpoints)

        body = http_client.post_token.call_args[0][1]
        assert body["grant_type"] == "urn:ietf:params:oauth:grant-type:token-exchange"
        assert body["subject_token"] == "user-token"
        assert (
            body["subject_token_type"]
            == "urn:ietf:params:oauth:token-type:access_token"
        )
        assert body["client_id"] == "test-client"
        assert body["client_secret"] == "test-secret"
        assert body["audience"] == "https://api.example.com"
        assert body["scope"] == "read write"

    async def test_omits_optional_fields_when_unset(
        self, http_client, auth_config_no_secret, endpoints, token_set
    ):
        """Optional fields (secret, audience, scope) are omitted when not configured."""
        http_client.post_token = AsyncMock(return_value=token_set)

        adapter = RFC8693Adapter(http_client)
        await adapter.exchange("user-token", auth_config_no_secret, endpoints)

        body = http_client.post_token.call_args[0][1]
        assert "client_secret" not in body
        assert "audience" not in body
        assert "scope" not in body

    async def test_error_handling(self, http_client, auth_config, endpoints):
        """ProviderError raised on HTTP error."""
        exc = httpx.HTTPStatusError(
            "Error",
            request=MagicMock(),
            response=MagicMock(status_code=500),
        )
        http_client.post_token = AsyncMock(side_effect=exc)

        adapter = RFC8693Adapter(http_client)
        with pytest.raises(httpx.HTTPStatusError):
            await adapter.exchange("user-token", auth_config, endpoints)


# ---------------------------------------------------------------------------
# Google STS body keys/values (camelCase)
# ---------------------------------------------------------------------------


class TestGoogleSTSAdapter:
    async def test_camelcase_body(self, http_client, auth_config, endpoints):
        """Google adapter uses camelCase parameter names and fixed URL."""
        mock_resp = MagicMock()
        mock_resp.json.return_value = {
            "access_token": "google-token",
            "expires_in": 3600,
            "token_type": "Bearer",
        }
        http_client.post_form = AsyncMock(return_value=mock_resp)

        adapter = GoogleSTSAdapter(http_client)
        result = await adapter.exchange("user-token", auth_config, endpoints)

        url = http_client.post_form.call_args[0][0]
        body = http_client.post_form.call_args[0][1]

        assert url == "https://sts.googleapis.com/v1/token"
        assert body["grantType"] == "urn:ietf:params:oauth:grant-type:token-exchange"
        assert body["subjectToken"] == "user-token"
        assert (
            body["subjectTokenType"] == "urn:ietf:params:oauth:token-type:access_token"
        )
        assert (
            body["requestedTokenType"]
            == "urn:ietf:params:oauth:token-type:access_token"
        )
        assert body["audience"] == "https://api.example.com"
        assert body["scope"] == "read write"
        assert result.access_token == "google-token"

    async def test_error_handling(self, http_client, auth_config, endpoints):
        """ProviderError raised with error_description on HTTP error."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "Token has been revoked",
        }
        exc = httpx.HTTPStatusError(
            "Bad Request", request=MagicMock(), response=mock_response
        )
        http_client.post_form = AsyncMock(side_effect=exc)

        adapter = GoogleSTSAdapter(http_client)
        with pytest.raises(ProviderError) as exc_info:
            await adapter.exchange("user-token", auth_config, endpoints)
        assert "Token has been revoked" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Entra OBO body keys/values (jwt-bearer)
# ---------------------------------------------------------------------------


class TestEntraOBOAdapter:
    async def test_jwt_bearer_body(self, http_client, auth_config, endpoints):
        """Entra adapter uses jwt-bearer grant, assertion=subject_token, OBO params."""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "entra-downstream",
            "refresh_token": "entra-refresh",
            "token_type": "Bearer",
            "id_token": "entra-id",
            "expires_in": 3600,
        }

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client.__aexit__ = AsyncMock(return_value=False)
            mock_client.post = AsyncMock(return_value=mock_response)
            mock_client_cls.return_value = mock_client

            adapter = EntraOBOAdapter(http_client)
            result = await adapter.exchange("user-token", auth_config, endpoints)

            posted_data = mock_client.post.call_args[1]["data"]
            assert (
                posted_data["grant_type"]
                == "urn:ietf:params:oauth:grant-type:jwt-bearer"
            )
            assert posted_data["assertion"] == "user-token"
            assert posted_data["requested_token_use"] == "on_behalf_of"
            assert posted_data["client_id"] == "test-client"
            assert posted_data["client_secret"] == "test-secret"
            assert result.access_token == "entra-downstream"
            assert result.refresh_token == "entra-refresh"

    async def test_error_handling(self, http_client, auth_config, endpoints):
        """ProviderError raised with error_description from response."""
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.json.return_value = {
            "error": "invalid_grant",
            "error_description": "AADSTS65001: User has not consented.",
        }
        http_client._cb.execute = AsyncMock(return_value=mock_response)

        adapter = EntraOBOAdapter(http_client)
        with pytest.raises(ProviderError) as exc_info:
            await adapter.exchange("user-token", auth_config, endpoints)
        assert "AADSTS65001" in str(exc_info.value)

    async def test_raises_authentication_error_without_secret(
        self, http_client, auth_config_no_secret, endpoints
    ):
        """AuthenticationError raised when client_secret is missing."""
        adapter = EntraOBOAdapter(http_client)
        with pytest.raises(AuthenticationError) as exc_info:
            await adapter.exchange("user-token", auth_config_no_secret, endpoints)
        assert "client_secret" in str(exc_info.value)
