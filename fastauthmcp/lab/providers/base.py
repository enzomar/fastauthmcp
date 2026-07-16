"""Base identity provider interface.

Each provider implements only what differs from the base.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class TokenResult:
    """A token issued by a provider."""

    access_token: str
    id_token: str | None = None
    refresh_token: str | None = None
    expires_in: int = 3600
    claims: dict[str, Any] = field(default_factory=dict)


class IdentityProvider(ABC):
    """Abstract identity provider.

    Implement this for each IDP (Zitadel, Keycloak, Auth0, etc).
    """

    name: str = "base"

    async def start(self) -> None:
        """Start the provider (e.g., Docker container). Override if needed."""
        pass

    async def stop(self) -> None:
        """Stop the provider. Override if needed."""
        pass

    @abstractmethod
    def discovery_url(self) -> str:
        """Return the OIDC discovery URL."""
        ...

    @abstractmethod
    def issue_token(self, claims: dict[str, Any] | None = None) -> TokenResult:
        """Issue a token with the given claims."""
        ...

    def issue_expired_token(self, claims: dict[str, Any] | None = None) -> TokenResult:
        """Issue an expired token for negative testing."""
        import time

        base_claims = claims or {}
        base_claims["exp"] = int(time.time()) - 3600
        return self.issue_token(base_claims)

    @property
    def issuer(self) -> str:
        """The issuer URL for this provider."""
        return self.discovery_url().replace("/.well-known/openid-configuration", "")

    @property
    def client_id(self) -> str:
        """Default client ID for testing."""
        return "lab-test-client"
