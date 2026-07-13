"""Unit tests for ConfigLoader."""

import os
from pathlib import Path

import pytest

from ceramic.config import CeramicConfig
from ceramic.config_loader import ConfigLoader
from ceramic.exceptions import ConfigurationError


@pytest.fixture
def loader():
    return ConfigLoader()


@pytest.fixture
def valid_yaml(tmp_path):
    """Create a valid ceramic.yaml in a temp directory."""
    content = """\
observability:
  enabled: true
  log_level: info
sessions:
  ttl: 7200
"""
    path = tmp_path / "ceramic.yaml"
    path.write_text(content)
    return path


@pytest.fixture
def full_yaml(tmp_path):
    """Create a full ceramic.yaml with auth section."""
    content = """\
auth:
  provider: oidc
  issuer: https://idp.example.com
  client_id: my-app
  client_secret: secret123
  callback_timeout: 60
observability:
  enabled: true
  log_level: debug
  metrics_port: 8080
sessions:
  ttl: 1800
"""
    path = tmp_path / "ceramic.yaml"
    path.write_text(content)
    return path


class TestConfigLoaderResolution:
    """Tests for configuration path resolution."""

    def test_load_explicit_path(self, loader, valid_yaml):
        config = loader.load(path=valid_yaml)
        assert config.observability is not None
        assert config.observability.log_level == "info"
        assert config.sessions is not None
        assert config.sessions.ttl == 7200

    def test_load_explicit_path_not_found(self, loader, tmp_path):
        missing = tmp_path / "missing.yaml"
        with pytest.raises(ConfigurationError, match="not found"):
            loader.load(path=missing)

    def test_load_from_env_var(self, loader, valid_yaml, monkeypatch):
        monkeypatch.setenv("CERAMIC_CONFIG", str(valid_yaml))
        config = loader.load()
        assert config.observability is not None
        assert config.observability.log_level == "info"

    def test_load_env_var_missing_file(self, loader, tmp_path, monkeypatch):
        monkeypatch.setenv("CERAMIC_CONFIG", str(tmp_path / "nope.yaml"))
        with pytest.raises(ConfigurationError, match="not found"):
            loader.load()

    def test_load_from_cwd(self, loader, tmp_path, monkeypatch):
        content = "sessions:\n  ttl: 3600\n"
        (tmp_path / "ceramic.yaml").write_text(content)
        monkeypatch.chdir(tmp_path)
        config = loader.load()
        assert config.sessions is not None
        assert config.sessions.ttl == 3600

    def test_load_no_config_passthrough(self, loader, tmp_path, monkeypatch):
        """When no config is found anywhere, return empty CeramicConfig."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("CERAMIC_CONFIG", raising=False)
        config = loader.load()
        assert config == CeramicConfig()

    def test_env_var_takes_precedence_over_cwd(self, loader, tmp_path, monkeypatch):
        """CERAMIC_CONFIG env var takes precedence over CWD ceramic.yaml."""
        # Create ceramic.yaml in CWD with sessions.ttl=1000
        cwd_yaml = tmp_path / "cwd"
        cwd_yaml.mkdir()
        (cwd_yaml / "ceramic.yaml").write_text("sessions:\n  ttl: 1000\n")

        # Create a different config pointed to by env var
        env_yaml = tmp_path / "env_config.yaml"
        env_yaml.write_text("sessions:\n  ttl: 2000\n")

        monkeypatch.chdir(cwd_yaml)
        monkeypatch.setenv("CERAMIC_CONFIG", str(env_yaml))

        config = loader.load()
        assert config.sessions.ttl == 2000


class TestConfigLoaderYAMLParsing:
    """Tests for YAML parsing and validation."""

    def test_invalid_yaml_syntax(self, loader, tmp_path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("auth:\n  provider: [unterminated")
        with pytest.raises(ConfigurationError, match="Invalid YAML"):
            loader.load(path=bad_yaml)

    def test_unknown_top_level_keys(self, loader, tmp_path):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("unknown_key: value\n")
        with pytest.raises(ConfigurationError, match="validation error"):
            loader.load(path=bad_yaml)

    def test_empty_yaml_file(self, loader, tmp_path):
        empty_yaml = tmp_path / "empty.yaml"
        empty_yaml.write_text("")
        config = loader.load(path=empty_yaml)
        assert config == CeramicConfig()

    def test_yaml_with_only_comments(self, loader, tmp_path):
        yaml_file = tmp_path / "comments.yaml"
        yaml_file.write_text("# just a comment\n")
        config = loader.load(path=yaml_file)
        assert config == CeramicConfig()

    def test_non_mapping_top_level(self, loader, tmp_path):
        bad_yaml = tmp_path / "list.yaml"
        bad_yaml.write_text("- item1\n- item2\n")
        with pytest.raises(ConfigurationError, match="expected a mapping"):
            loader.load(path=bad_yaml)

    def test_stderr_output_on_invalid_yaml(self, loader, tmp_path, capsys):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("auth:\n  provider: [unterminated")
        with pytest.raises(ConfigurationError):
            loader.load(path=bad_yaml)
        captured = capsys.readouterr()
        assert "Invalid YAML" in captured.err

    def test_stderr_output_on_missing_env_path(self, loader, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("CERAMIC_CONFIG", str(tmp_path / "gone.yaml"))
        with pytest.raises(ConfigurationError):
            loader.load()
        captured = capsys.readouterr()
        assert "not found" in captured.err

    def test_stderr_output_on_unknown_keys(self, loader, tmp_path, capsys):
        bad_yaml = tmp_path / "bad.yaml"
        bad_yaml.write_text("bogus: true\n")
        with pytest.raises(ConfigurationError):
            loader.load(path=bad_yaml)
        captured = capsys.readouterr()
        assert "validation error" in captured.err


class TestEnvOverrides:
    """Tests for environment variable overrides."""

    def test_override_scalar_string(self, loader, full_yaml, monkeypatch):
        monkeypatch.setenv("CERAMIC_AUTH_CLIENT_ID", "overridden-app")
        config = loader.load(path=full_yaml)
        assert config.auth.client_id == "overridden-app"

    def test_override_scalar_int(self, loader, full_yaml, monkeypatch):
        monkeypatch.setenv("CERAMIC_OBSERVABILITY_METRICS_PORT", "9999")
        config = loader.load(path=full_yaml)
        assert config.observability.metrics_port == 9999

    def test_override_scalar_bool_true(self, loader, full_yaml, monkeypatch):
        monkeypatch.setenv("CERAMIC_OBSERVABILITY_ENABLED", "true")
        config = loader.load(path=full_yaml)
        assert config.observability.enabled is True

    def test_override_scalar_bool_false(self, loader, full_yaml, monkeypatch):
        monkeypatch.setenv("CERAMIC_OBSERVABILITY_ENABLED", "false")
        config = loader.load(path=full_yaml)
        assert config.observability.enabled is False

    def test_override_bool_with_1(self, loader, full_yaml, monkeypatch):
        monkeypatch.setenv("CERAMIC_OBSERVABILITY_ENABLED", "1")
        config = loader.load(path=full_yaml)
        assert config.observability.enabled is True

    def test_override_bool_with_0(self, loader, full_yaml, monkeypatch):
        monkeypatch.setenv("CERAMIC_OBSERVABILITY_ENABLED", "0")
        config = loader.load(path=full_yaml)
        assert config.observability.enabled is False

    def test_skip_non_scalar_list(self, loader, tmp_path, monkeypatch):
        """Env override targeting a list value should be skipped."""
        content = """\
