"""Authentication flow abstractions."""

from fastauthmcp.lab.flows.base import AuthFlow, FlowResult
from fastauthmcp.lab.flows.client_credentials import ClientCredentialsFlow
from fastauthmcp.lab.flows.direct_token import DirectTokenFlow

__all__ = ["AuthFlow", "FlowResult", "ClientCredentialsFlow", "DirectTokenFlow"]
