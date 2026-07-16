"""Zitadel identity provider.

Can use the public FastAuthMCP OSS Zitadel instance or a local Docker one.
"""

from __future__ import annotations

from typing import Any

from fastauthmcp.lab.providers.base import IdentityProvider, TokenResult


class ZitadelProvider(IdentityProvider):
    """Zitadel OIDC provider.

    By default uses the public FastAuthMCP OSS Zitadel Cloud instance.
    For local testing, start Zitadel in Docker and override the base_url.
    """

    name = "zitadel"

    def __init__(
        self,
        base_url: str = "https://ceramic-oss-agq8i8.eu1.zitadel.cloud",
        client_id: str = "380842820363183891",
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._client_id_val = client_id

    def discovery_url(self) -> str:
        return f"{self._base_url}/.well-known/openid-configuration"

    @property
    def issuer(self) -> str:
        return self._base_url

    @property
    def client_id(self) -> str:
        return self._client_id_val

    def issue_token(self, claims: dict[str, Any] | None = None) -> TokenResult:
        """Zitadel requires interactive login or service account JWT.

        For lab tests, use MockProvider for unit scenarios and
        the real Zitadel flow for integration/browser scenarios.
        """
        raise NotImplementedError(
            "ZitadelProvider.issue_token() requires interactive login. "
            "Use MockProvider for non-interactive scenarios."
        )
