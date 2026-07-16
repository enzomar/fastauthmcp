"""Okta identity provider."""

from __future__ import annotations

from typing import Any

from fastauthmcp.lab.providers.base import IdentityProvider, TokenResult


class OktaProvider(IdentityProvider):
    """Okta OIDC provider.

    Supports client_credentials and authorization code flows.
    """

    name = "okta"

    def __init__(
        self,
        domain: str = "fastauthmcp-lab.okta.com",
        auth_server: str = "default",
        client_id: str = "lab-okta-client",
        client_secret: str = "",
        scopes: str = "openid profile email",
    ) -> None:
        self._domain = domain
        self._auth_server = auth_server
        self._client_id_val = client_id
        self._client_secret = client_secret
        self._scopes = scopes

    def discovery_url(self) -> str:
        return f"https://{self._domain}/oauth2/{self._auth_server}/.well-known/openid-configuration"

    @property
    def issuer(self) -> str:
        return f"https://{self._domain}/oauth2/{self._auth_server}"

    @property
    def client_id(self) -> str:
        return self._client_id_val

    def issue_token(self, claims: dict[str, Any] | None = None) -> TokenResult:
        """Issue a token via Okta client_credentials grant."""
        import httpx

        resp = httpx.post(
            f"https://{self._domain}/oauth2/{self._auth_server}/v1/token",
            data={
                "grant_type": "client_credentials",
                "scope": self._scopes,
            },
            auth=(self._client_id_val, self._client_secret),
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return TokenResult(
            access_token=data["access_token"],
            expires_in=data.get("expires_in", 3600),
        )
