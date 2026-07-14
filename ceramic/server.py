"""CeramicFastMCP - Drop-in replacement for fastmcp.FastMCP with enterprise features."""

from __future__ import annotations

import importlib
import logging
import ssl
from pathlib import Path
from typing import Any

from fastmcp import FastMCP as _FastMCP
from fastmcp.server.middleware import CallNext, Middleware, MiddlewareContext
from fastmcp.tools.base import ToolResult
import mcp.types as _mcp_types

from ceramic.config import AuthConfig, CeramicConfig, PluginRef
from ceramic.config_loader import ConfigLoader
from ceramic.exceptions import ConfigurationError, PluginError
from ceramic.middleware.builtin import (
    AuthenticationMiddleware,
    ObservabilityMiddleware,
    SessionMiddleware,
)
from ceramic.middleware.pipeline import (
    HOOK_POINTS,
    MiddlewarePipeline,
    MiddlewarePlugin,
    RequestContext,
)

logger = logging.getLogger(__name__)


class _CeramicBridgeMiddleware(Middleware):
    """FastMCP-native middleware that bridges to the Ceramic pipeline.

    Intercepts tool calls (on_call_tool) and runs the Ceramic middleware
    pipeline before letting FastMCP execute the tool. This ensures
    IdentityContext is set via contextvars before tool functions run.
    """

    def __init__(self, ceramic_server: "CeramicFastMCP") -> None:
        self._ceramic = ceramic_server

    async def on_call_tool(
        self,
        context: MiddlewareContext[_mcp_types.CallToolRequestParams],
        call_next: CallNext[_mcp_types.CallToolRequestParams, ToolResult],
    ) -> ToolResult:
        """Run Ceramic pipeline before tool execution."""
        pipeline = self._ceramic._pipeline
        tool_name = context.message.name

        # Build a Ceramic RequestContext for this tool call
        ctx = RequestContext(tool_name=tool_name)

        # The handler at the end of the Ceramic pipeline delegates back to
        # FastMCP's call_next, which actually executes the tool function.
        async def fastmcp_handler() -> Any:
            return await call_next(context)

        # Execute the Ceramic pipeline (auth, authz, observability, etc.)
        result = await pipeline.execute(ctx, fastmcp_handler)

        # If the pipeline returned a dict (e.g. error from auth/authz middleware),
        # convert it to a ToolResult so FastMCP can handle it properly.
        if isinstance(result, dict):
            import json
            from mcp.types import TextContent

            return ToolResult(
                content=[TextContent(type="text", text=json.dumps(result))],
                is_error=True,
            )

        return result


