"""Authorization middleware for the Ceramic framework.

Evaluates both decorator-based policies (stored on tool functions) and
YAML-defined policies (glob-matched against tool names). All policies
use AND semantics — every condition must pass for the request to proceed.
"""

from __future__ import annotations

import fnmatch
import logging
from typing import Any, Awaitable, Callable

from ceramic.config import AuthorizationConfig
from ceramic.middleware.pipeline import RequestContext

logger = logging.getLogger(__name__)


class AuthorizationMiddleware:
    """Evaluates authorization policies before tool execution.

    Checks both:
    1. Decorator-based policies (`_ceramic_required_roles`, `_ceramic_required_groups`)
    2. YAML-defined policies (glob pattern matching on tool names)

    All conditions use AND semantics — if any single condition fails,
    the request is rejected before the tool body executes.
    """

    def __init__(
        self,
        authz_config: AuthorizationConfig,
        tool_functions: dict[str, Callable] | None = None,
    ) -> None:
        """Initialize the authorization middleware.

        Args:
            authz_config: The authorization configuration containing policies.
            tool_functions: Mapping of tool_name → function for looking up
                decorator metadata. If None, only YAML policies are evaluated.
        """
        self.config = authz_config
        self._tool_functions = tool_functions or {}

    async def __call__(
        self, ctx: RequestContext, next: Callable[[], Awaitable[Any]]
    ) -> Any:
        """Evaluate authorization policies for the current request.

        Steps:
        1. Get tool_name from ctx
        2. Determine if any policies apply (decorator or YAML)
        3. If identity is None and policies exist → auth-required error
        4. Check decorator-based policies
        5. Check YAML-based policies
        6. If any policy fails → authorization error
        7. If all pass → call next()
        """
        tool_name = ctx.tool_name
        if tool_name is None:
            # Not a tool invocation — pass through
            return await next()

        # Gather all requirements
        required_roles: list[str] = []
        required_groups: list[str] = []

        # 1. Check decorator-based policies
        tool_func = self._tool_functions.get(tool_name)
        if tool_func is not None:
            decorator_roles = getattr(tool_func, "_ceramic_required_roles", [])
            decorator_groups = getattr(tool_func, "_ceramic_required_groups", [])
            required_roles.extend(decorator_roles)
            required_groups.extend(decorator_groups)

        # 2. Check YAML-based policies (glob match)
        for policy in self.config.policies:
            if fnmatch.fnmatch(tool_name, policy.tool):
                if policy.require_role is not None:
                    required_roles.append(policy.require_role)
                if policy.require_group is not None:
                    required_groups.append(policy.require_group)

        # If no policies apply, pass through
        if not required_roles and not required_groups:
            return await next()

        # 3. If identity is None and tool has policies → auth-required error
        if ctx.identity is None:
            all_required = []
            for r in required_roles:
                all_required.append(f"role:{r}")
            for g in required_groups:
                all_required.append(f"group:{g}")
            logger.warning(
                "Authorization denied for tool '%s': no identity context",
                tool_name,
            )
            return {
                "error": "authorization_denied",
                "message": "Authentication is required",
                "required": all_required,
            }

        # 4. Evaluate all policies (AND semantics)
        missing: list[str] = []

        # Check roles
        user_roles = ctx.identity.roles
        for role in required_roles:
            if role not in user_roles:
                missing.append(f"role:{role}")

        # Check groups
        user_groups = ctx.identity.groups
        for group in required_groups:
            if group not in user_groups:
                missing.append(f"group:{group}")

        # 5. If any policy fails → authorization error
        if missing:
            logger.warning(
                "Authorization denied for tool '%s': missing %s",
                tool_name,
                missing,
            )
            return {
                "error": "authorization_denied",
                "message": "Insufficient permissions",
                "required": missing,
            }

        # 6. All policies satisfied → proceed
        return await next()
