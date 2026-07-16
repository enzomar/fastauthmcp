"""Client Credentials flow (M2M)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from fastauthmcp.lab.flows.base import AuthFlow, FlowResult

if TYPE_CHECKING:
    from fastauthmcp.lab.providers.base import IdentityProvider


class ClientCredentialsFlow(AuthFlow):
    """OAuth2 Client Credentials grant (machine-to-machine)."""

    name = "client_credentials"

    async def execute(self, provider: "IdentityProvider") -> FlowResult:
        token_result = provider.issue_token()
        return FlowResult(
            access_token=token_result.access_token,
            claims=token_result.claims,
        )
