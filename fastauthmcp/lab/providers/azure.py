"""Azure Entra ID (formerly Azure AD) identity provider."""

from __future__ import annotations

from typing import Any

from fastauthmcp.lab.providers.base import IdentityProvider, TokenResult


class AzureEntraProvider(IdentityProvider):
    """Microsoft Entra ID OIDC provider.

    Supports client_credentials and On-Behalf-Of (OBO) token exchange.
    """

    name = "azure"

    def __init__(
        self,
        tenant_id: str = "common",
        client_id: str = "lab-azure-client",
        client_secret: str = "",
        scope: str = "https://graph.microsoft.com/.default",
    ) -> None:
        self._tenant_id = tenant_id
        self._client_id_val = client_id
        self._client_secret = client_secret
        self._scope = scope

    def discovery_url(self) -> str:
        return f"https://login.microsoftonline.com/{self._tenant_id}/v2.0/.well-known/openid-configuration"

    @property
    def issuer(self) -> str:
        return f"https://login.microsoftonline.com/{self._tenant_id}/v2.0"

    @property
    def client_id(self) -> str:
        return self._client_id_val

    def issue_token(self, claims: dict[str, Any] | None = None) -> TokenResult:
        """Issue a token via Entra ID client_credentials grant."""
        import httpx

        resp = httpx.post(
            f"https://login.microsoftonline.com/{self._tenant_id}/oauth2/v2.0/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id_val,
                "client_secret": self._client_secret,
                "scope": self._scope,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return TokenResult(
            access_token=data["access_token"],
            expires_in=data.get("expires_in", 3600),
        )
