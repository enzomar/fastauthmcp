"""Authorization middleware: evaluates per-tool policies before execution.

Checks decorator-based policies (@require_roles, @require_groups, @require_scopes)
and YAML-defined policies, rejecting unauthorized requests before the tool body runs.
"""

from __future__ import annotations

import fnmatch
import logging
from typing import Any, Awaitable, Callable

from fastauthmcp.authorization import AuthzPolicy, get_policies
from fastauthmcp.identity import IdentityContext
from fastauthmcp.middleware.pipeline import RequestContext

logger = logging.getLogger(__name__)


class AuthorizationMiddleware:
    """Middleware that enforces per-tool authorization policies.

    Evaluates:
    1. Decorator-based policies attached to the tool function
    2. YAML-defined policies from the authorization config section

    All policies use AND semantics — every policy must pass for access to be granted.
    """

    def __init__(
        self,
        tool_functions: dict[str, Any] | None = None,
        yaml_policies: list[dict[str, Any]] | None = None,
    ) -> None:
        self._tool_functions = tool_functions or {}
        self._yaml_policies = yaml_policies or []

    async def __call__(
        self, ctx: RequestContext, next: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Evaluate authorization policies before tool execution."""
        tool_name = ctx.tool_name

        if not tool_name:
            return await next()

        # Get the identity — if None, check if any policies exist
        identity: IdentityContext | None = ctx.identity

        # Collect all policies for this tool
        policies: list[AuthzPolicy] = []

        # 1. Decorator-based policies
        func = self._tool_functions.get(tool_name)
        if func is not None:
            policies.extend(get_policies(func))

        # 2. YAML-defined policies (glob matching on tool name)
        for yaml_policy in self._yaml_policies:
            pattern = yaml_policy.get("tool", "")
            if fnmatch.fnmatch(tool_name, pattern):
                if "require_role" in yaml_policy:
                    policies.append(
                        AuthzPolicy("roles", frozenset([yaml_policy["require_role"]]))
                    )
                if "require_group" in yaml_policy:
                    policies.append(
                        AuthzPolicy("groups", frozenset([yaml_policy["require_group"]]))
                    )
                if "require_scopes" in yaml_policy:
                    scopes = yaml_policy["require_scopes"]
                    if isinstance(scopes, str):
                        scopes = scopes.split()
                    policies.append(AuthzPolicy("scopes", frozenset(scopes)))

        # No policies = open access
        if not policies:
            return await next()

        # Policies exist but no identity = unauthorized
        if identity is None:
            logger.warning(
                "Authorization denied for tool '%s': no identity context", tool_name
            )
            return {
                "error": "authorization_required",
                "message": f"Tool '{tool_name}' requires authentication.",
            }

        # Evaluate all policies (AND semantics)
        user_roles = identity.roles
        user_groups = identity.groups
        # Extract scopes from claims (space-separated 'scope' claim)
        scope_claim = identity.claims.get("scope", "")
        user_scopes = frozenset(
            scope_claim.split() if isinstance(scope_claim, str) else scope_claim
        )

        for policy in policies:
            if not policy.evaluate(user_roles, user_groups, user_scopes):
                logger.warning(
                    "Authorization denied for tool '%s': "
                    "user lacks required %s (needed: %s, has: roles=%s, groups=%s, scopes=%s)",
                    tool_name,
                    policy.kind,
                    sorted(policy.values),
                    sorted(user_roles),
                    sorted(user_groups),
                    sorted(user_scopes),
                )
                return {
                    "error": "authorization_denied",
                    "message": (
                        f"Insufficient permissions for tool '{tool_name}'. "
                        f"Required {policy.kind}: {sorted(policy.values)}."
                    ),
                }

        return await next()
