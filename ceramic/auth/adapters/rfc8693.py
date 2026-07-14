"""Standard OAuth 2.0 Token Exchange adapter (RFC 8693).

This is the default adapter that preserves the behavior of
OAuthService.token_exchange(). Works with any OIDC provider that
supports the standard RFC 8693 grant type.
"""

from __future__ import annotations

from ceramic.config import AuthConfig
from ceramic.models import OIDCEndpoints, TokenSet
from ceramic.resilience import ResilientHttpClient


class RFC8693Adapter:
    """Standard RFC 8693 token exchange adapter (default).

    Builds the standard token exchange request body and POSTs to the
    discovered token endpoint.
    """

    def __init__(self, http_client: ResilientHttpClient) -> None:
        self._http = http_client

    @property
    def provider_id(self) -> str:
        return "rfc8693"

    async def exchange(
        self,
        subject_token: str,
        config: AuthConfig,
        endpoints: OIDCEndpoints,
        *,
        audience: str | None = None,
        scope: str | None = None,
    ) -> TokenSet:
        """Exchange a subject token using standard RFC 8693 token exchange."""
        body: dict[str, str] = {
            "grant_type": "urn:ietf:params:oauth:grant-type:token-exchange",
            "client_id": config.client_id,
            "subject_token": subject_token,
            "subject_token_type": "urn:ietf:params:oauth:token-type:access_token",
            "requested_token_type": "urn:ietf:params:oauth:token-type:access_token",
        }
        if config.client_secret:
            body["client_secret"] = config.client_secret
        if audience or config.token_exchange_audience:
            body["audience"] = audience or config.token_exchange_audience or ""
        if scope or config.token_exchange_scope:
            body["scope"] = scope or config.token_exchange_scope or ""

        return await self._http.post_token(
            endpoints.token_endpoint, body, config.token_exchange_timeout
        )
