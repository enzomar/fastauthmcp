"""FastAuthMCP Framework - Enterprise capabilities on top of FastMCP."""

from fastauthmcp.authorization import (
    require_group,
    require_groups,
    require_role,
    require_roles,
    require_scopes,
)
from fastauthmcp.context import get_context, request_context, set_context
from fastauthmcp.downstream import (
    authenticated_async_client,
    authenticated_client,
    authenticated_soap_client,
)
from fastauthmcp.identity import IdentityContext, access_token, identity
from fastauthmcp.server import FastAuthMCP
from fastauthmcp.testing import FastAuthMCPTestClient

# Public alias: `from fastauthmcp import FastMCP` is the drop-in replacement
FastMCP = FastAuthMCP

__all__ = [
    "FastMCP",
    "FastAuthMCP",
    "identity",
    "access_token",
    "IdentityContext",
    "FastAuthMCPTestClient",
    "authenticated_client",
    "authenticated_async_client",
    "authenticated_soap_client",
    # Authorization decorators
    "require_roles",
    "require_groups",
    "require_scopes",
    "require_role",
    "require_group",
    # Request context propagation
    "get_context",
    "set_context",
    "request_context",
]
