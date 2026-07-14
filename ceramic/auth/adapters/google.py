"""Google Cloud Security Token Service adapter.

Exchanges tokens via Google's STS endpoint using camelCase parameter
names as required by the Google STS API. Always POSTs to the fixed
Google STS URL regardless of discovered OIDC endpoints.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx

from ceramic.config import AuthConfig
from ceramic.exceptions import ProviderError
from ceramic.models import OIDCEndpoints, TokenSet
from ceramic.resilience import ResilientHttpClient


class GoogleSTSAdapter:
    """Google Cloud STS token exchange adapter.

    Uses camelCase parameters and a fixed endpoint as required by Google.
    """

    _GOOGLE_STS_URL = "https://sts.googleapis.com/v1/token"

    def __init__(self, http_client: ResilientHttpClient) -> None:
        self._http = http_client

    @property
    def provider_id(self) -> str:
        return "google"

    async def exchange(
        self,
        subject_token: str,
        config: AuthConfig,
        endpoints: OIDCEndpoints,
        *,
        audience: str | None = None,
        scope: str | None = None,
    ) -> TokenSet:
        """Exchange a subject token via Google Cloud STS.

        Uses camelCase parameter names (grantType, subjectToken, etc.)
        and posts to the fixed Google STS URL.
        """
        body: dict[str, str] = {
            "grantType": "urn:ietf:params:oauth:grant-type:token-exchange",
            "subjectToken": subject_token,
            "subjectTokenType": "urn:ietf:params:oauth:token-type:access_token",
            "requestedTokenType": "urn:ietf:params:oauth:token-type:access_token",
        }
        if audience or config.token_exchange_audience:
            body["audience"] = audience or config.token_exchange_audience or ""
        if scope or config.token_exchange_scope:
            body["scope"] = scope or config.token_exchange_scope or ""

        try:
            resp = await self._http.post_form(self._GOOGLE_STS_URL, body, timeout=30)
        except httpx.HTTPStatusError as exc:
            try:
                err_data = exc.response.json()
                message = (
                    err_data.get("error_description")
                    or err_data.get("error")
                    or str(exc.response.status_code)
                )
            except Exception:
                message = str(exc.response.status_code)
            raise ProviderError(f"Google STS token exchange failed: {message}") from exc

        data = resp.json()

        if "access_token" not in data:
            raise ProviderError(
                "Google STS response missing required 'access_token' field"
            )

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