auth:
  provider: oidc
  issuer: https://idp.example.com
  client_id: app
  scopes:
    - openid
    - profile
"""
        yaml_path = tmp_path / "ceramic.yaml"
        yaml_path.write_text(content)
        monkeypatch.setenv("CERAMIC_AUTH_SCOPES", "custom")
        config = loader.load(path=yaml_path)
        # scopes should remain unchanged (list not overridden)
        assert config.auth.scopes == ["openid", "profile"]

    def test_ceramic_config_env_not_treated_as_override(self, loader, valid_yaml, monkeypatch):
        """CERAMIC_CONFIG env var should not be treated as a config override."""
        monkeypatch.setenv("CERAMIC_CONFIG", str(valid_yaml))
        config = loader.load()
        # Should load normally without error about unknown path
        assert config.observability is not None

    def test_override_nested_underscore_field(self, loader, full_yaml, monkeypatch):
        """CERAMIC_AUTH_CALLBACK_TIMEOUT → auth.callback_timeout."""
        monkeypatch.setenv("CERAMIC_AUTH_CALLBACK_TIMEOUT", "90")
        config = loader.load(path=full_yaml)
        assert config.auth.callback_timeout == 90

    def test_override_log_level(self, loader, full_yaml, monkeypatch):
        monkeypatch.setenv("CERAMIC_OBSERVABILITY_LOG_LEVEL", "warning")
        config = loader.load(path=full_yaml)
        assert config.observability.log_level == "warning"

    def test_no_override_when_path_not_in_config(self, loader, valid_yaml, monkeypatch):
        """Env vars targeting non-existent paths are silently ignored."""
        monkeypatch.setenv("CERAMIC_NONEXISTENT_KEY", "value")
        config = loader.load(path=valid_yaml)
        # Should not raise — just load normally
        assert config.observability is not None


class TestWatchStub:
    """Test that watch() is a no-op stub."""

    def test_watch_does_not_raise(self, loader):
        # Should not raise
        loader.watch(lambda cfg: None)
