"""Auth0 identity provider."""

from __future__ import annotations

from typing import Any

from fastauthmcp.lab.providers.base import IdentityProvider, TokenResult


class Auth0Provider(IdentityProvider):
    """Auth0 OIDC provider.

    Supports client_credentials for M2M and token issuance via
    the Auth0 Management/Authentication API.
    """

    name = "auth0"

    def __init__(
        self,
        domain: str = "fastauthmcp-lab.auth0.com",
        client_id: str = "lab-m2m-client",
        client_secret: str = "",
        audience: str = "https://fastauthmcp-lab-api",
    ) -> None:
        self._domain = domain
        self._client_id_val = client_id
        self._client_secret = client_secret
        self._audience = audience

    def discovery_url(self) -> str:
        return f"https://{self._domain}/.well-known/openid-configuration"

    @property
    def issuer(self) -> str:
        return f"https://{self._domain}/"

    @property
    def client_id(self) -> str:
        return self._client_id_val

    def issue_token(self, claims: dict[str, Any] | None = None) -> TokenResult:
        """Issue a token via Auth0's client_credentials grant."""
        import httpx

        resp = httpx.post(
            f"https://{self._domain}/oauth/token",
            json={
                "grant_type": "client_credentials",
                "client_id": self._client_id_val,
                "client_secret": self._client_secret,
                "audience": self._audience,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return TokenResult(
            access_token=data["access_token"],
            expires_in=data.get("expires_in", 86400),
        )
