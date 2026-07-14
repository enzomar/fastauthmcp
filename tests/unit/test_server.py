"""Trimmed unit tests for CeramicFastMCP (~15 tests).

Covers: init/passthrough, delegation, plugin registration (valid/invalid),
enable_ceramic (valid/invalid), and middleware pipeline wiring.
"""

from __future__ import annotations

import pytest

from ceramic.config import CeramicConfig
from ceramic.exceptions import ConfigurationError, PluginError
from ceramic.server import CeramicFastMCP


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class ValidPlugin:
    def __init__(self, name="valid-plugin", hooks=None):
        self.name = name
        self.hooks = hooks if hooks is not None else {}


class PluginWithInvalidHooks:
    name = "bad-hooks-plugin"
    hooks = {"nonexistent_hook": lambda ctx, nxt: None}


# ---------------------------------------------------------------------------
# Init / Passthrough
# ---------------------------------------------------------------------------


class TestInit:
    def test_no_config_passthrough(self, tmp_path, monkeypatch):
        """No ceramic.yaml → passthrough mode with empty pipeline."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")

        assert server._passthrough is True
        assert server._config == CeramicConfig()
        assert server._middleware_layers == []

    def test_valid_config_loads(self, tmp_path, monkeypatch):
        """Valid ceramic.yaml activates config and disables passthrough."""
        config_file = tmp_path / "ceramic.yaml"
        config_file.write_text("observability:\n  enabled: true\n  log_level: info\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")

        assert server._passthrough is False
        assert server._config.observability.enabled is True

    def test_invalid_yaml_raises(self, tmp_path, monkeypatch):
        """Invalid YAML raises ConfigurationError."""
        (tmp_path / "ceramic.yaml").write_text("auth:\n  provider: [invalid\n")
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        with pytest.raises(ConfigurationError):
            CeramicFastMCP(name="test-server")


# ---------------------------------------------------------------------------
# Delegation
# ---------------------------------------------------------------------------


class TestDelegation:
    def test_tool_decorator(self, tmp_path, monkeypatch):
        """tool() registers on the internal FastMCP instance."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")

        @server.tool()
        def my_tool(x: int) -> int:
            return x * 2

        assert server._app is not None


# ---------------------------------------------------------------------------
# Plugin registration: valid and invalid
# ---------------------------------------------------------------------------


class TestPluginRegistration:
    def test_valid_plugin_works(self, tmp_path, monkeypatch):
        """use() accepts a valid plugin with correct hook names."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")
        plugin = ValidPlugin(hooks={"before_request": lambda ctx, nxt: None})
        server.use(plugin)

        assert len(server._plugins) == 1
        assert server._plugins[0].name == "valid-plugin"

    def test_invalid_plugin_raises(self, tmp_path, monkeypatch):
        """use() raises PluginError for invalid hook names."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        server = CeramicFastMCP(name="test-server")
        with pytest.raises(PluginError, match="invalid hook names"):
            server.use(PluginWithInvalidHooks())
        assert len(server._plugins) == 0


# ---------------------------------------------------------------------------
# enable_ceramic
# ---------------------------------------------------------------------------


class TestEnableCeramic:
    def test_wraps_existing_instance(self, tmp_path, monkeypatch):
        """enable_ceramic() wraps an existing FastMCP with passthrough."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        from fastmcp import FastMCP as _FastMCP

        original = _FastMCP(name="original-app")
        wrapped = CeramicFastMCP.enable_ceramic(original)

        assert isinstance(wrapped, CeramicFastMCP)
        assert wrapped._app is original
        assert wrapped._passthrough is True

    def test_invalid_config_raises(self, tmp_path, monkeypatch):
        """enable_ceramic() with invalid config raises ConfigurationError."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        (tmp_path / "bad.yaml").write_text("invalid_key: true\n")

        from fastmcp import FastMCP as _FastMCP

        original = _FastMCP(name="original-app")
        with pytest.raises(ConfigurationError):
            CeramicFastMCP.enable_ceramic(original, config=str(tmp_path / "bad.yaml"))


# ---------------------------------------------------------------------------
# Middleware pipeline wiring
# ---------------------------------------------------------------------------


class TestPipelineWiring:
    def test_all_sections_correct_order(self, tmp_path, monkeypatch):
        """Config with all sections produces observability → session → auth order."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        (tmp_path / "ceramic.yaml").write_text(
            "observability:\n  enabled: true\n"
            "sessions:\n  enabled: true\n  ttl: 3600\n"
            "auth:\n  provider: oidc\n  issuer: https://idp.example.com\n  client_id: my-app\n"
        )
        server = CeramicFastMCP(
            name="test-server", config=str(tmp_path / "ceramic.yaml")
        )

        assert server._middleware_layers == [
            "observability",
            "session",
            "authentication",
        ]
        assert len(server._pipeline._before) == 3

    def test_absent_section_no_middleware(self, tmp_path, monkeypatch):
        """Absent config sections don't add their middleware."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        (tmp_path / "ceramic.yaml").write_text("observability:\n  enabled: true\n")
        server = CeramicFastMCP(
            name="test-server", config=str(tmp_path / "ceramic.yaml")
        )

        assert "observability" in server._middleware_layers
        assert "session" not in server._middleware_layers
        assert "authentication" not in server._middleware_layers

    def test_plugins_added_after_builtins(self, tmp_path, monkeypatch):
        """Custom plugins appear after built-in middleware in the pipeline."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        (tmp_path / "ceramic.yaml").write_text("observability:\n  enabled: true\n")
        server = CeramicFastMCP(
            name="test-server", config=str(tmp_path / "ceramic.yaml")
        )

        async def dummy_before(ctx, nxt):
            return await nxt()

        plugin = ValidPlugin(name="custom", hooks={"before_request": dummy_before})
        server._plugins.append(plugin)
        server._pipeline = server._build_pipeline()

        assert server._middleware_layers == ["observability", "plugin:custom"]

    def test_pipeline_types_match(self, tmp_path, monkeypatch):
        """The middleware instances in the pipeline are the correct types."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)

        from ceramic.middleware.builtin import (
            AuthenticationMiddleware,
            ObservabilityMiddleware,
            SessionMiddleware,
        )

        (tmp_path / "ceramic.yaml").write_text(
            "observability:\n  enabled: true\n"
            "sessions:\n  enabled: true\n  ttl: 3600\n"
            "auth:\n  provider: oidc\n  issuer: https://idp.example.com\n  client_id: my-app\n"
        )
        server = CeramicFastMCP(
            name="test-server", config=str(tmp_path / "ceramic.yaml")
        )

        before_chain = server._pipeline._before
        assert isinstance(before_chain[0], ObservabilityMiddleware)
        assert isinstance(before_chain[1], SessionMiddleware)
        assert isinstance(before_chain[2], AuthenticationMiddleware)
