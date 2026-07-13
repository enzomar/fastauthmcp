"""Unit tests for CeramicFastMCP delegation and passthrough behavior."""

from __future__ import annotations


import pytest

from ceramic.config import CeramicConfig
from ceramic.exceptions import ConfigurationError, PluginError
from ceramic.server import CeramicFastMCP


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class FakePlugin:
    """A minimal MiddlewarePlugin-conforming object for testing use()."""

    name: str = "fake-plugin"
    hooks: dict = {}


class ValidPluginWithHooks:
    """A MiddlewarePlugin with valid hooks for testing."""

    def __init__(self, name: str = "valid-plugin", hooks: dict | None = None):
        self.name = name
        self.hooks = hooks if hooks is not None else {}


class PluginWithInvalidHooks:
    """A plugin with an invalid hook name."""

    name: str = "bad-hooks-plugin"
    hooks: dict = {"nonexistent_hook": lambda ctx, nxt: None}


class PluginMissingName:
    """A plugin without a name attribute."""

    hooks: dict = {}


class PluginMissingHooks:
    """A plugin without a hooks attribute."""

    name: str = "no-hooks"


# ---------------------------------------------------------------------------
# Tests: Initialization and passthrough mode
# ---------------------------------------------------------------------------


class TestCeramicFastMCPInit:
    """Tests for __init__ and config loading."""

    def test_init_no_config_passthrough(self, tmp_path, monkeypatch):
        """With no ceramic.yaml, should initialize in passthrough mode."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")

        assert server._passthrough is True
        assert server._config == CeramicConfig()
        assert server._plugins == []
        assert server._app is not None

    def test_init_with_valid_config(self, tmp_path, monkeypatch):
        """With a valid ceramic.yaml, should load config and not be passthrough."""
        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text("observability:\n  enabled: true\n  log_level: info\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")

        assert server._passthrough is False
        assert server._config.observability is not None
        assert server._config.observability.enabled is True

    def test_init_with_explicit_config_path(self, tmp_path, monkeypatch):
        """Explicit config path should be used directly."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)
        config_file = tmp_path / "custom.yaml"
        config_file.write_text("sessions:\n  enabled: true\n  ttl: 7200\n")

        server = CeramicFastMCP(name="test-server", config=str(config_file))

        assert server._config.sessions is not None
        assert server._config.sessions.ttl == 7200

    def test_init_invalid_yaml_raises_configuration_error(self, tmp_path, monkeypatch):
        """Invalid YAML should raise ConfigurationError at startup."""
        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text("auth:\n  provider: [invalid yaml\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        with pytest.raises(ConfigurationError):
            CeramicFastMCP(name="test-server")

    def test_init_unknown_keys_raises_configuration_error(self, tmp_path, monkeypatch):
        """Unknown top-level keys should raise ConfigurationError."""
        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text("unknown_section:\n  key: value\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        with pytest.raises(ConfigurationError):
            CeramicFastMCP(name="test-server")

    def test_init_forwards_kwargs_to_fastmcp(self, tmp_path, monkeypatch):
        """Additional kwargs should be forwarded to FastMCP.__init__."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        # FastMCP accepts 'instructions' kwarg
        server = CeramicFastMCP(name="test-server", instructions="Test instructions")

        assert server._app is not None


# ---------------------------------------------------------------------------
# Tests: Delegation
# ---------------------------------------------------------------------------


class TestDelegation:
    """Tests for decorator/method delegation to the internal FastMCP instance."""

    def test_tool_decorator_registers_on_internal_app(self, tmp_path, monkeypatch):
        """tool() should delegate to _app.tool() and register the tool."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")

        @server.tool()
        def my_tool(x: int) -> int:
            """A test tool."""
            return x * 2

        # The tool should be registered on the internal FastMCP instance
        # FastMCP stores tools internally — verify via the internal app
        assert server._app is not None

    def test_prompt_decorator_registers_on_internal_app(self, tmp_path, monkeypatch):
        """prompt() should delegate to _app.prompt()."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")

        @server.prompt()
        def my_prompt() -> str:
            """A test prompt."""
            return "Hello"

        assert server._app is not None

    def test_resource_decorator_registers_on_internal_app(self, tmp_path, monkeypatch):
        """resource() should delegate to _app.resource()."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")

        @server.resource("test://resource")
        def my_resource() -> str:
            """A test resource."""
            return "data"

        assert server._app is not None

    def test_run_method_exists_and_is_callable(self, tmp_path, monkeypatch):
        """run() should be a callable method on CeramicFastMCP."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")

        assert callable(server.run)


# ---------------------------------------------------------------------------
# Tests: use() plugin registration
# ---------------------------------------------------------------------------


class TestPluginRegistration:
    """Tests for the use() method."""

    def test_use_registers_plugin(self, tmp_path, monkeypatch):
        """use() should store the plugin in the plugins list."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")
        plugin = FakePlugin()

        server.use(plugin)

        assert len(server._plugins) == 1
        assert server._plugins[0] is plugin

    def test_use_multiple_plugins(self, tmp_path, monkeypatch):
        """use() should allow registering multiple plugins."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")
        plugin1 = FakePlugin()
        plugin2 = FakePlugin()

        server.use(plugin1)
        server.use(plugin2)

        assert len(server._plugins) == 2


# ---------------------------------------------------------------------------
# Tests: enable_ceramic() static method
# ---------------------------------------------------------------------------


class TestEnableCeramic:
    """Tests for the enable_ceramic() migration helper."""

    def test_enable_ceramic_wraps_existing_instance(self, tmp_path, monkeypatch):
        """enable_ceramic() should wrap an existing FastMCP instance."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        from fastmcp import FastMCP as _FastMCP

        original = _FastMCP(name="original-app")
        wrapped = CeramicFastMCP.enable_ceramic(original)

        assert isinstance(wrapped, CeramicFastMCP)
        assert wrapped._app is original
        assert wrapped._passthrough is True

    def test_enable_ceramic_with_config(self, tmp_path, monkeypatch):
        """enable_ceramic() should load config from explicit path."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text("observability:\n  enabled: true\n")

        from fastmcp import FastMCP as _FastMCP

        original = _FastMCP(name="original-app")
        wrapped = CeramicFastMCP.enable_ceramic(original, config=str(config_file))

        assert wrapped._app is original
        assert wrapped._passthrough is False
        assert wrapped._config.observability is not None

    def test_enable_ceramic_invalid_config_raises(self, tmp_path, monkeypatch):
        """enable_ceramic() with invalid config should raise ConfigurationError."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        config_file = tmp_path / "bad.yaml"
        config_file.write_text("invalid_key: true\n")

        from fastmcp import FastMCP as _FastMCP

        original = _FastMCP(name="original-app")

        with pytest.raises(ConfigurationError):
            CeramicFastMCP.enable_ceramic(original, config=str(config_file))

    def test_enable_ceramic_preserves_registered_tools(self, tmp_path, monkeypatch):
        """Tools registered on the original FastMCP should remain after wrapping."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        from fastmcp import FastMCP as _FastMCP

        original = _FastMCP(name="original-app")

        @original.tool()
        def existing_tool(x: int) -> int:
            """Pre-existing tool."""
            return x + 1

        wrapped = CeramicFastMCP.enable_ceramic(original)

        # The internal app is the same object, so tools are preserved
        assert wrapped._app is original


# ---------------------------------------------------------------------------
# Tests: Enhanced use() with validation
# ---------------------------------------------------------------------------


class TestPluginValidation:
    """Tests for use() plugin validation logic."""

    def test_use_valid_plugin_with_hooks(self, tmp_path, monkeypatch):
        """use() should accept a plugin with valid hook names."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")
        plugin = ValidPluginWithHooks(
            name="my-plugin",
            hooks={"before_request": lambda ctx, nxt: None},
        )

        server.use(plugin)

        assert len(server._plugins) == 1
        assert server._plugins[0].name == "my-plugin"

    def test_use_plugin_all_valid_hooks(self, tmp_path, monkeypatch):
        """use() should accept a plugin using all valid hook points."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")
        hooks = {
            hook: lambda ctx, nxt: None
            for hook in [
                "before_request",
                "after_request",
                "before_tool",
                "after_tool",
                "on_authentication",
                "on_authorization",
                "on_exception",
                "on_shutdown",
            ]
        }
        plugin = ValidPluginWithHooks(name="full-plugin", hooks=hooks)

        server.use(plugin)

        assert len(server._plugins) == 1

    def test_use_plugin_invalid_hook_raises_plugin_error(self, tmp_path, monkeypatch):
        """use() should raise PluginError when hooks contain invalid names."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")
        plugin = PluginWithInvalidHooks()

        with pytest.raises(PluginError, match="invalid hook names"):
            server.use(plugin)

        # Plugin should NOT be registered
        assert len(server._plugins) == 0

    def test_use_plugin_missing_name_raises_plugin_error(self, tmp_path, monkeypatch):
        """use() should raise PluginError when plugin lacks a name attribute."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")
        plugin = PluginMissingName()

        with pytest.raises(PluginError, match="'name' attribute"):
            server.use(plugin)

        assert len(server._plugins) == 0

    def test_use_plugin_missing_hooks_raises_plugin_error(self, tmp_path, monkeypatch):
        """use() should raise PluginError when plugin lacks a hooks attribute."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")
        plugin = PluginMissingHooks()

        with pytest.raises(PluginError, match="'hooks' attribute"):
            server.use(plugin)

        assert len(server._plugins) == 0

    def test_use_plugin_name_not_string_raises_plugin_error(
        self, tmp_path, monkeypatch
    ):
        """use() should raise PluginError when name is not a string."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")

        class BadNamePlugin:
            name = 123
            hooks = {}

        with pytest.raises(PluginError, match="'name' attribute"):
            server.use(BadNamePlugin())

        assert len(server._plugins) == 0

    def test_use_plugin_hooks_not_dict_raises_plugin_error(self, tmp_path, monkeypatch):
        """use() should raise PluginError when hooks is not a dict."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")

        class BadHooksPlugin:
            name = "bad"
            hooks = ["before_request"]  # list instead of dict

        with pytest.raises(PluginError, match="'hooks' attribute"):
            server.use(BadHooksPlugin())

        assert len(server._plugins) == 0

    def test_use_plugin_empty_hooks_is_valid(self, tmp_path, monkeypatch):
        """use() should accept a plugin with empty hooks dict."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")
        plugin = ValidPluginWithHooks(name="empty-hooks", hooks={})

        server.use(plugin)

        assert len(server._plugins) == 1


# ---------------------------------------------------------------------------
# Tests: Enhanced enable_ceramic() — unmodified on error
# ---------------------------------------------------------------------------


class TestEnableCeramicEnhanced:
    """Tests for enable_ceramic() ensuring FastMCP is unmodified on error."""

    def test_enable_ceramic_invalid_config_leaves_app_unmodified(
        self, tmp_path, monkeypatch
    ):
        """enable_ceramic() with invalid config should NOT modify the original app."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        config_file = tmp_path / "bad.yaml"
        config_file.write_text("unknown_key: true\n")

        from fastmcp import FastMCP as _FastMCP

        original = _FastMCP(name="original-app")

        # Register a tool on the original
        @original.tool()
        def my_tool(x: int) -> int:
            return x + 1

        with pytest.raises(ConfigurationError):
            CeramicFastMCP.enable_ceramic(original, config=str(config_file))

        # Original should be completely unmodified
        assert original.name == "original-app"

    def test_enable_ceramic_missing_config_raises_configuration_error(
        self, tmp_path, monkeypatch
    ):
        """enable_ceramic() with a non-existent config path should raise."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        from fastmcp import FastMCP as _FastMCP

        original = _FastMCP(name="original-app")

        with pytest.raises(ConfigurationError):
            CeramicFastMCP.enable_ceramic(
                original, config=str(tmp_path / "nonexistent.yaml")
            )

    def test_enable_ceramic_with_plugins_in_config(self, tmp_path, monkeypatch):
        """enable_ceramic() should load plugins from the YAML config."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        # Create a plugin module
        plugin_dir = tmp_path / "my_plugin_pkg"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text(
            "class _Plugin:\n"
            '    name = "my-yaml-plugin"\n'
            "    hooks = {}\n"
            "\n"
            "def create_plugin(config):\n"
            "    return _Plugin()\n"
        )

        # Add plugin dir to path
        monkeypatch.syspath_prepend(str(tmp_path))

        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text(
            "plugins:\n  - module: my_plugin_pkg\n    config:\n      max_requests: 10\n"
        )

        from fastmcp import FastMCP as _FastMCP

        original = _FastMCP(name="original-app")
        wrapped = CeramicFastMCP.enable_ceramic(original, config=str(config_file))

        assert wrapped._app is original
        assert len(wrapped._plugins) == 1
        assert wrapped._plugins[0].name == "my-yaml-plugin"

    def test_enable_ceramic_bad_plugin_module_raises_configuration_error(
        self, tmp_path, monkeypatch
    ):
        """enable_ceramic() should raise ConfigurationError if plugin module fails to import."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text("plugins:\n  - module: nonexistent_module_xyz\n")

        from fastmcp import FastMCP as _FastMCP

        original = _FastMCP(name="original-app")

        with pytest.raises(ConfigurationError, match="Cannot import plugin module"):
            CeramicFastMCP.enable_ceramic(original, config=str(config_file))


# ---------------------------------------------------------------------------
# Tests: _load_plugins_from_config / _load_plugins_from_refs
# ---------------------------------------------------------------------------


class TestPluginLoadingFromConfig:
    """Tests for plugin loading from YAML config."""

    def test_load_valid_plugin_module(self, tmp_path, monkeypatch):
        """Should import module and call create_plugin factory."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        # Create a plugin module
        plugin_dir = tmp_path / "test_plugin_mod"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text(
            "class TestPlugin:\n"
            "    def __init__(self, config):\n"
            '        self.name = "test-loaded"\n'
            "        self.hooks = {}\n"
            "        self.received_config = config\n"
            "\n"
            "def create_plugin(config):\n"
            "    return TestPlugin(config)\n"
        )
        monkeypatch.syspath_prepend(str(tmp_path))

        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text(
            "plugins:\n  - module: test_plugin_mod\n    config:\n      key: value\n"
        )

        server = CeramicFastMCP(name="test-server", config=str(config_file))

        assert len(server._plugins) == 1
        assert server._plugins[0].name == "test-loaded"

    def test_load_plugin_missing_factory_raises(self, tmp_path, monkeypatch):
        """Should raise ConfigurationError if module lacks create_plugin."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        # Create a module without create_plugin
        plugin_dir = tmp_path / "no_factory_mod"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text("# No create_plugin here\nx = 1\n")
        monkeypatch.syspath_prepend(str(tmp_path))

        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text("plugins:\n  - module: no_factory_mod\n")

        with pytest.raises(ConfigurationError, match="create_plugin"):
            CeramicFastMCP(name="test-server", config=str(config_file))

    def test_load_plugin_import_failure_raises(self, tmp_path, monkeypatch):
        """Should raise ConfigurationError if module can't be imported."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text(
            "plugins:\n  - module: this_module_does_not_exist_anywhere\n"
        )

        with pytest.raises(ConfigurationError, match="Cannot import plugin module"):
            CeramicFastMCP(name="test-server", config=str(config_file))

    def test_load_plugin_with_invalid_hooks_raises(self, tmp_path, monkeypatch):
        """Should raise ConfigurationError if loaded plugin has invalid hooks."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        plugin_dir = tmp_path / "bad_hook_mod"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text(
            "class BadPlugin:\n"
            '    name = "bad-hook"\n'
            '    hooks = {"invalid_hook_name": lambda ctx, nxt: None}\n'
            "\n"
            "def create_plugin(config):\n"
            "    return BadPlugin()\n"
        )
        monkeypatch.syspath_prepend(str(tmp_path))

        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text("plugins:\n  - module: bad_hook_mod\n")

        with pytest.raises(ConfigurationError, match="invalid hook names"):
            CeramicFastMCP(name="test-server", config=str(config_file))

    def test_load_plugin_factory_raises_exception(self, tmp_path, monkeypatch):
        """Should raise ConfigurationError if create_plugin raises."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        plugin_dir = tmp_path / "exploding_mod"
        plugin_dir.mkdir()
        (plugin_dir / "__init__.py").write_text(
            'def create_plugin(config):\n    raise RuntimeError("boom")\n'
        )
        monkeypatch.syspath_prepend(str(tmp_path))

        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text("plugins:\n  - module: exploding_mod\n")

        with pytest.raises(ConfigurationError, match="Failed to create plugin"):
            CeramicFastMCP(name="test-server", config=str(config_file))


