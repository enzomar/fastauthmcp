"""Microsoft Entra ID On-Behalf-Of flow adapter.

Exchanges an incoming user token for a downstream token using
Entra ID's OBO flow. Uses the discovered OIDC token endpoint
and requires client_secret to be configured.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from fastauthmcp.config import AuthConfig
from fastauthmcp.exceptions import AuthenticationError, ProviderError
from fastauthmcp.models import OIDCEndpoints, TokenSet
from fastauthmcp.resilience import ResilientHttpClient


class EntraOBOAdapter:
    """Microsoft Entra ID On-Behalf-Of token exchange adapter.

    Wire format:
        - grant_type: urn:ietf:params:oauth:grant-type:jwt-bearer
        - assertion: the subject token (incoming user token)
        - requested_token_use: on_behalf_of
        - client_id, client_secret from config
        - scope from arg or config.token_exchange_scope
    """

    def __init__(self, http_client: ResilientHttpClient) -> None:
        self._http = http_client

    @property
    def provider_id(self) -> str:
        return "entra"

    async def exchange(
        self,
        subject_token: str,
        config: AuthConfig,
        endpoints: OIDCEndpoints,
        *,
        audience: str | None = None,
        scope: str | None = None,
    ) -> TokenSet:
        """Exchange a subject token using Entra ID On-Behalf-Of flow.

        Raises:
            AuthenticationError: If client_secret is not configured.
            ProviderError: If the Entra token endpoint returns an HTTP error.
        """
        if not config.client_secret:
            raise AuthenticationError("Entra on-behalf-of flow requires client_secret")

        body: dict[str, str] = {
            "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
            "client_id": config.client_id,
            "client_secret": config.client_secret,
            "assertion": subject_token,
            "requested_token_use": "on_behalf_of",
        }
        effective_scope = scope or config.token_exchange_scope
        if effective_scope:
            body["scope"] = effective_scope

        timeout = config.token_exchange_timeout

        try:
            resp = await self._http.post_form(endpoints.token_endpoint, body, timeout=timeout)
        except httpx.HTTPStatusError as exc:
            try:
                error_data = exc.response.json()
                error_msg = error_data.get("error_description", error_data.get("error", ""))
            except Exception:
                error_msg = f"HTTP {exc.response.status_code}"
            raise ProviderError(error_msg) from exc

        try:
            data = resp.json()
        except Exception:
            raise ProviderError(f"Entra OBO: unparseable response (HTTP {resp.status_code})")

        if "access_token" not in data:
            error_msg = data.get("error_description", data.get("error", "unknown error"))
            raise ProviderError(f"Entra OBO exchange failed: {error_msg}")

        expires_in = int(data.get("expires_in", 3600))
        expires_at = datetime.now(timezone.utc).replace(microsecond=0) + timedelta(
            seconds=expires_in
        )

        return TokenSet(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_at=expires_at,
            token_type=data.get("token_type", "Bearer"),
            id_token=data.get("id_token"),
        )
