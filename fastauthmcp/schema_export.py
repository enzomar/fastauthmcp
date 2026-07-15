"""Schema export: generate machine-readable API schemas from FastAuthMCP servers.

Exports the MCP server's tool definitions, authorization requirements,
rate limits, and configuration schema in standard formats for documentation,
client generation, and integration testing.

Usage:

    fastauthmcp schema export --format json > schema.json
    fastauthmcp schema export --format openapi > openapi.yaml
    fastauthmcp schema export --format markdown > API.md
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any

from fastauthmcp.authorization import get_policies


@dataclass
class ToolSchema:
    """Schema for a single MCP tool including auth requirements."""

    name: str
    description: str | None = None
    parameters: dict[str, Any] = field(default_factory=dict)
    return_type: str | None = None
    required_roles: list[str] = field(default_factory=list)
    required_groups: list[str] = field(default_factory=list)
    required_scopes: list[str] = field(default_factory=list)
    rate_limit_rpm: int | None = None
    is_async: bool = True


@dataclass
class ServerSchema:
    """Complete schema for a FastAuthMCP MCP server."""

    name: str
    version: str | None = None
    description: str | None = None
    tools: list[ToolSchema] = field(default_factory=list)
    auth_required: bool = False
    supported_transports: list[str] = field(
        default_factory=lambda: ["stdio", "sse", "streamable-http"]
    )
    idp_issuer: str | None = None


class SchemaExporter:
    """Generates server schemas from a FastAuthMCP instance."""

    def __init__(self, server: Any) -> None:
        self._server = server

    def export_schema(self) -> ServerSchema:
        """Generate the full server schema."""
        tools: list[ToolSchema] = []

        for tool_name, func in self._server._tool_functions.items():
            tool_schema = self._build_tool_schema(tool_name, func)
            tools.append(tool_schema)

        schema = ServerSchema(
            name=self._server._app.name
            if hasattr(self._server._app, "name")
            else "fastauthmcp",
            tools=tools,
            auth_required=self._server._config.auth is not None,
        )

        if self._server._config.auth:
            schema.idp_issuer = str(self._server._config.auth.issuer)

        return schema

    def to_json(self, indent: int = 2) -> str:
        """Export schema as JSON."""
        schema = self.export_schema()
        return json.dumps(asdict(schema), indent=indent, default=str)

    def to_markdown(self) -> str:
        """Export schema as Markdown documentation."""
        schema = self.export_schema()
        lines = [
            f"# {schema.name} — MCP Server API",
            "",
        ]

        if schema.description:
            lines.append(schema.description)
            lines.append("")

        if schema.auth_required:
            lines.append(
                f"**Authentication:** Required (OIDC, issuer: `{schema.idp_issuer}`)"
            )
            lines.append("")

        lines.append("## Tools")
        lines.append("")

        for tool in schema.tools:
            lines.append(f"### `{tool.name}`")
            lines.append("")
            if tool.description:
                lines.append(tool.description)
                lines.append("")
            if tool.required_roles:
                lines.append(f"**Required roles:** {', '.join(tool.required_roles)}")
            if tool.required_groups:
                lines.append(f"**Required groups:** {', '.join(tool.required_groups)}")
            if tool.required_scopes:
                lines.append(f"**Required scopes:** {', '.join(tool.required_scopes)}")
            if tool.rate_limit_rpm:
                lines.append(f"**Rate limit:** {tool.rate_limit_rpm} rpm")
            lines.append("")

        return "\n".join(lines)

    def _build_tool_schema(self, tool_name: str, func: Any) -> ToolSchema:
        """Build a ToolSchema from a tool function."""
        import asyncio
        import inspect

        # Get policies from decorators
        policies = get_policies(func)
        required_roles: list[str] = []
        required_groups: list[str] = []
        required_scopes: list[str] = []

        for policy in policies:
            if policy.kind == "roles":
                required_roles.extend(sorted(policy.values))
            elif policy.kind == "groups":
                required_groups.extend(sorted(policy.values))
            elif policy.kind == "scopes":
                required_scopes.extend(sorted(policy.values))

        # Extract description from docstring
        description = inspect.getdoc(func)

        # Extract parameters from type hints
        params: dict[str, Any] = {}
        sig = inspect.signature(func)
        for param_name, param in sig.parameters.items():
            if param_name in ("self", "cls"):
                continue
            param_info: dict[str, Any] = {}
            if param.annotation != inspect.Parameter.empty:
                param_info["type"] = str(param.annotation)
            if param.default != inspect.Parameter.empty:
                param_info["default"] = repr(param.default)
            params[param_name] = param_info

        return ToolSchema(
            name=tool_name,
            description=description,
            parameters=params,
            required_roles=required_roles,
            required_groups=required_groups,
            required_scopes=required_scopes,
            is_async=asyncio.iscoroutinefunction(func),
        )
