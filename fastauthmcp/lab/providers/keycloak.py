"""Keycloak identity provider (Docker-based).

Requires Docker. Starts a Keycloak container with a pre-configured realm.
"""

from __future__ import annotations

from typing import Any

from fastauthmcp.lab.providers.base import IdentityProvider, TokenResult


class KeycloakProvider(IdentityProvider):
    """Keycloak OIDC provider running in Docker.

    Starts a Keycloak container, imports a test realm, and provides
    token issuance via the admin API or direct grants.
    """

    name = "keycloak"

    def __init__(
        self,
        realm: str = "fastauthmcp-lab",
        port: int = 8080,
        client_id: str = "lab-test-client",
        client_secret: str = "lab-test-secret",
    ) -> None:
        self._realm = realm
        self._port = port
        self._client_id_val = client_id
        self._client_secret = client_secret
        self._base_url = f"http://localhost:{port}"

    def discovery_url(self) -> str:
        return f"{self._base_url}/realms/{self._realm}/.well-known/openid-configuration"

    @property
    def issuer(self) -> str:
        return f"{self._base_url}/realms/{self._realm}"

    @property
    def client_id(self) -> str:
        return self._client_id_val

    def issue_token(self, claims: dict[str, Any] | None = None) -> TokenResult:
        """Issue a token via Keycloak's direct-grant (ROPC) endpoint."""
        import httpx

        resp = httpx.post(
            f"{self._base_url}/realms/{self._realm}/protocol/openid-connect/token",
            data={
                "grant_type": "client_credentials",
                "client_id": self._client_id_val,
                "client_secret": self._client_secret,
            },
            timeout=10,
        )
        resp.raise_for_status()
        data = resp.json()
        return TokenResult(
            access_token=data["access_token"],
            refresh_token=data.get("refresh_token"),
            expires_in=data.get("expires_in", 300),
        )