# ---------------------------------------------------------------------------
# Tests: Middleware pipeline wiring (Task 4.3)
# ---------------------------------------------------------------------------


class TestMiddlewarePipelineWiring:
    """Tests for _build_pipeline() and _middleware_layers introspection.

    Validates Property 3: Configuration Section Activates Middleware.
    """

    def test_passthrough_mode_empty_pipeline(self, tmp_path, monkeypatch):
        """In passthrough mode (no config), the pipeline should be empty."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")

        assert server._passthrough is True
        assert server._middleware_layers == []
        assert server._pipeline._before == []
        assert server._pipeline._after == []

    def test_observability_section_activates_middleware(self, tmp_path, monkeypatch):
        """Config with observability section should add observability middleware."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text("observability:\n  enabled: true\n")

        server = CeramicFastMCP(name="test-server", config=str(config_file))

        assert "observability" in server._middleware_layers
        assert len(server._pipeline._before) == 1

    def test_sessions_section_activates_middleware(self, tmp_path, monkeypatch):
        """Config with sessions section should add session middleware."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text("sessions:\n  enabled: true\n  ttl: 3600\n")

        server = CeramicFastMCP(name="test-server", config=str(config_file))

        assert "session" in server._middleware_layers
        assert len(server._pipeline._before) == 1

    def test_auth_section_activates_middleware(self, tmp_path, monkeypatch):
        """Config with auth section should add authentication middleware."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text(
            "auth:\n"
            "  provider: oidc\n"
            "  issuer: https://idp.example.com\n"
            "  client_id: my-app\n"
        )

        server = CeramicFastMCP(name="test-server", config=str(config_file))

        assert "authentication" in server._middleware_layers
        assert len(server._pipeline._before) == 1

    def test_authorization_section_activates_middleware(self, tmp_path, monkeypatch):
        """Config with authorization section should add authorization middleware."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text(
            "authorization:\n"
            "  role_claim: realm_access.roles\n"
            "  policies:\n"
            "    - tool: admin_*\n"
            "      require_role: admin\n"
        )

        server = CeramicFastMCP(name="test-server", config=str(config_file))

        assert "authorization" in server._middleware_layers
        assert len(server._pipeline._before) == 1

    def test_all_sections_correct_order(self, tmp_path, monkeypatch):
        """Config with all sections should have middleware in fixed order:
        observability → session → authentication → authorization.
        """
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text(
            "observability:\n"
            "  enabled: true\n"
            "sessions:\n"
            "  enabled: true\n"
            "  ttl: 3600\n"
            "auth:\n"
            "  provider: oidc\n"
            "  issuer: https://idp.example.com\n"
            "  client_id: my-app\n"
            "authorization:\n"
            "  role_claim: realm_access.roles\n"
            "  policies: []\n"
        )

        server = CeramicFastMCP(name="test-server", config=str(config_file))

        expected_order = ["observability", "session", "authentication", "authorization"]
        assert server._middleware_layers == expected_order
        assert len(server._pipeline._before) == 4

    def test_absent_section_no_middleware(self, tmp_path, monkeypatch):
        """When a config section is absent, its middleware should NOT be present."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        # Only observability — no session, auth, or authorization
        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text("observability:\n  enabled: true\n")

        server = CeramicFastMCP(name="test-server", config=str(config_file))

        assert "observability" in server._middleware_layers
        assert "session" not in server._middleware_layers
        assert "authentication" not in server._middleware_layers
        assert "authorization" not in server._middleware_layers

    def test_plugins_added_after_builtins(self, tmp_path, monkeypatch):
        """Custom plugins should appear in pipeline after built-in middleware."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text("observability:\n  enabled: true\n")

        server = CeramicFastMCP(name="test-server", config=str(config_file))

        # Manually add a plugin and rebuild pipeline
        async def dummy_before(ctx, nxt):
            return await nxt()

        plugin = ValidPluginWithHooks(
            name="custom-plugin",
            hooks={"before_request": dummy_before},
        )
        server._plugins.append(plugin)
        server._pipeline = server._build_pipeline()

        assert server._middleware_layers == ["observability", "plugin:custom-plugin"]
        # 1 built-in + 1 plugin before-hook
        assert len(server._pipeline._before) == 2

    def test_enable_ceramic_builds_pipeline(self, tmp_path, monkeypatch):
        """enable_ceramic() should also build the middleware pipeline."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text(
            "observability:\n  enabled: true\nsessions:\n  enabled: true\n  ttl: 3600\n"
        )

        from fastmcp import FastMCP as _FastMCP

        original = _FastMCP(name="original-app")
        wrapped = CeramicFastMCP.enable_ceramic(original, config=str(config_file))

        assert wrapped._middleware_layers == ["observability", "session"]
        assert len(wrapped._pipeline._before) == 2

    def test_pipeline_middleware_types_match_config(self, tmp_path, monkeypatch):
        """The middleware instances in the pipeline should be the correct types."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        from ceramic.middleware.builtin import (
            AuthenticationMiddleware,
            AuthorizationMiddleware,
            ObservabilityMiddleware,
            SessionMiddleware,
        )

        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text(
            "observability:\n"
            "  enabled: true\n"
            "sessions:\n"
            "  enabled: true\n"
            "  ttl: 3600\n"
            "auth:\n"
            "  provider: oidc\n"
            "  issuer: https://idp.example.com\n"
            "  client_id: my-app\n"
            "authorization:\n"
            "  role_claim: realm_access.roles\n"
            "  policies: []\n"
        )

        server = CeramicFastMCP(name="test-server", config=str(config_file))

        before_chain = server._pipeline._before
        assert isinstance(before_chain[0], ObservabilityMiddleware)
        assert isinstance(before_chain[1], SessionMiddleware)
        assert isinstance(before_chain[2], AuthenticationMiddleware)
        assert isinstance(before_chain[3], AuthorizationMiddleware)
