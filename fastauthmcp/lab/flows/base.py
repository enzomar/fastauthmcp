"""Base authentication flow interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from fastauthmcp.lab.providers.base import IdentityProvider


@dataclass
class FlowResult:
    """Result of executing an authentication flow."""

    access_token: str
    id_token: str | None = None
    refresh_token: str | None = None
    claims: dict[str, Any] = field(default_factory=dict)
    success: bool = True
    error: str | None = None


class AuthFlow(ABC):
    """Base class for authentication flows.

    Each flow implements a specific OAuth2/OIDC grant type.
    """

    name: str = "base"

    @abstractmethod
    async def execute(self, provider: "IdentityProvider") -> FlowResult:
        """Execute the authentication flow against the given provider."""
        ...
