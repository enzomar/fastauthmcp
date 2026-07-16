"""Direct token injection flow.

Used for testing scenarios where a pre-issued token is injected
directly into the gateway (no interactive login needed).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastauthmcp.lab.flows.base import AuthFlow, FlowResult

if TYPE_CHECKING:
    from fastauthmcp.lab.providers.base import IdentityProvider


class DirectTokenFlow(AuthFlow):
    """Inject a pre-issued token directly (no OAuth dance)."""

    name = "direct_token"

    def __init__(self, claims: dict | None = None) -> None:
        self._claims = claims

    async def execute(self, provider: "IdentityProvider") -> FlowResult:
        token_result = provider.issue_token(self._claims)
        return FlowResult(
            access_token=token_result.access_token,
            claims=token_result.claims,
        )
