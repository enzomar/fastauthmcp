"""Identity provider abstractions."""

from fastauthmcp.lab.providers.base import IdentityProvider, TokenResult
from fastauthmcp.lab.providers.mock import MockProvider
from fastauthmcp.lab.providers.zitadel import ZitadelProvider
from fastauthmcp.lab.providers.keycloak import KeycloakProvider
from fastauthmcp.lab.providers.auth0 import Auth0Provider
from fastauthmcp.lab.providers.azure import AzureEntraProvider
from fastauthmcp.lab.providers.okta import OktaProvider

__all__ = [
    "IdentityProvider",
    "TokenResult",
    "MockProvider",
    "ZitadelProvider",
    "KeycloakProvider",
    "Auth0Provider",
    "AzureEntraProvider",
    "OktaProvider",
]