class CeramicFastMCP:
    """Drop-in replacement for fastmcp.FastMCP with enterprise features.

    Composes an internal FastMCP instance and delegates all MCP protocol handling
    to it, intercepting the request lifecycle through a middleware pipeline.

    When no ceramic.yaml is found, operates in passthrough mode — behaving
    identically to a vanilla FastMCP instance with no middleware active.
    """

    def __init__(
        self,
        name: str = "ceramic",
        config: str | Path | None = None,
        **kwargs: Any,
    ) -> None:
        """Initialize CeramicFastMCP.

        Args:
            name: Server name (passed to FastMCP).
            config: Path to ceramic.yaml. If None, uses CERAMIC_CONFIG env var
                    or ./ceramic.yaml. If no config found, runs in passthrough mode.
            **kwargs: All additional kwargs forwarded to FastMCP.__init__.

        Raises:
            ConfigurationError: If the config file exists but contains invalid
                YAML, unknown keys, or other validation errors.
        """
        # Compose the internal FastMCP instance
        self._app: _FastMCP = _FastMCP(name=name, **kwargs)

        # Load configuration
        loader = ConfigLoader()
        config_path = Path(config) if isinstance(config, str) else config
        self._config: CeramicConfig = loader.load(path=config_path)

        # Track whether we're in passthrough mode (no config sections active)
        self._passthrough: bool = self._is_passthrough(self._config)

        # Plugin registry — plugins registered via use() are stored here.
        # Wiring into the middleware pipeline happens in task 4.3.
        self._plugins: list[MiddlewarePlugin] = []

        # Load plugins from config if present
        if self._config.plugins:
            self._load_plugins_from_config(self._config.plugins)

        # Tool function registry: tool_name → function (for identity metadata)
        self._tool_functions: dict[str, Any] = {}

        # Build the middleware pipeline based on config sections and plugins
        self._pipeline: MiddlewarePipeline = self._build_pipeline()

        # Register the bridge middleware on the FastMCP instance so that
        # tool calls are intercepted and routed through the Ceramic pipeline.
        if not self._passthrough:
            self._app.add_middleware(_CeramicBridgeMiddleware(self))

    # ------------------------------------------------------------------
    # Delegated decorators (signature-compatible with FastMCP)
    # ------------------------------------------------------------------

    def tool(self, *args: Any, **kwargs: Any) -> Any:
        """Register an MCP tool. Delegates to the internal FastMCP instance."""
        decorator = self._app.tool(*args, **kwargs)

        def wrapper(func: Any) -> Any:
            result = decorator(func)
            tool_name = kwargs.get("name") or func.__name__
            self._tool_functions[tool_name] = func
            return result

        # If called without arguments as @server.tool (no parens), args[0] is the func
        if args and callable(args[0]) and not kwargs:
            func = args[0]
            result = self._app.tool()(func)
            tool_name = func.__name__
            self._tool_functions[tool_name] = func
            return result

        return wrapper

    def prompt(self, *args: Any, **kwargs: Any) -> Any:
        """Register an MCP prompt. Delegates to the internal FastMCP instance."""
        return self._app.prompt(*args, **kwargs)

    def resource(self, *args: Any, **kwargs: Any) -> Any:
        """Register an MCP resource. Delegates to the internal FastMCP instance."""
        return self._app.resource(*args, **kwargs)

    # ------------------------------------------------------------------
    # Transport methods (delegated)
    # ------------------------------------------------------------------

    def run(self, transport: str = "stdio", **kwargs: Any) -> None:
        """Run the server. Delegates to the internal FastMCP instance.

        Args:
            transport: Transport type ("stdio", "sse", "http", or "streamable-http").
            **kwargs: Additional kwargs forwarded to FastMCP.run().
                For HTTP transports, supports host, port, log_level, etc.
        """
        # Filter out host/port for stdio since it doesn't use them
        if transport == "stdio":
            kwargs.pop("host", None)
            kwargs.pop("port", None)
        self._app.run(transport=transport, **kwargs)  # type: ignore[arg-type]

    # ------------------------------------------------------------------
    # Ceramic-specific API
    # ------------------------------------------------------------------

    def use(self, plugin: MiddlewarePlugin) -> None:
        """Register a middleware plugin.

        Validates that the plugin conforms to the MiddlewarePlugin protocol:
        - Must have a ``name`` attribute (str)
        - Must have a ``hooks`` attribute (dict)
        - All hook names in ``hooks`` must be valid HOOK_POINTS members

        The plugin is stored and will be wired into the middleware pipeline
        during request processing (implemented in task 4.3).

        Args:
            plugin: A MiddlewarePlugin instance with name and hooks attributes.

        Raises:
            PluginError: If the plugin does not conform to the MiddlewarePlugin
                protocol or contains invalid hook names.
        """
        # Validate name attribute
        if not hasattr(plugin, "name") or not isinstance(plugin.name, str):
            raise PluginError("Plugin must have a 'name' attribute of type str.")

        # Validate hooks attribute
        if not hasattr(plugin, "hooks") or not isinstance(plugin.hooks, dict):
            raise PluginError(
                f"Plugin '{plugin.name}' must have a 'hooks' attribute of type dict."
            )

        # Validate all hook names are valid
        invalid_hooks = set(plugin.hooks.keys()) - HOOK_POINTS
        if invalid_hooks:
            raise PluginError(
                f"Plugin '{plugin.name}' has invalid hook names: "
                f"{sorted(invalid_hooks)}. "
                f"Valid hook points are: {sorted(HOOK_POINTS)}."
            )

        self._plugins.append(plugin)

    # ------------------------------------------------------------------
    # Migration helper
    # ------------------------------------------------------------------

    @staticmethod
    def enable_ceramic(
        app: _FastMCP, config: str | Path | None = None
    ) -> "CeramicFastMCP":
        """Wrap an existing FastMCP instance with Ceramic enterprise features.

        This allows incremental migration without changing the import statement.
        The existing FastMCP instance becomes the internal delegate.

        If config is invalid, raises ConfigurationError and leaves the original
        FastMCP instance completely unmodified.

        Args:
            app: An existing fastmcp.FastMCP instance to wrap.
            config: Path to ceramic.yaml. If None, uses CERAMIC_CONFIG env var
                    or ./ceramic.yaml.

        Returns:
            A CeramicFastMCP instance wrapping the provided FastMCP app.

        Raises:
            ConfigurationError: If the config file exists but is invalid.
        """
        # Load configuration FIRST — before touching the app.
        # If this raises, the original app is never modified.
        loader = ConfigLoader()
        config_path = Path(config) if isinstance(config, str) else config
        loaded_config = loader.load(path=config_path)

        # Load plugins from config before constructing instance.
        # If plugin loading fails, the original app remains unmodified.
        plugins: list[MiddlewarePlugin] = []
        if loaded_config.plugins:
            plugins = CeramicFastMCP._load_plugins_from_refs(loaded_config.plugins)

        # Everything validated — now build the instance
        instance = object.__new__(CeramicFastMCP)
        instance._app = app
        instance._config = loaded_config
        instance._passthrough = CeramicFastMCP._is_passthrough(loaded_config)
        instance._plugins = plugins
        instance._tool_functions = {}
        instance._pipeline = instance._build_pipeline()

        # Register the bridge middleware on the FastMCP instance
        if not instance._passthrough:
            instance._app.add_middleware(_CeramicBridgeMiddleware(instance))

        return instance

    # ------------------------------------------------------------------
    # Plugin loading from config
    # ------------------------------------------------------------------

    def _load_plugins_from_config(self, plugin_refs: list[PluginRef]) -> None:
        """Load and register plugins from the config's plugins section.

        For each PluginRef, imports the module and looks for a
        ``create_plugin(config: dict) -> MiddlewarePlugin`` factory function.

        Args:
            plugin_refs: List of PluginRef entries from the config.

        Raises:
            ConfigurationError: If a module can't be imported or doesn't have
                the ``create_plugin`` factory function.
        """
        plugins = self._load_plugins_from_refs(plugin_refs)
        for plugin in plugins:
            self._plugins.append(plugin)

    @staticmethod
    def _load_plugins_from_refs(plugin_refs: list[PluginRef]) -> list[MiddlewarePlugin]:
        """Load plugins from a list of PluginRef entries.

        For each PluginRef, imports the module and looks for a
        ``create_plugin(config: dict) -> MiddlewarePlugin`` factory function.

        Args:
            plugin_refs: List of PluginRef entries from the config.

        Returns:
            List of instantiated MiddlewarePlugin objects.

        Raises:
            ConfigurationError: If a module can't be imported or doesn't have
                the ``create_plugin`` factory function.
        """
        plugins: list[MiddlewarePlugin] = []

        for ref in plugin_refs:
            # Import the module
            try:
                module = importlib.import_module(ref.module)
            except (ImportError, ModuleNotFoundError) as exc:
                raise ConfigurationError(
                    f"Cannot import plugin module '{ref.module}': {exc}"
                ) from exc

            # Look for create_plugin factory
            factory = getattr(module, "create_plugin", None)
            if factory is None or not callable(factory):
                raise ConfigurationError(
                    f"Plugin module '{ref.module}' does not have a callable "
                    f"'create_plugin' factory function."
                )

            # Instantiate the plugin
            try:
                plugin = factory(ref.config)
            except Exception as exc:
                raise ConfigurationError(
                    f"Failed to create plugin from module '{ref.module}': {exc}"
                ) from exc

            # Validate the resulting plugin
            if not hasattr(plugin, "name") or not isinstance(plugin.name, str):
                raise ConfigurationError(
                    f"Plugin from module '{ref.module}' does not have a valid "
                    f"'name' attribute."
                )
            if not hasattr(plugin, "hooks") or not isinstance(plugin.hooks, dict):
                raise ConfigurationError(
                    f"Plugin from module '{ref.module}' does not have a valid "
                    f"'hooks' attribute."
                )

            # Validate hook names
            invalid_hooks = set(plugin.hooks.keys()) - HOOK_POINTS
            if invalid_hooks:
                raise ConfigurationError(
                    f"Plugin '{plugin.name}' from module '{ref.module}' has "
                    f"invalid hook names: {sorted(invalid_hooks)}."
                )

            plugins.append(plugin)

        return plugins

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _build_pipeline(self) -> MiddlewarePipeline:
        """Construct the middleware pipeline based on loaded config sections.

        Built-in middleware is registered in fixed order per design:
        1. ObservabilityMiddleware (if config.observability is present/enabled)
        2. SessionMiddleware (if config.sessions is present/enabled)
        3. AuthenticationMiddleware (if config.auth is present)
        4. Custom plugins (in registration order)

        In passthrough mode (no config sections active and no plugins),
        the pipeline is empty — requests go directly to FastMCP.

        Returns:
            A configured MiddlewarePipeline instance.
        """
        pipeline = MiddlewarePipeline()
        layers: list[str] = []

        # Add built-in middleware based on config sections (fixed order)
        if self._config.observability is not None:
            pipeline.add_before(ObservabilityMiddleware(self._config.observability))
            layers.append("observability")

        # Sessions are auto-disabled in token_exchange mode — each request
        # carries its own upstream token so there's no session to restore.
        _is_token_exchange = (
            self._config.auth is not None
            and self._config.auth.grant_type == "token_exchange"
        )
        if self._config.sessions is not None and not _is_token_exchange:
            pipeline.add_before(SessionMiddleware(self._config.sessions))
            layers.append("session")
        elif _is_token_exchange and self._config.sessions is not None:
            logger.info(
                "Sessions auto-disabled: token_exchange mode uses per-request tokens"
            )

        if self._config.auth is not None:
            ssl_context = self._build_mtls_context(self._config.auth)
            pipeline.add_before(
                AuthenticationMiddleware(self._config.auth, ssl_context=ssl_context)
            )
            layers.append("authentication")

        # Add custom plugin hooks (in registration order, after built-ins)
        for plugin in self._plugins:
            if "before_request" in plugin.hooks:
                pipeline.add_before(plugin.hooks["before_request"])
            if "after_request" in plugin.hooks:
                pipeline.add_after(plugin.hooks["after_request"])
            if "on_exception" in plugin.hooks:
                pipeline.add_exception_handler(plugin.hooks["on_exception"])
            layers.append(f"plugin:{plugin.name}")

        self._middleware_layers = layers
        return pipeline

    @staticmethod
    def _is_passthrough(config: CeramicConfig) -> bool:
        """Determine if Ceramic should run in passthrough mode.

        Passthrough mode is active when no enterprise feature sections are
        configured (all optional sections are None).
        """
        return (
            config.auth is None
            and config.observability is None
            and config.sessions is None
            and config.plugins is None
        )

    @staticmethod
    def _build_mtls_context(auth_config: "AuthConfig") -> "ssl.SSLContext | None":
        """Build an SSL context for mTLS if configured.

        Reads the ``mtls`` section from AuthConfig and constructs an
        ssl.SSLContext with the client certificate loaded. Returns None
        if mTLS is not configured.

        Args:
            auth_config: The authentication configuration.

        Returns:
            An ssl.SSLContext configured for mTLS, or None.

        Raises:
            ConfigurationError: If the certificate/key files are invalid or missing.
        """

        from ceramic.security import TLSEnforcer

        if auth_config.mtls is None:
            return None

        mtls = auth_config.mtls
        enforcer = TLSEnforcer()
        return enforcer.get_mtls_ssl_context(
            client_cert=mtls.client_cert,
            client_key=mtls.client_key,
            ca_bundle=mtls.ca_bundle,
        )
